from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from backend.app.services.ai_client_service import AiClientService
from backend.app.services.ai_provider_registry import AiGenerationRuntimeConfig, AiProviderRegistry


class AiDiagnosisLlmService:
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

    def analyze_diagnosis(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        input_snapshot: dict[str, Any],
        baseline_result: dict[str, Any],
        has_clear_signal: bool,
    ) -> tuple[dict[str, Any], list[str]]:
        payload, trace = self._ai_client.generate_json(
            runtime=runtime,
            system_prompt=self._build_system_prompt(has_clear_signal=has_clear_signal),
            user_prompt=self._build_user_prompt(
                input_snapshot=input_snapshot,
                baseline_result=baseline_result,
                has_clear_signal=has_clear_signal,
            ),
        )
        self.last_call_trace = dict(trace or {})
        normalized = self._normalize_payload(payload)
        result = normalized.get("result")
        warnings = normalized.get("warnings")
        if not isinstance(result, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的诊断结构不合法。")
        return result, [str(item) for item in warnings or []]

    def _build_system_prompt(self, *, has_clear_signal: bool) -> str:
        baseline_clause = (
            "当前规则基线已经给出较强信号，请优先在基线附近做增强，不要为了求新而随意改类。"
            if has_clear_signal
            else "当前规则基线信号较弱，请结合 execution summary、first_failure、retry_history、items 补充更合理的诊断，但不要假装结论已经被人工确认。"
        )
        return (
            "你是 API 执行失败诊断助手。"
            f"{baseline_clause}"
            "必须只返回 JSON，不要 markdown，不要额外解释。"
            "顶层对象必须包含 result 和 warnings。"
            "result 必须包含 diagnosis_category、root_cause_hypothesis、confidence、next_actions。"
            "diagnosis_category 只允许使用机器值：dependency_timeout、auth_issue、mock_mismatch、assertion_too_strict、environment_issue、test_data_issue、real_regression、unknown。"
            "confidence 必须是 0 到 1 之间的小数。"
            "next_actions 必须是字符串数组。"
            "root_cause_hypothesis、warnings、next_actions 必须使用简体中文。"
            "如果上下文不足，请保守输出并在 warnings 中明确提示低可信度。"
        )

    def _build_user_prompt(
        self,
        *,
        input_snapshot: dict[str, Any],
        baseline_result: dict[str, Any],
        has_clear_signal: bool,
    ) -> str:
        diagnosis_mode = "grounded" if has_clear_signal else "weak_signal_requires_caution"
        return (
            "请根据下面的执行上下文补充失败诊断。\n\n"
            "要求：\n"
            "1. 可以参考 baseline diagnosis，但不要机械复述。\n"
            "2. 如果 evidence 很弱，请在 warnings 中明确加入“当前诊断可信度较低，请结合原始执行详情人工确认”。\n"
            "3. next_actions 控制在 2 到 4 条。\n"
            "4. 不要输出上下文中不存在的外部系统名称或业务字段。\n\n"
            "响应示例：\n"
            '{'
            '"result":{"diagnosis_category":"dependency_timeout","root_cause_hypothesis":"下游依赖响应超时，导致当前执行在网关阶段失败。","confidence":0.84,"next_actions":["检查下游接口时延和超时配置","对比同时间窗其他执行是否出现相同故障"]},'
            '"warnings":["当前诊断可信度较低，请结合原始执行详情人工确认"]'
            '}\n\n'
            f"diagnosis mode:\n{diagnosis_mode}\n\n"
            "baseline diagnosis:\n"
            f"{json.dumps(baseline_result, ensure_ascii=False, indent=2)}\n\n"
            "execution context:\n"
            f"{json.dumps(input_snapshot, ensure_ascii=False, indent=2)}"
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._looks_like_payload(payload):
            return payload
        content = self._extract_message_content(payload)
        parsed = self._load_json_payload(content)
        if not self._looks_like_payload(parsed):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的诊断结构不合法。")
        return parsed

    def _looks_like_payload(self, payload: dict[str, Any]) -> bool:
        return isinstance(payload, dict) and "result" in payload

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
