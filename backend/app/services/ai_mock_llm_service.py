from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from backend.app.services.ai_client_service import AiClientService
from backend.app.services.ai_provider_registry import AiGenerationRuntimeConfig, AiProviderRegistry


class AiMockLlmService:
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

    def analyze_templates(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        input_snapshot: dict[str, Any],
        baseline_templates: list[dict[str, Any]],
        has_rule_baseline: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        payload, trace = self._ai_client.generate_json(
            runtime=runtime,
            system_prompt=self._build_system_prompt(has_rule_baseline=has_rule_baseline),
            user_prompt=self._build_user_prompt(
                input_snapshot=input_snapshot,
                baseline_templates=baseline_templates,
                has_rule_baseline=has_rule_baseline,
            ),
        )
        self.last_call_trace = dict(trace or {})
        normalized = self._normalize_payload(payload)
        templates = normalized.get("mock_templates")
        warnings = normalized.get("warnings")
        if not isinstance(templates, list):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的 Mock 模板结构不合法。")
        return [item for item in templates if isinstance(item, dict)], [str(item) for item in warnings or []]

    def _build_system_prompt(self, *, has_rule_baseline: bool) -> str:
        baseline_clause = (
            "当前已有 deterministic baseline，请基于已有模板增强，而不是删掉合理模板。"
            if has_rule_baseline
            else "当前没有 deterministic baseline，请基于 method、url、response_shape、recent_failure_sample、metadata_json 生成少量可人工确认的 Mock 草案，但不要假装这些模板已通过真实流量验证。"
        )
        return (
            "你是 API Mock 模板设计助手。"
            f"{baseline_clause}"
            "必须只返回 JSON，不要 markdown，不要额外解释。"
            "不要虚构上下文中不存在的响应字段。"
            "顶层对象必须包含 mock_templates 和 warnings。"
            "mock_templates 每一项必须包含 template_id、scenario_name、status_code、response_template、mock_rules、reason、confidence。"
            "confidence 必须是 0 到 1 之间的小数。"
            "reason 和 warnings 必须使用简体中文。"
            "mock_rules 至少包含 method、path、status_code。"
            "模板要可执行、低歧义，并避免明显重复。"
        )

    def _build_user_prompt(
        self,
        *,
        input_snapshot: dict[str, Any],
        baseline_templates: list[dict[str, Any]],
        has_rule_baseline: bool,
    ) -> str:
        generation_mode = "grounded" if has_rule_baseline else "draft_without_rule_baseline"
        return (
            "请根据下面的 case 上下文生成 Mock 模板。\n\n"
            "要求：\n"
            "1. 如果已有 baseline 模板，可以补强文案或补充少量新模板。\n"
            "2. 如果没有 baseline，也要生成 1 到 3 个草案模板，并在 warnings 中明确提示“以下 Mock 建议未基于规则保底生成，可信度较低，请人工确认后再应用”。\n"
            "3. 模板总数尽量控制在 4 个以内。\n"
            "4. response_template 必须是对象，mock_rules 至少给出 method/path/status_code。\n\n"
            "响应示例：\n"
            '{'
            '"mock_templates":['
            '{"template_id":"mt_validation_error_post_orders","scenario_name":"validation_error","status_code":400,"response_template":{"code":40001,"message":"参数错误"},"mock_rules":[{"method":"POST","path":"/orders","status_code":400}],"reason":"建议覆盖常见参数校验失败返回","confidence":0.84}'
            '],'
            '"warnings":["如接口返回体高度动态，请人工确认后再应用"]'
            '}\n\n'
            f"generation mode:\n{generation_mode}\n\n"
            "deterministic baseline templates:\n"
            f"{json.dumps(baseline_templates, ensure_ascii=False, indent=2)}\n\n"
            "case context:\n"
            f"{json.dumps(input_snapshot, ensure_ascii=False, indent=2)}"
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._looks_like_payload(payload):
            return payload
        content = self._extract_message_content(payload)
        parsed = self._load_json_payload(content)
        if not self._looks_like_payload(parsed):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的 Mock 模板结构不合法。")
        return parsed

    def _looks_like_payload(self, payload: dict[str, Any]) -> bool:
        return isinstance(payload, dict) and "mock_templates" in payload

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
