from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.schemas.ai_copilot import AiArtifactStatus
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.workspace_service import WorkspaceService


class AiAssertionService:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
        existing_assertions = snapshot.get("assertions_json") if isinstance(snapshot.get("assertions_json"), list) else []
        recent_success_sample = snapshot.get("recent_success_sample") if isinstance(snapshot.get("recent_success_sample"), dict) else {}
        response = recent_success_sample.get("response") if isinstance(recent_success_sample.get("response"), dict) else {}
        response_body = response.get("response_json") if isinstance(response.get("response_json"), dict) else {}
        status_code = response.get("status_code")

        seen_keys = {self._assertion_key(item) for item in existing_assertions if isinstance(item, dict)}
        suggestions: list[dict[str, Any]] = []
        warnings: list[str] = []

        if not recent_success_sample:
            warnings.append("No recent successful execution sample was found. Assertion suggestions are unavailable for this case.")
            return {"result": {"suggested_assertions": []}, "warnings": warnings}

        if status_code is not None:
            candidate = {
                "type": "status_code",
                "operator": "==",
                "expected": status_code,
                "enabled": True,
                "reason": "Use the latest successful execution status code as the baseline assertion.",
                "confidence": 0.96,
            }
            if self._assertion_key(candidate) not in seen_keys:
                suggestions.append(candidate)
                seen_keys.add(self._assertion_key(candidate))

        for path, value in self._collect_scalar_paths(response_body):
            candidate = {
                "type": "json_path",
                "path": path,
                "operator": "==",
                "expected": value,
                "enabled": True,
                "reason": f"Observed stable field {path} in the latest successful execution sample.",
                "confidence": self._confidence_for(value),
            }
            key = self._assertion_key(candidate)
            if key in seen_keys:
                continue
            suggestions.append(candidate)
            seen_keys.add(key)
            if len(suggestions) >= 4:
                break

        if not suggestions:
            warnings.append("No non-duplicate assertion suggestion could be derived from the latest successful execution sample.")

        return {"result": {"suggested_assertions": suggestions}, "warnings": warnings}

    def apply_artifact(self, artifact_id: str, *, override_existing: bool = False):
        if self._session is None:
            raise RuntimeError("AiAssertionService.apply_artifact requires a database session.")

        artifact_service = AiArtifactService(self._session)
        artifact = artifact_service.accept_artifact(artifact_id)
        if artifact.capability != "assertion":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact capability mismatch.")
        if artifact.case_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact is not bound to a case.")

        workspace = WorkspaceService(self._session)
        api_case = workspace.get_case(artifact.case_id)
        suggested_assertions = [item for item in (artifact.output_json or {}).get("suggested_assertions", []) if isinstance(item, dict)]
        existing_assertions = [item for item in (api_case.assertions_json or []) if isinstance(item, dict)]

        if override_existing:
            next_assertions = suggested_assertions
        else:
            seen_keys = {self._assertion_key(item) for item in existing_assertions}
            appended = list(existing_assertions)
            for suggestion in suggested_assertions:
                key = self._assertion_key(suggestion)
                if key in seen_keys:
                    continue
                appended.append(suggestion)
                seen_keys.add(key)
            next_assertions = appended

        api_case.assertions_json = next_assertions
        saved = workspace.save_case(api_case)
        artifact.status = AiArtifactStatus.applied.value
        artifact_service.save(artifact)
        return saved

    def _collect_scalar_paths(self, value: Any, *, prefix: str = "$", depth: int = 0) -> list[tuple[str, Any]]:
        if depth > 2:
            return []
        if not isinstance(value, dict):
            return []

        collected: list[tuple[str, Any]] = []
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if isinstance(item, dict):
                collected.extend(self._collect_scalar_paths(item, prefix=path, depth=depth + 1))
                continue
            if isinstance(item, list) or item is None:
                continue
            if isinstance(item, str) and len(item.strip()) > 80:
                continue
            collected.append((path, item))
            if len(collected) >= 3:
                break
        return collected

    def _assertion_key(self, assertion: dict[str, Any]) -> str:
        normalized_expected = repr(assertion.get("expected"))
        return "|".join(
            [
                str(assertion.get("type") or ""),
                str(assertion.get("operator") or ""),
                str(assertion.get("path") or ""),
                str(assertion.get("header") or ""),
                normalized_expected,
            ]
        )

    def _confidence_for(self, value: Any) -> float:
        if isinstance(value, (bool, int, float)):
            return 0.9
        if isinstance(value, str) and len(value) <= 16:
            return 0.82
        return 0.74
