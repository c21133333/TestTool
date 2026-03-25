from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from backend.app.services.ai_client_service import AiClientService
from backend.app.services.ai_provider_registry import AiGenerationRuntimeConfig, AiProviderRegistry


class AiTestDataLlmService:
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

    def analyze_variants(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        input_snapshot: dict[str, Any],
        baseline_variants: list[dict[str, Any]],
        has_rule_baseline: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        payload, trace = self._ai_client.generate_json(
            runtime=runtime,
            system_prompt=self._build_system_prompt(has_rule_baseline=has_rule_baseline),
            user_prompt=self._build_user_prompt(
                input_snapshot=input_snapshot,
                baseline_variants=baseline_variants,
                has_rule_baseline=has_rule_baseline,
            ),
        )
        self.last_call_trace = dict(trace or {})
        normalized = self._normalize_payload(payload)
        variants = normalized.get("data_variants")
        warnings = normalized.get("warnings")
        if not isinstance(variants, list):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的测试数据结构不合法。")
        return [item for item in variants if isinstance(item, dict)], [str(item) for item in warnings or []]

    def _build_system_prompt(self, *, has_rule_baseline: bool) -> str:
        baseline_clause = (
            "当前已有 deterministic baseline，请基于现有 baseline 做增强，不要删除合理项。"
            if has_rule_baseline
            else "当前没有 deterministic baseline，请基于 method、url、body_json、request_shape、recent_success_sample、recent_failure_sample 生成少量可人工确认的测试数据草案，但不要假装它们已被真实执行验证。"
        )
        return (
            "你是 API 测试数据设计助手。"
            f"{baseline_clause}"
            "必须只返回 JSON，不要 markdown，不要额外解释。"
            "不要虚构上下文中不存在的字段。"
            "顶层对象必须包含 data_variants 和 warnings。"
            "data_variants 每一项必须包含 variant_id、name、category、payload_patch、target_fields、reason、suggested_assertions、confidence。"
            "category 只允许使用机器值：happy_path、negative_path、boundary_path、auth。"
            "confidence 必须是 0 到 1 之间的小数。"
            "reason 和 warnings 必须使用简体中文。"
            "suggested_assertions 可以为空数组，但如果返回断言建议，请使用现有断言结构。"
            "生成结果要可执行、低歧义，并避免明显重复。"
        )

    def _build_user_prompt(
        self,
        *,
        input_snapshot: dict[str, Any],
        baseline_variants: list[dict[str, Any]],
        has_rule_baseline: bool,
    ) -> str:
        generation_mode = "grounded" if has_rule_baseline else "draft_without_rule_baseline"
        return (
            "请根据下面的 case 上下文生成测试数据变体。\n\n"
            "要求：\n"
            "1. 如果 baseline 已经给出合理变体，可以补强 reason、suggested_assertions，或补充少量新变体。\n"
            "2. 如果没有 baseline，也要给出 1 到 3 个草案变体，并在 warnings 中明确提示“以下测试数据建议未基于规则保底生成，可信度较低，请人工确认后再应用”。\n"
            "3. 变体总数尽量控制在 5 个以内。\n"
            "4. payload_patch 必须是完整对象，target_fields 必须对应被修改字段路径。\n\n"
            "响应示例：\n"
            '{'
            '"data_variants":['
            '{"variant_id":"tv_username_empty","name":"empty_string","category":"boundary_path","payload_patch":{"username":""},"target_fields":["username"],"reason":"建议验证用户名为空时的边界处理","suggested_assertions":[{"type":"status_code","operator":"==","expected":400,"enabled":true}],"confidence":0.88}'
            '],'
            '"warnings":["如接口字段存在环境差异，请人工确认后再应用"]'
            '}\n\n'
            f"generation mode:\n{generation_mode}\n\n"
            "deterministic baseline variants:\n"
            f"{json.dumps(baseline_variants, ensure_ascii=False, indent=2)}\n\n"
            "case context:\n"
            f"{json.dumps(input_snapshot, ensure_ascii=False, indent=2)}"
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._looks_like_payload(payload):
            return payload
        content = self._extract_message_content(payload)
        parsed = self._load_json_payload(content)
        if not self._looks_like_payload(parsed):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的测试数据结构不合法。")
        return parsed

    def _looks_like_payload(self, payload: dict[str, Any]) -> bool:
        return isinstance(payload, dict) and "data_variants" in payload

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
