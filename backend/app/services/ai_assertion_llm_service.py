from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from backend.app.services.ai_client_service import AiClientService
from backend.app.services.ai_provider_registry import AiGenerationRuntimeConfig, AiProviderRegistry


class AiAssertionLlmService:
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

    def analyze_assertions(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        input_snapshot: dict[str, Any],
        baseline_suggestions: list[dict[str, Any]],
        existing_assertions: list[dict[str, Any]],
        has_success_sample: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        payload, trace = self._ai_client.generate_json(
            runtime=runtime,
            system_prompt=self._build_system_prompt(has_success_sample=has_success_sample),
            user_prompt=self._build_user_prompt(
                input_snapshot=input_snapshot,
                baseline_suggestions=baseline_suggestions,
                existing_assertions=existing_assertions,
                has_success_sample=has_success_sample,
            ),
        )
        self.last_call_trace = dict(trace or {})
        normalized = self._normalize_payload(payload)
        suggestions = normalized.get("suggested_assertions")
        warnings = normalized.get("warnings")
        if not isinstance(suggestions, list):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的断言建议结构不合法。")
        return [item for item in suggestions if isinstance(item, dict)], [str(item) for item in warnings or []]

    def _build_system_prompt(self, *, has_success_sample: bool) -> str:
        grounding_clause = (
            "当前存在最近一次成功执行样本，请优先基于真实响应生成可直接应用的断言建议。"
            if has_success_sample
            else "当前没有最近一次成功执行样本，可以基于 method、url、headers、body、request_shape、response_shape、recent_failure_sample 生成草案断言，但不要假装这些断言已经被真实响应验证。"
        )
        return (
            "你是 API 断言补全助手。"
            f"{grounding_clause}"
            "必须只返回 JSON，不要 markdown，不要额外解释。"
            "不要虚构上下文中不存在的业务字段。"
            "顶层对象必须包含 suggested_assertions 和 warnings。"
            "suggested_assertions 的每一项必须包含 type、operator、expected、enabled、reason、confidence，必要时可包含 path 或 header。"
            "type 只允许使用机器值：status_code、json_path。"
            "operator 只允许使用机器值：==、contains、not_null。"
            "confidence 必须是 0 到 1 之间的小数。"
            "reason 和 warnings 必须使用简体中文。"
            "优先输出稳定、可执行、低歧义的断言建议，并避免与 existing assertions 重复。"
        )

    def _build_user_prompt(
        self,
        *,
        input_snapshot: dict[str, Any],
        baseline_suggestions: list[dict[str, Any]],
        existing_assertions: list[dict[str, Any]],
        has_success_sample: bool,
    ) -> str:
        serialized_snapshot = json.dumps(input_snapshot, ensure_ascii=False, indent=2)
        serialized_baseline = json.dumps(baseline_suggestions, ensure_ascii=False, indent=2)
        serialized_existing = json.dumps(existing_assertions, ensure_ascii=False, indent=2)
        generation_mode = "grounded" if has_success_sample else "draft_without_success_sample"
        return (
            "请根据下面的 case 上下文生成断言建议。\n\n"
            "要求：\n"
            "1. 不要删除 deterministic baseline 中已经合理的建议，可以重写 reason 或补充更优建议。\n"
            "2. 避免与 existing assertions 重复。\n"
            "3. 建议总数尽量控制在 6 条以内。\n"
            "4. 如果没有最近一次成功执行样本，请继续生成可人工确认的草案断言，并在 warnings 中明确说明“以下建议未基于真实成功响应验证，请人工确认后再应用”。\n"
            "5. 如果信息不足，warnings 返回中文提醒；否则返回空数组。\n\n"
            "响应示例：\n"
            '{'
            '"suggested_assertions":['
            '{"type":"status_code","operator":"==","expected":200,"enabled":true,"reason":"建议固定成功响应状态码","confidence":0.96},'
            '{"type":"json_path","path":"$.code","operator":"==","expected":0,"enabled":true,"reason":"建议校验稳定业务码字段","confidence":0.9}'
            '],'
            '"warnings":["如接口响应字段波动较大，请人工确认后再应用"]'
            '}\n\n'
            f"generation mode:\n{generation_mode}\n\n"
            "existing assertions:\n"
            f"{serialized_existing}\n\n"
            "deterministic baseline suggestions:\n"
            f"{serialized_baseline}\n\n"
            "case context:\n"
            f"{serialized_snapshot}"
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._looks_like_assertion_payload(payload):
            return payload
        content = self._extract_message_content(payload)
        parsed = self._load_json_payload(content)
        if not self._looks_like_assertion_payload(parsed):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的断言建议结构不合法。")
        return parsed

    def _looks_like_assertion_payload(self, payload: dict[str, Any]) -> bool:
        return isinstance(payload, dict) and "suggested_assertions" in payload

    def _extract_message_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 响应中缺少 choices。")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 响应中缺少合法的 message。")
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
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI 没有返回合法 JSON：{exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的 JSON 顶层必须是对象。")
        return parsed
