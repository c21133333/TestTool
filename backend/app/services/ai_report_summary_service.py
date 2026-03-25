from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.app.services.ai_report_summary_llm_service import AiReportSummaryLlmService


class AiReportSummaryService:
    def __init__(
        self,
        *,
        llm_service: AiReportSummaryLlmService | None = None,
    ) -> None:
        self._llm_service = llm_service or AiReportSummaryLlmService()

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
        baseline_result = self._build_baseline_result(snapshot)
        has_rule_baseline = self._has_rule_baseline(snapshot)
        baseline_warnings = self._build_baseline_warnings(snapshot, has_rule_baseline=has_rule_baseline)

        result = dict(baseline_result)
        warnings = list(baseline_warnings)
        fallback_call_trace: dict[str, Any] | None = None

        try:
            runtime = self._llm_service.resolve_runtime()
            llm_result, llm_warnings = self._llm_service.analyze_summary(
                runtime=runtime,
                input_snapshot=snapshot,
                baseline_result=baseline_result,
                has_rule_baseline=has_rule_baseline,
            )
            result = self._merge_result(baseline_result=baseline_result, llm_result=llm_result)
            warnings = self._merge_warnings(
                baseline_warnings=baseline_warnings,
                llm_warnings=llm_warnings,
                has_rule_baseline=has_rule_baseline,
            )
        except HTTPException as exc:
            fallback_call_trace = self._build_fallback_call_trace(exc)
            warnings = self._merge_warnings(
                baseline_warnings=baseline_warnings,
                llm_warnings=[self._fallback_warning(exc)],
                has_rule_baseline=has_rule_baseline,
            )

        return {
            "result": result,
            "warnings": warnings,
            "call_trace": fallback_call_trace or self._llm_service.last_call_trace,
        }

    def _build_baseline_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        execution_summary = snapshot.get("execution_summary") if isinstance(snapshot.get("execution_summary"), dict) else {}
        metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
        recent_suite_execution = snapshot.get("recent_suite_execution") if isinstance(snapshot.get("recent_suite_execution"), dict) else {}

        total = int(execution_summary.get("total") or metadata.get("summary", {}).get("total") or 0)
        failed = int(execution_summary.get("ng") or metadata.get("summary", {}).get("ng") or 0)
        ok = int(execution_summary.get("ok") or metadata.get("summary", {}).get("ok") or 0)
        failure_breakdown = execution_summary.get("failure_breakdown") if isinstance(execution_summary.get("failure_breakdown"), dict) else {}
        primary_risk = next(iter(failure_breakdown.keys()), "stable")

        executive_summary = f"This execution finished with {total} items, {ok} passed and {failed} failed."
        if failure_breakdown:
            executive_summary += f" Failures are mainly concentrated in {', '.join(str(key) for key in failure_breakdown.keys())}."

        risk_summary = self._build_risk_summary(primary_risk=primary_risk, failed=failed, recent_suite_execution=recent_suite_execution)
        top_failures = [
            {"category": str(key), "count": int(value)}
            for key, value in failure_breakdown.items()
            if isinstance(value, (int, float))
        ]
        recommended_actions = self._recommended_actions(primary_risk=primary_risk, failed=failed)
        return {
            "executive_summary": executive_summary,
            "risk_summary": risk_summary,
            "top_failures": top_failures,
            "recommended_actions": recommended_actions,
        }

    def _build_risk_summary(self, *, primary_risk: str, failed: int, recent_suite_execution: dict[str, Any]) -> str:
        if failed == 0:
            return "No immediate regression signal was detected in this execution."
        previous_summary = recent_suite_execution.get("summary") if isinstance(recent_suite_execution.get("summary"), dict) else {}
        previous_failed = int(previous_summary.get("ng") or 0)
        if previous_failed and previous_failed == failed:
            return f"The current failure volume is similar to the latest suite baseline, with primary risk in {primary_risk}."
        return f"There is visible regression risk in {primary_risk}, and the latest execution should be compared for confirmation."

    def _recommended_actions(self, *, primary_risk: str, failed: int) -> list[str]:
        if failed == 0:
            return ["Archive this report summary and keep the current baseline for comparison."]
        mapping = {
            "timeout": [
                "Inspect downstream latency and timeout metrics around this run.",
                "Compare with other executions from the same time window.",
            ],
            "request_error": [
                "Verify environment reachability and gateway configuration.",
                "Check whether failures reproduced in another environment.",
            ],
            "assertion_failed": [
                "Inspect the raw response body and validate whether assertions are stale.",
                "Compare with the latest successful report for the same suite.",
            ],
        }
        return mapping.get(
            primary_risk,
            [
                "Review the failed items and confirm whether the failure is environmental or a real regression.",
                "Use the latest suite baseline to prioritize follow-up checks.",
            ],
        )

    def _has_rule_baseline(self, snapshot: dict[str, Any]) -> bool:
        execution_summary = snapshot.get("execution_summary") if isinstance(snapshot.get("execution_summary"), dict) else {}
        metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
        recent_suite_execution = snapshot.get("recent_suite_execution") if isinstance(snapshot.get("recent_suite_execution"), dict) else {}
        return bool(execution_summary or metadata.get("summary") or recent_suite_execution)

    def _build_baseline_warnings(self, snapshot: dict[str, Any], *, has_rule_baseline: bool) -> list[str]:
        warnings: list[str] = []
        execution_summary = snapshot.get("execution_summary") if isinstance(snapshot.get("execution_summary"), dict) else {}
        if not has_rule_baseline:
            warnings.append("当前报告上下文不足，规则总结尚未建立稳定基线。")
        if not execution_summary.get("failure_breakdown") and int(execution_summary.get("ng") or 0) > 0:
            warnings.append("当前失败分类信息不完整，总结将更多依赖聚合计数。")
        return warnings

    def _merge_result(self, *, baseline_result: dict[str, Any], llm_result: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_result(llm_result, fallback=baseline_result)
        if not normalized["executive_summary"]:
            return dict(baseline_result)
        return normalized

    def _normalize_result(self, llm_result: dict[str, Any], *, fallback: dict[str, Any]) -> dict[str, Any]:
        top_failures = [
            {
                "category": str(item.get("category") or "").strip(),
                "count": int(item.get("count") or 0),
            }
            for item in llm_result.get("top_failures") or []
            if isinstance(item, dict) and str(item.get("category") or "").strip()
        ]
        recommended_actions = [str(item).strip() for item in llm_result.get("recommended_actions") or [] if str(item).strip()]
        return {
            "executive_summary": str(llm_result.get("executive_summary") or fallback["executive_summary"]).strip(),
            "risk_summary": str(llm_result.get("risk_summary") or fallback["risk_summary"]).strip(),
            "top_failures": top_failures or list(fallback["top_failures"]),
            "recommended_actions": recommended_actions or list(fallback["recommended_actions"]),
        }

    def _merge_warnings(
        self,
        *,
        baseline_warnings: list[str],
        llm_warnings: list[str],
        has_rule_baseline: bool,
    ) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def _append(items: list[str]) -> None:
            for item in items:
                normalized = str(item).strip()
                if not normalized or normalized in seen:
                    continue
                ordered.append(normalized)
                seen.add(normalized)

        _append(baseline_warnings)
        _append(llm_warnings)
        if not has_rule_baseline:
            _append(["当前总结可信度较低，请结合原始报告人工确认。"])
        return ordered

    def _fallback_warning(self, error: HTTPException) -> str:
        detail = str(error.detail or "")
        if error.status_code == 504:
            return "大模型总结超时，已回退到规则总结结果。"
        if "API key" in detail or "endpoint" in detail or "model" in detail or "provider" in detail:
            return "当前未配置可用的大模型总结能力，已回退到规则总结结果。"
        return "大模型总结暂不可用，已回退到规则总结结果。"

    def _build_fallback_call_trace(self, error: HTTPException) -> dict[str, Any]:
        failure_category = "llm_unavailable"
        if error.status_code == 504:
            failure_category = "llm_timeout"
        elif error.status_code == 502:
            failure_category = "llm_response_error"
        return {
            "call_mode": "deterministic_fallback",
            "failure_category": failure_category,
            "trace_json": {"detail": str(error.detail or "")},
        }
