from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.app.services.ai_diagnosis_llm_service import AiDiagnosisLlmService


class AiDiagnosisService:
    def __init__(
        self,
        *,
        llm_service: AiDiagnosisLlmService | None = None,
    ) -> None:
        self._llm_service = llm_service or AiDiagnosisLlmService()

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
        baseline_result = self._build_baseline_result(snapshot)
        baseline_warnings = self._build_baseline_warnings(snapshot, baseline_result)
        has_clear_signal = baseline_result["diagnosis_category"] != "unknown" and baseline_result["confidence"] >= 0.75

        warnings = list(baseline_warnings)
        result = dict(baseline_result)
        fallback_call_trace: dict[str, Any] | None = None

        try:
            runtime = self._llm_service.resolve_runtime()
            llm_result, llm_warnings = self._llm_service.analyze_diagnosis(
                runtime=runtime,
                input_snapshot=snapshot,
                baseline_result=baseline_result,
                has_clear_signal=has_clear_signal,
            )
            result = self._merge_result(baseline_result=baseline_result, llm_result=llm_result, has_clear_signal=has_clear_signal)
            warnings = self._merge_warnings(
                baseline_warnings=baseline_warnings,
                llm_warnings=llm_warnings,
                confidence=self._normalize_confidence(result.get("confidence"), fallback=baseline_result["confidence"]),
            )
        except HTTPException as exc:
            fallback_call_trace = self._build_fallback_call_trace(exc)
            warnings = self._merge_warnings(
                baseline_warnings=baseline_warnings,
                llm_warnings=[self._fallback_warning(exc)],
                confidence=baseline_result["confidence"],
            )

        return {
            "result": result,
            "warnings": warnings,
            "call_trace": fallback_call_trace or self._llm_service.last_call_trace,
        }

    def _build_baseline_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
        first_failure = snapshot.get("first_failure") if isinstance(snapshot.get("first_failure"), dict) else {}
        items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
        failure_breakdown = summary.get("failure_breakdown") if isinstance(summary.get("failure_breakdown"), dict) else {}

        category = self._diagnose_category(first_failure=first_failure, failure_breakdown=failure_breakdown, items=items)
        hypothesis = self._build_hypothesis(category=category, first_failure=first_failure)
        next_actions = self._build_next_actions(category=category)
        confidence = self._confidence_for(category)
        return {
            "diagnosis_category": category,
            "root_cause_hypothesis": hypothesis,
            "confidence": confidence,
            "next_actions": next_actions,
        }

    def _diagnose_category(
        self,
        *,
        first_failure: dict[str, Any],
        failure_breakdown: dict[str, Any],
        items: list[Any],
    ) -> str:
        combined_text = " ".join(
            str(part).lower()
            for part in [
                first_failure.get("category"),
                first_failure.get("message"),
                failure_breakdown,
                items,
            ]
        )
        if "timeout" in combined_text:
            return "dependency_timeout"
        if "401" in combined_text or "403" in combined_text or "auth" in combined_text or "token" in combined_text:
            return "auth_issue"
        if "mock" in combined_text:
            return "mock_mismatch"
        if "assertion" in combined_text or "expected" in combined_text:
            return "assertion_too_strict"
        if "request_error" in combined_text or "connection" in combined_text or "dns" in combined_text:
            return "environment_issue"
        if "data" in combined_text or "duplicate" in combined_text or "not found" in combined_text:
            return "test_data_issue"
        if "500" in combined_text or "502" in combined_text or "503" in combined_text:
            return "real_regression"
        return "unknown"

    def _build_hypothesis(self, *, category: str, first_failure: dict[str, Any]) -> str:
        message = str(first_failure.get("message") or "").strip()
        if category == "dependency_timeout":
            return f"Downstream dependency timed out or became unstable during execution. {message}".strip()
        if category == "auth_issue":
            return f"Authentication or authorization looks broken, likely due to expired credentials or permission mismatch. {message}".strip()
        if category == "assertion_too_strict":
            return f"The request reached the target, but the current assertion set may be too strict for the observed response. {message}".strip()
        if category == "environment_issue":
            return f"The failure looks closer to environment or network instability than to a product regression. {message}".strip()
        if category == "test_data_issue":
            return f"The execution likely used invalid, missing, or polluted test data. {message}".strip()
        if category == "mock_mismatch":
            return f"The observed response does not match the expected mock contract or configured scenario. {message}".strip()
        if category == "real_regression":
            return f"The service returned a business or server-side failure that looks like a real regression. {message}".strip()
        return f"The current evidence is insufficient for a precise diagnosis. {message}".strip()

    def _build_next_actions(self, *, category: str) -> list[str]:
        mapping = {
            "dependency_timeout": [
                "Check downstream service health and latency around the execution window.",
                "Compare timeout failures in other executions from the same time period.",
            ],
            "auth_issue": [
                "Verify token freshness, environment credentials, and permission scope.",
                "Replay the request with a known-good account or refreshed token.",
            ],
            "assertion_too_strict": [
                "Inspect the raw response body and compare it with the current assertion set.",
                "Review whether the case expects outdated response fields or business codes.",
            ],
            "environment_issue": [
                "Check network reachability, DNS, gateway, and environment configuration.",
                "Confirm whether other suites failed with similar request errors.",
            ],
            "test_data_issue": [
                "Inspect preconditions and whether the referenced resource exists.",
                "Re-run the case with a fresh, isolated dataset.",
            ],
            "mock_mismatch": [
                "Check the active mock scenario and compare it with the expected contract.",
                "Verify whether mock payload fields and status codes are still aligned.",
            ],
            "real_regression": [
                "Review recent service changes affecting the failing endpoint.",
                "Compare this failure with the latest successful baseline execution.",
            ],
            "unknown": [
                "Inspect raw request and response details for more failure evidence.",
                "Re-run the execution after validating environment, data, and authentication.",
            ],
        }
        return mapping.get(category, mapping["unknown"])

    def _confidence_for(self, category: str) -> float:
        mapping = {
            "dependency_timeout": 0.86,
            "auth_issue": 0.84,
            "assertion_too_strict": 0.78,
            "environment_issue": 0.72,
            "test_data_issue": 0.74,
            "mock_mismatch": 0.76,
            "real_regression": 0.73,
            "unknown": 0.42,
        }
        return mapping.get(category, 0.42)

    def _build_baseline_warnings(self, snapshot: dict[str, Any], baseline_result: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        if not snapshot.get("first_failure"):
            warnings.append("当前执行上下文缺少首个失败样本，诊断将更多依赖聚合摘要。")
        if baseline_result["diagnosis_category"] == "unknown":
            warnings.append("当前执行证据不足，规则诊断尚未收敛到明确类别。")
        return warnings

    def _merge_result(
        self,
        *,
        baseline_result: dict[str, Any],
        llm_result: dict[str, Any],
        has_clear_signal: bool,
    ) -> dict[str, Any]:
        normalized_llm = self._normalize_result(llm_result, fallback=baseline_result)
        if has_clear_signal and normalized_llm["diagnosis_category"] == "unknown":
            return dict(baseline_result)
        if has_clear_signal and normalized_llm["confidence"] + 0.15 < baseline_result["confidence"]:
            return dict(baseline_result)
        return normalized_llm

    def _normalize_result(self, llm_result: dict[str, Any], *, fallback: dict[str, Any]) -> dict[str, Any]:
        allowed_categories = {
            "dependency_timeout",
            "auth_issue",
            "mock_mismatch",
            "assertion_too_strict",
            "environment_issue",
            "test_data_issue",
            "real_regression",
            "unknown",
        }
        category = str(llm_result.get("diagnosis_category") or "").strip()
        normalized = {
            "diagnosis_category": category if category in allowed_categories else fallback["diagnosis_category"],
            "root_cause_hypothesis": str(llm_result.get("root_cause_hypothesis") or fallback["root_cause_hypothesis"]).strip(),
            "confidence": self._normalize_confidence(llm_result.get("confidence"), fallback=fallback["confidence"]),
            "next_actions": [str(item).strip() for item in llm_result.get("next_actions") or [] if str(item).strip()],
        }
        if not normalized["next_actions"]:
            normalized["next_actions"] = list(fallback["next_actions"])
        return normalized

    def _normalize_confidence(self, value: Any, *, fallback: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, confidence))

    def _merge_warnings(
        self,
        *,
        baseline_warnings: list[str],
        llm_warnings: list[str],
        confidence: float,
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
        if confidence < 0.75:
            _append(["当前诊断可信度较低，请结合原始执行详情人工确认。"])
        return ordered

    def _fallback_warning(self, error: HTTPException) -> str:
        detail = str(error.detail or "")
        if error.status_code == 504:
            return "大模型诊断超时，已回退到规则诊断结果。"
        if "API key" in detail or "endpoint" in detail or "model" in detail or "provider" in detail:
            return "当前未配置可用的大模型诊断能力，已回退到规则诊断结果。"
        return "大模型诊断暂不可用，已回退到规则诊断结果。"

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
