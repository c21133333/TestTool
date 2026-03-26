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
        required_pairs: list[dict[str, str]] | None = None,
        enforce_required_pairs: bool = False,
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
                required_pairs=required_pairs or [],
                enforce_required_pairs=enforce_required_pairs,
            ),
        )
        self.last_call_trace = dict(trace or {})
        normalized = self._normalize_payload(payload)
        points = normalized.get("test_points")
        warnings = normalized.get("warnings")
        if not isinstance(points, list):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的测试点结构无效。")
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
            "The supported categories are happy_path, negative_path, boundary_path, auth, idempotent, pagination, assertion_hardening. "
            "The title must use the format 'METHOD /path category'. "
            "The 'reason' field and every item in 'warnings' must be written in Simplified Chinese. "
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
        required_pairs: list[dict[str, str]],
        enforce_required_pairs: bool,
    ) -> str:
        generation_mode = "grounded" if has_rule_baseline else "draft_without_rule_baseline"
        hints = prompt_hints.strip() or "请优先关注最有回归价值的测试点。"
        required_lines = [f'- {item["endpoint"]} -> {item["category"]}' for item in required_pairs if item.get("endpoint") and item.get("category")]
        required_block = "\n".join(required_lines) if required_lines else "（无）"
        required_clause = (
            "5. 对于下面列出的每个必补 endpoint/category 对，除非规则基线中已经存在对应测试点，否则必须至少补出 1 条测试点。\n"
            if enforce_required_pairs and required_lines
            else ""
        )
        return (
            "请结合现有接口上下文生成测试点。\n\n"
            "要求：\n"
            "1. 如果已经存在规则基线，请保留已有 grounded points，只在必要时优化 reason、风险信号和建议草稿数。\n"
            "2. 如果没有规则基线，最多生成 3 条草案测试点，并明确给出“可信度较低”的中文告警。\n"
            "3. 避免重复测试点。\n"
            "4. 除非有充分依据，否则 covered_by_existing_cases 必须与已有上下文保持一致。\n"
            f"{required_clause}"
            "5. 所有 reason 和 warnings 必须使用简体中文。\n\n"
            "返回示例：\n"
            '{'
            '"test_points":['
            '{"id":"tp_get_profile_happy_path","title":"GET /profile happy_path","category":"happy_path","risk_level":"high","reason":"主流程读取用户资料是核心链路，建议保持稳定覆盖。","covered_by_existing_cases":true,"suggested_case_count":1,"confidence":0.93}'
            '],'
            '"warnings":["当前输出仅为草案建议，可信度较低，请在生成草稿前人工复核。"]'
            '}\n\n'
            f"生成模式：\n{generation_mode}\n\n"
            f"附加提示：\n{hints}\n\n"
            "必须补齐的 endpoint/category 对：\n"
            f"{required_block}\n\n"
            "规则基线测试点：\n"
            f"{json.dumps(baseline_points, ensure_ascii=False, indent=2)}\n\n"
            "Markdown 文档：\n"
            f"{markdown_text or '(empty)'}\n\n"
            "项目上下文：\n"
            f"{json.dumps(input_snapshot, ensure_ascii=False, indent=2)}"
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._looks_like_payload(payload):
            return payload
        content = self._extract_message_content(payload)
        parsed = self._load_json_payload(content)
        if not self._looks_like_payload(parsed):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的测试点结构无效。")
        return parsed

    def _looks_like_payload(self, payload: dict[str, Any]) -> bool:
        return isinstance(payload, dict) and "test_points" in payload

    def _extract_message_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 响应中缺少 choices。")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 响应中缺少有效 message。")
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
            return "".join(text_parts).strip()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 响应内容为空。")

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
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI 返回的 JSON 无法解析：{exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的 JSON 顶层必须是对象。")
        return parsed
