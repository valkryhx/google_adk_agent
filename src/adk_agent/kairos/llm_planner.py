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
        if not str(raw.get("goal") or "").strip():
            raw["goal"] = item.goal
        return KairosUnderstandingResult(**raw)

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
        raw.setdefault("attempt_id", attempt_id)
        return KairosVerificationResult(**raw)

    async def replan_from_failure(
        self,
        *,
        work_item: DocumentReadResult,
        verification: KairosVerificationResult,
        understanding: KairosUnderstandingResult,
    ) -> KairosReplanResult:
        system_prompt = self._prompt_config.replan_system
        skill_context = self._build_skill_context()
        user_prompt = json.dumps(
            {
                "work_item": work_item.__dict__,
                "understanding": understanding.__dict__,
                "verification": verification.__dict__,
                **skill_context,
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
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
            action = "sleep"
        return {
            "action": action,
            "reason": raw.get("reason"),
            "description": raw.get("description"),
            "message": raw.get("message"),
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
            return self._extract_json_object(text)

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
