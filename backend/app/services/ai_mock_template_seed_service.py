from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from backend.app.schemas.ai_copilot import AiMockResult, AiMockTemplateRead


class AiMockTemplateSeedService:
    def build_result(self, case_context: dict[str, Any]) -> AiMockResult:
        method = str(case_context.get("method") or "GET").upper()
        raw_url = str(case_context.get("url") or "")
        path = urlparse(raw_url).path or raw_url
        success_response = self._extract_response(case_context.get("recent_success_sample"))
        failure_response = self._extract_response(case_context.get("recent_failure_sample"))

        templates: list[AiMockTemplateRead] = []

        if success_response is not None:
            templates.append(
                self._build_template(
                    scenario_name="happy_path",
                    method=method,
                    path=path,
                    status_code=int(success_response.get("status_code") or 200),
                    response_template=self._extract_response_payload(success_response),
                    reason="latest successful response provides the safest baseline mock template",
                )
            )

        if failure_response is not None:
            failure_status = int(failure_response.get("status_code") or 500)
            failure_payload = self._extract_response_payload(failure_response)
            failure_text = " ".join(str(part).lower() for part in [failure_status, failure_payload, case_context.get("metadata_json", {})])

            if failure_status == 403 or "permission denied" in failure_text or "forbidden" in failure_text:
                templates.append(
                    self._build_template(
                        scenario_name="permission_denied",
                        method=method,
                        path=path,
                        status_code=failure_status,
                        response_template=failure_payload,
                        reason="permission-denied branch is present in recent failure history",
                    )
                )
            elif failure_status == 400 or "validation" in failure_text or "invalid" in failure_text:
                templates.append(
                    self._build_template(
                        scenario_name="validation_error",
                        method=method,
                        path=path,
                        status_code=failure_status,
                        response_template=failure_payload,
                        reason="validation failure branch is present in recent failure history",
                    )
                )
            elif failure_status >= 500 or "timeout" in failure_text or "degraded" in failure_text:
                templates.append(
                    self._build_template(
                        scenario_name="downstream_timeout",
                        method=method,
                        path=path,
                        status_code=failure_status,
                        response_template=failure_payload,
                        reason="downstream degradation or timeout is reflected in recent failure history",
                    )
                )

        return AiMockResult(mock_templates=templates)

    def _build_template(
        self,
        *,
        scenario_name: str,
        method: str,
        path: str,
        status_code: int,
        response_template: dict[str, Any],
        reason: str,
    ) -> AiMockTemplateRead:
        return AiMockTemplateRead(
            template_id=f"mt_{scenario_name}_{method.lower()}_{path.strip('/').replace('/', '_').replace('{', '').replace('}', '') or 'root'}",
            scenario_name=scenario_name,
            status_code=status_code,
            response_template=response_template,
            mock_rules=[{"method": method, "path": path, "status_code": status_code}],
            reason=reason,
            confidence=0.9 if scenario_name == "happy_path" else 0.86,
        )

    def _extract_response(self, sample: Any) -> dict[str, Any] | None:
        if not isinstance(sample, dict):
            return None
        response = sample.get("response")
        return response if isinstance(response, dict) else None

    def _extract_response_payload(self, response: dict[str, Any]) -> dict[str, Any]:
        payload = response.get("response_json")
        if isinstance(payload, dict):
            return payload
        return {"status_code": response.get("status_code")}
