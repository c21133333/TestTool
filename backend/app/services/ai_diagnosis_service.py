from __future__ import annotations

from typing import Any


class AiDiagnosisService:
    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
        summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
        first_failure = snapshot.get("first_failure") if isinstance(snapshot.get("first_failure"), dict) else {}
        items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
        failure_breakdown = summary.get("failure_breakdown") if isinstance(summary.get("failure_breakdown"), dict) else {}

        category = self._diagnose_category(first_failure=first_failure, failure_breakdown=failure_breakdown, items=items)
        hypothesis = self._build_hypothesis(category=category, first_failure=first_failure)
        next_actions = self._build_next_actions(category=category)
        confidence = self._confidence_for(category)
        warnings: list[str] = []
        if confidence < 0.75:
            warnings.append("Low confidence diagnosis. Review raw execution details before applying this conclusion.")

        return {
            "result": {
                "diagnosis_category": category,
                "root_cause_hypothesis": hypothesis,
                "confidence": confidence,
                "next_actions": next_actions,
            },
            "warnings": warnings,
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
