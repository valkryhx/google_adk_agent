from __future__ import annotations

import json
import re
import uuid
from typing import Any, Callable, Iterable

import litellm

from .kairos_config import DEFAULT_KAIROS_PROMPT_CONFIG, KairosPromptConfig
from .models import (
    DocumentReadResult,
    KairosActionPayload,
    KairosExecutionPlan,
    KairosReplanResult,
    KairosUnderstandingResult,
    KairosVerificationResult,
)


ALLOWED_ACTION_KINDS = {
    "update_document",
    "spawn_dex_task",
    "agent_execute",
    "wait_for_artifact",
    "summarize_progress",
    "ask_user",
    "sleep",
}

SAFE_COMMAND_TEMPLATES = (
    "draft_requirements_doc",
    "generate_todo_app",
    "run_smoke_check",
    "summarize_delivery",
)

DOC_SECTIONS = (
    "Goal",
    "Current Status",
    "Current Step",
    "Steps",
    "Expected Artifacts",
    "Blockers",
    "Verification",
    "Replan Notes",
    "Spawned Work",
)


class KairosPlanner:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        api_base: str,
        extra_body: dict[str, Any] | None = None,
        timeout_seconds: int = 60,
        max_retries: int = 3,
        prompt_config: KairosPromptConfig | None = None,
        list_available_skill_catalog: Callable[[], Iterable[dict[str, Any]] | Iterable[str]] | None = None,
    ):
        self._model = model
        self._api_key = api_key
        self._api_base = api_base
        self._extra_body = extra_body or {}
        self._timeout_seconds = self._normalize_timeout_seconds(timeout_seconds)
        self._max_retries = self._normalize_max_retries(max_retries)
        self._prompt_config = prompt_config or DEFAULT_KAIROS_PROMPT_CONFIG
        self._list_available_skill_catalog = list_available_skill_catalog

    @staticmethod
    def _normalize_timeout_seconds(timeout_seconds: int | float | None) -> int:
        if timeout_seconds is None:
            return 120
        try:
            normalized = int(timeout_seconds)
        except (TypeError, ValueError):
            return 120
        if normalized <= 0:
            return 120
        # Some runtimes store timeout in milliseconds (e.g., 600000).
        if normalized > 3600:
            normalized = max(1, normalized // 1000)
        # Keep a sane lower/upper bound while preserving configured intent.
        return max(15, min(normalized, 600))

    @staticmethod
    def _normalize_max_retries(max_retries: int | float | None) -> int:
        if max_retries is None:
            return 3
        try:
            normalized = int(max_retries)
        except (TypeError, ValueError):
            return 3
        if normalized < 0:
            return 3
        return normalized

    def _resolve_available_skill_catalog(self) -> list[dict[str, str]]:
        provider = self._list_available_skill_catalog
        if provider is None:
            return []
        try:
            raw_items = list(provider())
        except Exception:
            return []
        deduped: dict[str, dict[str, str]] = {}
        for raw in raw_items:
            if isinstance(raw, str):
                skill_id = raw.strip()
                if not skill_id:
                    continue
                deduped[skill_id] = {"id": skill_id, "name": skill_id, "description": ""}
                continue
            if not isinstance(raw, dict):
                continue
            skill_id = str(raw.get("id", "")).strip()
            if not skill_id:
                continue
            name = str(raw.get("name", "")).strip() or skill_id
            description = str(raw.get("description", "")).strip().replace("\r", " ").replace("\n", " ")
            if len(description) > 220:
                description = f"{description[:217]}..."
            if skill_id in deduped:
                if not deduped[skill_id].get("description") and description:
                    deduped[skill_id]["description"] = description
                if deduped[skill_id].get("name", skill_id) == skill_id and name:
                    deduped[skill_id]["name"] = name
                continue
            deduped[skill_id] = {"id": skill_id, "name": name, "description": description}
        return [deduped[skill_id] for skill_id in sorted(deduped)]

    def _build_skill_context(self) -> dict[str, Any]:
        catalog = self._resolve_available_skill_catalog()
        skill_ids = [item["id"] for item in catalog]
        hints: list[dict[str, str]] = []

        def _add_hint(intent: str, preferred_skill_id: str) -> None:
            if preferred_skill_id in skill_ids:
                hints.append({"intent": intent, "preferred_skill_id": preferred_skill_id})

        _add_hint("网络搜索/网页信息获取", "web-search")
        _add_hint("代码搜索/仓库定位", "codebase_search")
        _add_hint("命令执行/环境检查", "bash")

        return {
            "available_skills": catalog[:120],
            "available_skill_ids": skill_ids[:200],
            "skill_selection_hints": hints,
        }

    @staticmethod
    def _coerce_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if not text:
            return None
        truthy = {"true", "1", "yes", "y", "stop", "halt", "terminate", "终止", "中止", "停止", "结束"}
        falsy = {"false", "0", "no", "n", "continue", "继续", "否", "不中止"}
        if text in truthy:
            return True
        if text in falsy:
            return False
        return None

    @staticmethod
    def _split_nonempty_lines(text: str) -> list[str]:
        return [line.strip("-* \t") for line in str(text or "").splitlines() if line.strip()]

    @staticmethod
    def _first_line(text: str, default: str = "") -> str:
        for line in str(text or "").splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned
        return default

    @staticmethod
    def _normalize_phase_payload(raw: dict[str, Any]) -> dict[str, Any]:
        data = dict(raw or {})
        goal = (
            data.get("任务目标")
            or data.get("goal")
            or data.get("task_goal")
            or data.get("objective")
            or ""
        )
        current_phase = (
            data.get("本阶段")
            or data.get("current_phase")
            or data.get("current")
            or ""
        )
        next_phase = (
            data.get("下阶段")
            or data.get("next_phase")
            or data.get("next")
            or ""
        )
        should_stop = (
            data.get("任务是否中止")
            if "任务是否中止" in data
            else data.get("should_stop")
        )
        return {
            "goal": str(goal or "").strip(),
            "current_phase": str(current_phase or "").strip(),
            "next_phase": str(next_phase or "").strip(),
            "should_stop": KairosPlanner._coerce_bool(should_stop),
        }

    def _infer_action_kind(self, text: str, *, fallback: str = "agent_execute") -> str:
        lowered = str(text or "").lower()
        if not lowered:
            return fallback
        if any(token in lowered for token in ("ask_user", "ask user", "需要用户", "用户确认", "人工确认", "提问")):
            return "ask_user"
        if any(token in lowered for token in ("sleep", "等待", "稍后", "挂起", "暂缓")):
            return "sleep"
        if any(token in lowered for token in ("spawn_dex_task", "dex", "创建任务", "派发任务", "follow-up", "follow up")):
            return "spawn_dex_task"
        if any(token in lowered for token in ("update_document", "更新文档", "回写文档", "patch")):
            return "update_document"
        if any(token in lowered for token in ("summarize_progress", "总结进度", "阶段总结", "summary")):
            return "summarize_progress"
        return fallback

    def _infer_required_skills(self, text: str, skill_context: dict[str, Any]) -> list[str]:
        content = str(text or "")
        lowered = content.lower()
        available_ids = [str(item).strip() for item in skill_context.get("available_skill_ids", []) if str(item).strip()]
        if not available_ids:
            return []

        selected: list[str] = []
        for skill_id in available_ids:
            if skill_id.lower() in lowered and skill_id not in selected:
                selected.append(skill_id)

        keyword_to_skill = [
            (("代码", "仓库", "ripgrep", "grep", "search code"), "codebase_search"),
            (("命令", "shell", "终端", "bash", "powershell"), "bash"),
            (("文档", "文件", "markdown", "read file", "edit file"), "file_editor"),
            (("网络", "联网", "网页", "web", "search"), "web-search"),
        ]
        for keywords, candidate_skill in keyword_to_skill:
            if candidate_skill not in available_ids:
                continue
            if candidate_skill in selected:
                continue
            if any(keyword in lowered for keyword in keywords):
                selected.append(candidate_skill)

        return selected[:4]

    @staticmethod
    def _text_requests_user(text: str) -> bool:
        lowered = str(text or "").lower()
        if not lowered:
            return False
        return any(token in lowered for token in ("ask_user", "ask user", "需要用户", "用户确认", "人工确认"))

    def _compose_step_from_phase(
        self,
        *,
        phase_payload: dict[str, Any],
        default_step_id: str,
        candidate_actions: list[str] | None,
        skill_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        current_phase = str(phase_payload.get("current_phase") or "")
        next_phase = str(phase_payload.get("next_phase") or "")
        phase_text = "\n".join(part for part in (current_phase, next_phase) if part).strip()
        if not phase_text:
            return None

        action_kind = self._infer_action_kind(phase_text, fallback="agent_execute")
        candidate_set = set(candidate_actions or [])
        if candidate_set and action_kind not in candidate_set:
            action_kind = "agent_execute" if "agent_execute" in candidate_set else next(iter(candidate_set))

        step: dict[str, Any] = {
            "step_id": default_step_id or "step-1",
            "action_kind": action_kind,
            "reason": self._first_line(current_phase, default="phase-planned-action"),
            "exit_condition": self._first_line(next_phase, default="完成本阶段核验"),
        }
        if action_kind == "agent_execute":
            execution_prompt = next_phase or current_phase or "继续推进任务并更新文档"
            step["execution_prompt"] = execution_prompt
            inferred_skills = self._infer_required_skills(execution_prompt, skill_context)
            if inferred_skills:
                step["required_skills"] = inferred_skills
        return step

    @staticmethod
    def _extract_phase_payload_from_text(text: str) -> dict[str, Any]:
        section_pattern = re.compile(
            r"^(?:#{1,6}\s*)?(任务目标|本阶段|下阶段|任务是否中止|goal|current_phase|next_phase|should_stop)\s*[:：]?\s*(.*)$",
            re.IGNORECASE,
        )
        label_to_key = {
            "任务目标": "goal",
            "goal": "goal",
            "本阶段": "current_phase",
            "current_phase": "current_phase",
            "下阶段": "next_phase",
            "next_phase": "next_phase",
            "任务是否中止": "should_stop",
            "should_stop": "should_stop",
        }
        sections: dict[str, list[str]] = {
            "goal": [],
            "current_phase": [],
            "next_phase": [],
            "should_stop": [],
        }
        current_key: str | None = None
        for raw_line in str(text or "").splitlines():
            line = raw_line.rstrip()
            match = section_pattern.match(line.strip())
            if match:
                label = str(match.group(1)).lower()
                key = label_to_key.get(label, label_to_key.get(str(match.group(1)), ""))
                if key:
                    current_key = key
                    inline_content = str(match.group(2) or "").strip()
                    if inline_content:
                        sections[key].append(inline_content)
                    continue
            if current_key is not None:
                sections[current_key].append(line)

        payload: dict[str, Any] = {}
        for key, lines in sections.items():
            value = "\n".join(item for item in lines if str(item).strip()).strip()
            if value:
                if key == "should_stop":
                    payload[key] = KairosPlanner._coerce_bool(value)
                else:
                    payload[key] = value
        if payload:
            return payload
        text_fallback = str(text or "").strip()
        if not text_fallback:
            return {}
        return {"current_phase": text_fallback}

    async def draft_requirement_understanding(self, item: DocumentReadResult) -> KairosUnderstandingResult:
        system_prompt = self._prompt_config.requirement_understanding_system
        user_prompt = json.dumps(
            {
                "work_id": item.work_id,
                "goal": item.goal,
                "status": item.status,
                "current_step": item.current_step,
                "next_actions": item.next_actions,
                "expected_artifacts": item.expected_artifacts,
                "open_questions": item.open_questions,
                "source_docs": item.source_docs,
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
        phase_payload = self._normalize_phase_payload(raw)

        goal = str(raw.get("goal") or phase_payload.get("goal") or item.goal).strip()
        constraints = list(raw.get("constraints", []))
        assumptions = list(raw.get("assumptions", []))
        missing_info = list(raw.get("missing_info", []))
        success_criteria = list(raw.get("success_criteria", []))
        current_artifacts = list(raw.get("current_artifacts", []))
        risk_flags = list(raw.get("risk_flags", []))
        recommended_mode = raw.get("recommended_mode")

        current_phase_lines = self._split_nonempty_lines(phase_payload.get("current_phase", ""))
        next_phase_lines = self._split_nonempty_lines(phase_payload.get("next_phase", ""))

        if not constraints and current_phase_lines:
            constraints = current_phase_lines[:8]
        if not assumptions:
            assumptions = [line for line in current_phase_lines if any(token in line for token in ("默认", "假设", "assume"))][:5]
        if not missing_info:
            missing_info = [line for line in current_phase_lines if any(token in line for token in ("缺", "阻塞", "待确认", "missing"))][:5]
        if not success_criteria and next_phase_lines:
            success_criteria = next_phase_lines[:8]
        if not current_artifacts:
            current_artifacts = list(item.expected_artifacts or [])
        if not risk_flags:
            risk_flags = [line for line in current_phase_lines if any(token in line.lower() for token in ("风险", "risk", "失败", "error"))][:5]
        if not recommended_mode:
            if phase_payload.get("should_stop") is True:
                recommended_mode = "waiting_artifact"
            elif self._text_requests_user(phase_payload.get("current_phase", "")):
                recommended_mode = "ask_user"
            else:
                recommended_mode = "active_execution"

        return KairosUnderstandingResult(
            goal=goal,
            constraints=constraints,
            assumptions=assumptions,
            missing_info=missing_info,
            success_criteria=success_criteria,
            current_artifacts=current_artifacts,
            risk_flags=risk_flags,
            recommended_mode=str(recommended_mode or "active_execution"),
        )

    async def build_execution_plan(
        self,
        item: DocumentReadResult,
        understanding: KairosUnderstandingResult,
        *,
        candidate_actions: list[str],
    ) -> KairosExecutionPlan:
        last_raw: dict[str, Any] = {}
        system_prompt = self._prompt_config.render_execution_plan_system(ALLOWED_ACTION_KINDS)
        skill_context = self._build_skill_context()
        user_prompt = json.dumps(
            {
                "work_id": item.work_id,
                "goal": item.goal,
                "current_step": item.current_step,
                "understanding": understanding.__dict__,
                "candidate_actions": candidate_actions,
                **skill_context,
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
        last_raw = dict(raw)
        raw.setdefault("plan_id", f"plan-{uuid.uuid4().hex[:8]}")
        raw.setdefault("work_id", item.work_id)
        self._sanitize_plan(raw)
        phase_payload = self._normalize_phase_payload(raw)
        if not raw["steps"]:
            phase_step = self._compose_step_from_phase(
                phase_payload=phase_payload,
                default_step_id=item.current_step or "step-1",
                candidate_actions=candidate_actions,
                skill_context=skill_context,
            )
            if phase_step is not None:
                raw["steps"] = [phase_step]
                raw["summary"] = raw.get("summary") or phase_payload.get("current_phase") or phase_payload.get("goal")
                if phase_payload.get("should_stop") is True:
                    raw["stop_conditions"] = list(raw.get("stop_conditions", [])) + ["任务可中止"]
                    raw["completion_definition"] = list(raw.get("completion_definition", [])) + ["目标已完成并通过核验"]
                self._sanitize_plan(raw)
        if not raw["steps"]:
            retry_system_prompt = self._prompt_config.render_execution_plan_retry_system(ALLOWED_ACTION_KINDS)
            retry_user_prompt = json.dumps(
                {
                    "work_id": item.work_id,
                    "goal": item.goal,
                    "current_step": item.current_step,
                    "understanding": understanding.__dict__,
                    "candidate_actions": candidate_actions,
                    **skill_context,
                    "previous_output": raw,
                    "failure_reason": "empty_steps",
                },
                ensure_ascii=False,
            )
            raw = await self._complete_json(retry_system_prompt, retry_user_prompt)
            last_raw = dict(raw)
            raw.setdefault("plan_id", f"plan-{uuid.uuid4().hex[:8]}")
            raw.setdefault("work_id", item.work_id)
            self._sanitize_plan(raw)
            phase_payload = self._normalize_phase_payload(raw)
            if not raw["steps"]:
                phase_step = self._compose_step_from_phase(
                    phase_payload=phase_payload,
                    default_step_id=item.current_step or "step-1",
                    candidate_actions=candidate_actions,
                    skill_context=skill_context,
                )
                if phase_step is not None:
                    raw["steps"] = [phase_step]
                    raw["summary"] = raw.get("summary") or phase_payload.get("current_phase") or phase_payload.get("goal")
                    if phase_payload.get("should_stop") is True:
                        raw["stop_conditions"] = list(raw.get("stop_conditions", [])) + ["任务可中止"]
                        raw["completion_definition"] = list(raw.get("completion_definition", [])) + ["目标已完成并通过核验"]
                    self._sanitize_plan(raw)
        if not raw["steps"]:
            raise ValueError(
                f"llm execution plan contains no steps; raw_keys={sorted(last_raw.keys())}"
            )
        return KairosExecutionPlan(**raw)

    async def build_action_payload(
        self,
        *,
        work_item: DocumentReadResult,
        step: dict[str, Any],
    ) -> KairosActionPayload:
        system_prompt = self._prompt_config.render_action_payload_system(
            allowed_action_kinds=ALLOWED_ACTION_KINDS,
            safe_templates=SAFE_COMMAND_TEMPLATES,
        )
        skill_context = self._build_skill_context()
        user_prompt = json.dumps(
            {
                "work_item": work_item.__dict__,
                "step": step,
                "allowed_action_kinds": sorted(ALLOWED_ACTION_KINDS),
                **skill_context,
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
        raw["action_kind"] = step.get("action_kind")
        phase_payload = self._normalize_phase_payload(raw)
        raw.setdefault("rationale", phase_payload.get("current_phase") or phase_payload.get("goal"))
        if raw["action_kind"] == "agent_execute":
            args = dict(raw.get("args", {}))
            execution_prompt = str(args.get("execution_prompt") or phase_payload.get("next_phase") or phase_payload.get("current_phase") or "").strip()
            if execution_prompt:
                args["execution_prompt"] = execution_prompt
            if not args.get("required_skills"):
                inferred_skills = self._infer_required_skills(execution_prompt, skill_context)
                if inferred_skills:
                    args["required_skills"] = inferred_skills
            raw["args"] = args
        elif raw["action_kind"] == "ask_user":
            raw.setdefault("question", self._first_line(phase_payload.get("next_phase", ""), default="请补充安全关键阻塞信息"))
            raw.setdefault("why_blocked", phase_payload.get("current_phase") or raw.get("question"))
        elif raw["action_kind"] == "summarize_progress":
            raw.setdefault("brief", phase_payload.get("current_phase") or phase_payload.get("next_phase"))
        return self._sanitize_action_payload(raw)

    async def build_document_patch_payload(
        self,
        *,
        work_item: DocumentReadResult,
        step: dict[str, Any],
    ) -> KairosActionPayload:
        system_prompt = self._prompt_config.render_document_patch_system(DOC_SECTIONS)
        user_prompt = json.dumps(
            {
                "work_item": work_item.__dict__,
                "step": step,
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
        raw["action_kind"] = "update_document"
        phase_payload = self._normalize_phase_payload(raw)
        if not raw.get("section_updates"):
            update_text = phase_payload.get("current_phase") or phase_payload.get("next_phase") or step.get("reason") or "update progress"
            raw["section_updates"] = [
                {
                    "section": "Replan Notes",
                    "text": str(update_text).strip(),
                }
            ]
        return self._sanitize_action_payload(raw)

    async def build_design_codegen_payload(
        self,
        *,
        work_item: DocumentReadResult,
        step: dict[str, Any],
    ) -> KairosActionPayload:
        system_prompt = self._prompt_config.render_design_codegen_system(SAFE_COMMAND_TEMPLATES)
        user_prompt = json.dumps(
            {
                "work_item": work_item.__dict__,
                "step": step,
                "allowed_templates": list(SAFE_COMMAND_TEMPLATES),
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
        raw["action_kind"] = "spawn_dex_task"
        phase_payload = self._normalize_phase_payload(raw)
        raw.setdefault("description", self._first_line(phase_payload.get("next_phase", ""), default=str(step.get("reason") or "llm generated dex task")))
        raw.setdefault("brief", phase_payload.get("current_phase") or phase_payload.get("next_phase") or raw.get("description"))
        if not raw.get("command_template_id"):
            lower_step = str(step.get("step_id") or work_item.current_step or "").lower()
            if "verify" in lower_step or "test" in lower_step:
                raw["command_template_id"] = "run_smoke_check"
            elif "delivery" in lower_step or "report" in lower_step:
                raw["command_template_id"] = "summarize_delivery"
            else:
                raw["command_template_id"] = "draft_requirements_doc"
        raw.setdefault("expected_artifacts", list(work_item.expected_artifacts))
        return self._sanitize_action_payload(raw)

    async def verify_attempt(
        self,
        *,
        attempt_id: str,
        work_item: DocumentReadResult,
        attempt_summary: dict[str, Any],
        artifacts: list[dict[str, Any]],
    ) -> KairosVerificationResult:
        system_prompt = self._prompt_config.verification_system
        user_prompt = json.dumps(
            {
                "attempt_id": attempt_id,
                "work_item": work_item.__dict__,
                "attempt_summary": attempt_summary,
                "artifacts": artifacts,
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
        phase_payload = self._normalize_phase_payload(raw)
        verdict = str(raw.get("verdict") or "").strip().lower()
        phase_text = f"{phase_payload.get('current_phase', '')}\n{phase_payload.get('next_phase', '')}".lower()
        if verdict not in {"pass", "partial", "fail", "unknown"}:
            if any(token in phase_text for token in ("通过", "pass", "ready", "完成", "ok")):
                verdict = "pass"
            elif any(token in phase_text for token in ("失败", "fail", "error", "未通过")):
                verdict = "fail"
            elif any(token in phase_text for token in ("部分", "partial", "待补充", "未完成")):
                verdict = "partial"
            else:
                verdict = "unknown"

        evidence = list(raw.get("evidence", []))
        if not evidence and phase_payload.get("current_phase"):
            evidence = [{"source": "phase_current", "note": phase_payload.get("current_phase", "")}]

        artifact_check = list(raw.get("artifact_check", []))
        if not artifact_check:
            artifact_check = [
                {
                    "artifact": item.get("artifact"),
                    "exists": item.get("exists"),
                    "usable": item.get("usable", item.get("exists")),
                    "note": item.get("note"),
                }
                for item in artifacts
            ]

        goal_progress = raw.get("goal_progress")
        if not isinstance(goal_progress, int):
            goal_progress = {
                "pass": 100,
                "partial": 60,
                "fail": 25,
                "unknown": 40,
            }.get(verdict, 40)
        goal_progress = max(0, min(100, int(goal_progress)))

        remaining_gaps = list(raw.get("remaining_gaps", []))
        if not remaining_gaps and phase_payload.get("next_phase"):
            remaining_gaps = self._split_nonempty_lines(phase_payload.get("next_phase", ""))[:6]

        next_best_action = str(raw.get("next_best_action") or "").strip()
        if not next_best_action:
            next_best_action = self._first_line(phase_payload.get("next_phase", ""), default=str(attempt_summary.get("description") or "continue"))

        should_replan = bool(raw.get("should_replan"))
        if not should_replan:
            should_replan = verdict in {"partial", "fail", "unknown"}

        should_ask_user = bool(raw.get("should_ask_user"))
        if not should_ask_user:
            should_ask_user = self._text_requests_user(phase_payload.get("current_phase", "")) and any(
                token in phase_payload.get("current_phase", "") for token in ("安全", "关键", "外部依赖")
            )

        # Strict anti-water gate: no evidence => cannot pass.
        if verdict == "pass":
            has_usable_artifact = any(
                bool(item.get("usable") or item.get("exists"))
                for item in artifact_check
                if isinstance(item, dict)
            )
            has_nonempty_evidence = any(
                str(item.get("note") if isinstance(item, dict) else item).strip()
                for item in evidence
            )
            if not (has_usable_artifact or has_nonempty_evidence):
                verdict = "partial"
                should_replan = True
                remaining_gaps = ["缺少可核验证据，禁止直接判定通过"] + remaining_gaps

        return KairosVerificationResult(
            attempt_id=attempt_id,
            verdict=verdict,
            evidence=evidence,
            artifact_check=artifact_check,
            goal_progress=goal_progress,
            remaining_gaps=remaining_gaps,
            next_best_action=next_best_action,
            should_replan=should_replan,
            should_ask_user=should_ask_user,
        )

    async def replan_from_failure(
        self,
        *,
        work_item: DocumentReadResult,
        verification_result: dict[str, Any] | KairosVerificationResult,
        available_actions: list[str] | None = None,
        understanding: KairosUnderstandingResult | None = None,
    ) -> KairosReplanResult:
        system_prompt = self._prompt_config.replan_system
        skill_context = self._build_skill_context()
        if isinstance(verification_result, KairosVerificationResult):
            verification_payload: dict[str, Any] = verification_result.__dict__
        else:
            verification_payload = dict(verification_result or {})
        understanding_payload = (
            understanding.__dict__
            if isinstance(understanding, KairosUnderstandingResult)
            else {}
        )
        user_prompt = json.dumps(
            {
                "work_item": work_item.__dict__,
                "understanding": understanding_payload,
                "verification": verification_payload,
                "available_actions": list(available_actions or sorted(ALLOWED_ACTION_KINDS)),
                **skill_context,
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
        phase_payload = self._normalize_phase_payload(raw)
        if not raw.get("replan_reason"):
            raw["replan_reason"] = self._first_line(phase_payload.get("current_phase", ""), default="verification_failed")
        if not raw.get("root_cause_hypothesis"):
            raw["root_cause_hypothesis"] = phase_payload.get("current_phase") or "insufficient evidence or failed verification"
        if not raw.get("revised_steps"):
            phase_step = self._compose_step_from_phase(
                phase_payload=phase_payload,
                default_step_id=work_item.current_step or "replan-step-1",
                candidate_actions=available_actions,
                skill_context=skill_context,
            )
            if phase_step is not None:
                raw["revised_steps"] = [phase_step]
        raw.setdefault("retryable", phase_payload.get("should_stop") is not True)
        raw.setdefault("retry_budget_cost", 1)
        escalate_to_user = self._text_requests_user(phase_payload.get("current_phase", "") + "\n" + phase_payload.get("next_phase", ""))
        raw.setdefault("escalate_to_user", escalate_to_user)
        raw.setdefault(
            "user_question",
            self._first_line(phase_payload.get("next_phase", ""), default=None) if raw.get("escalate_to_user") else None,
        )
        return KairosReplanResult(**raw)

    async def plan_follow_up_action(
        self,
        *,
        workflow_id: str,
        workflow_status: str,
        current_stage: str | None,
        blocked_reason: str | None,
        completed_task_ids: list[str],
        required_artifacts: list[dict[str, Any]],
        verification_result: dict[str, Any],
        tracked_tasks: list[dict[str, Any]],
        default_follow_up_description: str,
    ) -> dict[str, Any]:
        system_prompt = self._prompt_config.follow_up_system
        user_prompt = json.dumps(
            {
                "workflow_id": workflow_id,
                "workflow_status": workflow_status,
                "current_stage": current_stage,
                "blocked_reason": blocked_reason,
                "completed_task_ids": completed_task_ids,
                "required_artifacts": required_artifacts,
                "verification_result": verification_result,
                "tracked_tasks": tracked_tasks,
                "default_follow_up_description": default_follow_up_description,
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
        action = str(raw.get("action") or "sleep").strip().lower()
        if action not in {"create_follow_up", "ask_user", "sleep"}:
            phase_payload = self._normalize_phase_payload(raw)
            phase_text = f"{phase_payload.get('current_phase', '')}\n{phase_payload.get('next_phase', '')}".lower()
            if phase_payload.get("should_stop") is True:
                action = "sleep"
            elif self._text_requests_user(phase_text):
                action = "ask_user"
            else:
                action = "create_follow_up"
        if action not in {"create_follow_up", "ask_user", "sleep"}:
            action = "sleep"
        phase_payload = self._normalize_phase_payload(raw)
        reason = raw.get("reason") or self._first_line(phase_payload.get("current_phase", ""), default="llm_follow_up")
        description = raw.get("description") or self._first_line(
            phase_payload.get("next_phase", ""),
            default=default_follow_up_description,
        )
        message = raw.get("message")
        if action == "ask_user" and not str(message or "").strip():
            message = self._first_line(phase_payload.get("next_phase", ""), default="缺少安全关键输入，请补充")
        return {
            "action": action,
            "reason": reason,
            "description": description,
            "message": message,
        }

    async def _complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        try:
            response = await litellm.acompletion(
                model=self._model,
                api_key=self._api_key,
                api_base=self._api_base,
                extra_body=self._extra_body,
                temperature=0.1,
                timeout=self._timeout_seconds,
                max_retries=self._max_retries,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            text = self._extract_completion_text(response) or "{}"
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("completion JSON must be an object")
            return parsed
        except Exception:
            response = await litellm.acompletion(
                model=self._model,
                api_key=self._api_key,
                api_base=self._api_base,
                extra_body=self._extra_body,
                temperature=0.1,
                timeout=self._timeout_seconds,
                max_retries=self._max_retries,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt + " 输出必须包含一个 JSON 对象，可放在 markdown code fence 中。",
                    },
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = self._extract_completion_text(response) or "{}"
            try:
                return self._extract_json_object(text)
            except Exception:
                return self._extract_phase_payload_from_text(text)

    def _extract_completion_text(self, response: Any) -> str:
        try:
            message = response.choices[0].message
        except Exception:
            message = None

        if message is not None:
            for attr in ("content", "reasoning_content"):
                text = self._normalize_completion_field(getattr(message, attr, None))
                if text.strip():
                    return text

        if hasattr(response, "model_dump"):
            try:
                dump = response.model_dump()
                choices = dump.get("choices", []) if isinstance(dump, dict) else []
                if choices and isinstance(choices[0], dict):
                    message_obj = choices[0].get("message", {})
                    if isinstance(message_obj, dict):
                        for key in ("content", "reasoning_content"):
                            text = self._normalize_completion_field(message_obj.get(key))
                            if text.strip():
                                return text
            except Exception:
                pass

        return ""

    def _normalize_completion_field(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
                        continue
                parts.append(str(item))
            return "".join(parts)
        return str(value)

    def _extract_json_object(self, text: str) -> dict[str, Any]:
        fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text)
        if fenced:
            return json.loads(fenced.group(1))
        direct = re.search(r"(\{[\s\S]*\})", text)
        if direct:
            return json.loads(direct.group(1))
        raise ValueError("No JSON object found in completion output")

    def _sanitize_action_payload(self, raw: dict[str, Any]) -> KairosActionPayload:
        action_kind = raw.get("action_kind")
        if action_kind not in ALLOWED_ACTION_KINDS:
            action_kind = "ask_user"
        payload = {
            "action_kind": action_kind,
            "target_doc": raw.get("target_doc"),
            "section_updates": list(raw.get("section_updates", [])),
            "rationale": raw.get("rationale"),
            "task_type": raw.get("task_type"),
            "description": raw.get("description"),
            "command_template_id": raw.get("command_template_id"),
            "args": dict(raw.get("args", {})),
            "expected_artifacts": list(raw.get("expected_artifacts", [])),
            "timeout_hint": raw.get("timeout_hint"),
            "question": raw.get("question"),
            "why_blocked": raw.get("why_blocked"),
            "choices": list(raw.get("choices", [])),
            "brief": raw.get("brief"),
            "artifact_summary": list(raw.get("artifact_summary", [])),
            "next_recommendation": raw.get("next_recommendation"),
        }
        if action_kind != "spawn_dex_task":
            payload["command_template_id"] = None
        if action_kind not in {"spawn_dex_task", "agent_execute"}:
            payload["args"] = {}
        return KairosActionPayload(**payload)

    def _sanitize_plan(self, raw: dict[str, Any]) -> None:
        raw["steps"] = list(raw.get("steps", []))
        for step in raw["steps"]:
            action_kind = step.get("action_kind")
            if action_kind not in ALLOWED_ACTION_KINDS:
                step["action_kind"] = "ask_user"
        raw["stop_conditions"] = list(raw.get("stop_conditions", []))
        raw["ask_user_if"] = list(raw.get("ask_user_if", []))
        raw["completion_definition"] = list(raw.get("completion_definition", []))
