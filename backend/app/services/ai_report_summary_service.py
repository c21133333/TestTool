from __future__ import annotations

from typing import Any


class AiReportSummaryService:
    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
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
            "result": {
                "executive_summary": executive_summary,
                "risk_summary": risk_summary,
                "top_failures": top_failures,
                "recommended_actions": recommended_actions,
            },
            "warnings": [],
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
