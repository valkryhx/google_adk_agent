from __future__ import annotations

import json
import re
import uuid
from typing import Any

import litellm

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
    "wait_for_artifact",
    "summarize_progress",
    "ask_user",
    "sleep",
}


class KairosPlanner:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        api_base: str,
        extra_body: dict[str, Any] | None = None,
        timeout_seconds: int = 60,
        max_retries: int = 1,
    ):
        self._model = model
        self._api_key = api_key
        self._api_base = api_base
        self._extra_body = extra_body or {}
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    async def draft_requirement_understanding(self, item: DocumentReadResult) -> KairosUnderstandingResult:
        system_prompt = (
            "你是 Kairos 的 requirement understanding planner。"
            "请把用户需求转成结构化理解结果，必须输出 JSON，且字段只允许："
            "goal,constraints,assumptions,missing_info,success_criteria,current_artifacts,risk_flags,recommended_mode。"
        )
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
        return KairosUnderstandingResult(**raw)

    async def build_execution_plan(
        self,
        item: DocumentReadResult,
        understanding: KairosUnderstandingResult,
        *,
        candidate_actions: list[str],
    ) -> KairosExecutionPlan:
        system_prompt = (
            "你是 Kairos 的 execution planner。"
            "请基于任务理解结果，输出结构化执行计划 JSON。"
            "steps[].action_kind 只能来自这个集合："
            f"{sorted(ALLOWED_ACTION_KINDS)}。"
        )
        user_prompt = json.dumps(
            {
                "work_id": item.work_id,
                "goal": item.goal,
                "current_step": item.current_step,
                "understanding": understanding.__dict__,
                "candidate_actions": candidate_actions,
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
        raw.setdefault("plan_id", f"plan-{uuid.uuid4().hex[:8]}")
        raw.setdefault("work_id", item.work_id)
        self._sanitize_plan(raw)
        return KairosExecutionPlan(**raw)

    async def build_action_payload(
        self,
        *,
        work_item: DocumentReadResult,
        step: dict[str, Any],
    ) -> KairosActionPayload:
        system_prompt = (
            "你是 Kairos 的 action payload generator。"
            "请为给定 step 输出受限 JSON payload。"
            "只能生成与 action_kind 对应的字段，禁止输出任意 shell 命令。"
            "如果是 spawn_dex_task，只允许 command_template_id 使用安全模板标识，例如 draft_requirements_doc、generate_todo_app、run_smoke_check、summarize_delivery。"
        )
        user_prompt = json.dumps(
            {
                "work_item": work_item.__dict__,
                "step": step,
                "allowed_action_kinds": sorted(ALLOWED_ACTION_KINDS),
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
        system_prompt = (
            "你是 Kairos 的 document patch generator。"
            "请输出 section-level JSON patch，只能更新已知工作文档 section。"
            "section_updates[].section 只能来自 Goal, Current Status, Current Step, Steps, Expected Artifacts, Blockers, Verification, Replan Notes, Spawned Work。"
        )
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
        system_prompt = (
            "你是 Kairos 的 design/codegen brief generator。"
            "请输出结构化 JSON brief，用于受控 dex/codegen 执行。"
            "不要输出自由 shell 命令。"
            "如果 action_kind=spawn_dex_task，需要提供 description、command_template_id、args、expected_artifacts。"
        )
        user_prompt = json.dumps(
            {
                "work_item": work_item.__dict__,
                "step": step,
                "allowed_templates": [
                    "draft_requirements_doc",
                    "generate_design_brief",
                    "generate_codegen_brief",
                    "run_smoke_check",
                    "summarize_delivery",
                ],
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
        system_prompt = (
            "你是 Kairos 的 verification engine。"
            "请输出结构化 verification JSON，字段只允许："
            "attempt_id,verdict,evidence,artifact_check,goal_progress,remaining_gaps,next_best_action,should_replan,should_ask_user。"
        )
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
        system_prompt = (
            "你是 Kairos 的 replanner。"
            "请基于 verification 失败结果生成结构化 replan JSON，字段只允许："
            "replan_reason,root_cause_hypothesis,invalidated_assumptions,revised_steps,retryable,retry_budget_cost,escalate_to_user,user_question。"
        )
        user_prompt = json.dumps(
            {
                "work_item": work_item.__dict__,
                "understanding": understanding.__dict__,
                "verification": verification.__dict__,
            },
            ensure_ascii=False,
        )
        raw = await self._complete_json(system_prompt, user_prompt)
        return KairosReplanResult(**raw)

    async def _complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        try:
            response = await litellm.acompletion(
                model=self._model,
                api_key=self._api_key,
                api_base=self._api_base,
                extra_body=self._extra_body or None,
                temperature=0.1,
                timeout=self._timeout_seconds,
                max_retries=self._max_retries,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            return json.loads(text)
        except Exception:
            response = await litellm.acompletion(
                model=self._model,
                api_key=self._api_key,
                api_base=self._api_base,
                extra_body=self._extra_body or None,
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
            text = response.choices[0].message.content or "{}"
            return self._extract_json_object(text)

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
