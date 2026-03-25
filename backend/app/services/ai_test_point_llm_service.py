from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from backend.app.services.ai_client_service import AiClientService
from backend.app.services.ai_provider_registry import AiGenerationRuntimeConfig, AiProviderRegistry


class AiTestPointLlmService:
    def __init__(
        self,
        *,
        ai_client: AiClientService | None = None,
        provider_registry: AiProviderRegistry | None = None,
    ) -> None:
        self._ai_client = ai_client or AiClientService()
        self._provider_registry = provider_registry or AiProviderRegistry()
        self.last_call_trace: dict[str, Any] = {"call_mode": "deterministic", "trace_json": {}}

    def resolve_runtime(self) -> AiGenerationRuntimeConfig:
        return self._provider_registry.resolve_runtime()

    def analyze_points(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        input_snapshot: dict[str, Any],
        baseline_points: list[dict[str, Any]],
        markdown_text: str,
        prompt_hints: str,
        has_rule_baseline: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        payload, trace = self._ai_client.generate_json(
            runtime=runtime,
            system_prompt=self._build_system_prompt(has_rule_baseline=has_rule_baseline),
            user_prompt=self._build_user_prompt(
                input_snapshot=input_snapshot,
                baseline_points=baseline_points,
                markdown_text=markdown_text,
                prompt_hints=prompt_hints,
                has_rule_baseline=has_rule_baseline,
            ),
        )
        self.last_call_trace = dict(trace or {})
        normalized = self._normalize_payload(payload)
        points = normalized.get("test_points")
        warnings = normalized.get("warnings")
        if not isinstance(points, list):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI returned invalid test point payload.")
        return [item for item in points if isinstance(item, dict)], [str(item) for item in warnings or []]

    def _build_system_prompt(self, *, has_rule_baseline: bool) -> str:
        baseline_clause = (
            "A deterministic baseline already exists. Preserve grounded points and only refine or add a few obviously useful points."
            if has_rule_baseline
            else "No deterministic baseline exists. Generate only a small draft set and clearly warn that confidence is lower."
        )
        return (
            "You design API test points for an existing test platform. "
            f"{baseline_clause} "
            "Return JSON only. No markdown fences. No commentary. "
            "Do not invent undocumented business contracts. "
            "The top-level object must contain keys 'test_points' and 'warnings'. "
            "Each test point must include: id, title, category, risk_level, reason, covered_by_existing_cases, suggested_case_count, confidence. "
            "The supported categories are happy_path, negative_path, boundary_path. "
            "The title must use the format 'METHOD /path category'. "
            "confidence must be a number between 0 and 1."
        )

    def _build_user_prompt(
        self,
        *,
        input_snapshot: dict[str, Any],
        baseline_points: list[dict[str, Any]],
        markdown_text: str,
        prompt_hints: str,
        has_rule_baseline: bool,
    ) -> str:
        generation_mode = "grounded" if has_rule_baseline else "draft_without_rule_baseline"
        hints = prompt_hints.strip() or "Focus on the most useful regression-oriented points."
        return (
            "Review the existing API context and produce test points.\n\n"
            "Requirements:\n"
            "1. If a baseline already exists, keep it grounded and improve reason, priority signal, and suggested case count where helpful.\n"
            "2. If no baseline exists, generate at most 3 draft points and include a warning that the output is low confidence.\n"
            "3. Avoid duplicate points.\n"
            "4. Keep covered_by_existing_cases aligned with the grounded context unless there is strong contrary evidence.\n\n"
            "Response example:\n"
            '{'
            '"test_points":['
            '{"id":"tp_get_profile_happy_path","title":"GET /profile happy_path","category":"happy_path","risk_level":"high","reason":"Happy path should remain stable for the main profile read flow.","covered_by_existing_cases":true,"suggested_case_count":1,"confidence":0.93}'
            '],'
            '"warnings":["Low confidence draft output. Please review before generating drafts."]'
            '}\n\n'
            f"generation mode:\n{generation_mode}\n\n"
            f"additional hints:\n{hints}\n\n"
            "deterministic baseline points:\n"
            f"{json.dumps(baseline_points, ensure_ascii=False, indent=2)}\n\n"
            "markdown text:\n"
            f"{markdown_text or '(empty)'}\n\n"
            "project context:\n"
            f"{json.dumps(input_snapshot, ensure_ascii=False, indent=2)}"
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._looks_like_payload(payload):
            return payload
        content = self._extract_message_content(payload)
        parsed = self._load_json_payload(content)
        if not self._looks_like_payload(parsed):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI returned invalid test point payload.")
        return parsed

    def _looks_like_payload(self, payload: dict[str, Any]) -> bool:
        return isinstance(payload, dict) and "test_points" in payload

    def _extract_message_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI response did not contain choices.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI response did not contain a valid message.")
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
            return "".join(text_parts).strip()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI response content was empty.")

    def _load_json_payload(self, content: str) -> dict[str, Any]:
        normalized = content.strip()
        if normalized.startswith("```"):
            normalized = normalized.strip("`")
            if normalized.startswith("json"):
                normalized = normalized[4:]
            normalized = normalized.strip()
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI did not return valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI response JSON must be an object.")
        return parsed
