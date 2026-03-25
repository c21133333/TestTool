from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from backend.app.services.ai_client_service import AiClientService
from backend.app.services.ai_provider_registry import AiGenerationRuntimeConfig, AiProviderRegistry


class AiReportSummaryLlmService:
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

    def analyze_summary(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        input_snapshot: dict[str, Any],
        baseline_result: dict[str, Any],
        has_rule_baseline: bool,
    ) -> tuple[dict[str, Any], list[str]]:
        payload, trace = self._ai_client.generate_json(
            runtime=runtime,
            system_prompt=self._build_system_prompt(has_rule_baseline=has_rule_baseline),
            user_prompt=self._build_user_prompt(
                input_snapshot=input_snapshot,
                baseline_result=baseline_result,
                has_rule_baseline=has_rule_baseline,
            ),
        )
        self.last_call_trace = dict(trace or {})
        normalized = self._normalize_payload(payload)
        result = normalized.get("result")
        warnings = normalized.get("warnings")
        if not isinstance(result, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的报告总结结构不合法。")
        return result, [str(item) for item in warnings or []]

    def _build_system_prompt(self, *, has_rule_baseline: bool) -> str:
        baseline_clause = (
            "当前规则基线已经能提炼报告摘要，请在保持事实准确的前提下增强表达和行动建议。"
            if has_rule_baseline
            else "当前规则基线信号较弱，请结合 execution summary、metadata、recent_suite_execution 做保守总结，不要编造上下文中不存在的事实。"
        )
        return (
            "你是 API 执行报告总结助手。"
            f"{baseline_clause}"
            "必须只返回 JSON，不要 markdown，不要额外解释。"
            "顶层对象必须包含 result 和 warnings。"
            "result 必须包含 executive_summary、risk_summary、top_failures、recommended_actions。"
            "top_failures 必须是对象数组，每项包含 category 和 count。"
            "recommended_actions 必须是字符串数组。"
            "executive_summary、risk_summary、recommended_actions、warnings 必须使用简体中文。"
            "如果上下文不足，请在 warnings 中明确提示“当前总结可信度较低，请结合原始报告人工确认”。"
        )

    def _build_user_prompt(
        self,
        *,
        input_snapshot: dict[str, Any],
        baseline_result: dict[str, Any],
        has_rule_baseline: bool,
    ) -> str:
        summary_mode = "grounded" if has_rule_baseline else "weak_signal_requires_caution"
        return (
            "请根据下面的报告上下文生成业务可读的执行总结。\n\n"
            "要求：\n"
            "1. 可以参考 baseline summary，但不要照抄。\n"
            "2. recommended_actions 控制在 2 到 4 条。\n"
            "3. 如果 evidence 很弱，请在 warnings 中明确加入“当前总结可信度较低，请结合原始报告人工确认”。\n"
            "4. 不要虚构失败分类、数量或不存在的回归结论。\n\n"
            "响应示例：\n"
            '{'
            '"result":{"executive_summary":"本次执行共 12 条，成功 9 条，失败 3 条，失败主要集中在 timeout。","risk_summary":"timeout 风险明显，建议先排查下游稳定性后再判断是否为真实回归。","top_failures":[{"category":"timeout","count":3}],"recommended_actions":["检查下游超时与网关时延","对比最近一次同套件成功执行"]},'
            '"warnings":["当前总结可信度较低，请结合原始报告人工确认"]'
            '}\n\n'
            f"summary mode:\n{summary_mode}\n\n"
            "baseline summary:\n"
            f"{json.dumps(baseline_result, ensure_ascii=False, indent=2)}\n\n"
            "report context:\n"
            f"{json.dumps(input_snapshot, ensure_ascii=False, indent=2)}"
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._looks_like_payload(payload):
            return payload
        content = self._extract_message_content(payload)
        parsed = self._load_json_payload(content)
        if not self._looks_like_payload(parsed):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的报告总结结构不合法。")
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
