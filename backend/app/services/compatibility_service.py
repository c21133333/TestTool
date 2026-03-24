from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException, status

from backend.app.core.config import settings


class CompatibilityService:
    def get_legacy_policy(self) -> dict[str, Any]:
        sunset_date = settings.legacy_imports_sunset_date
        today = date.today()
        if not settings.legacy_imports_enabled:
            import_status = "disabled"
        elif sunset_date is not None and today > sunset_date:
            import_status = "expired"
        elif sunset_date is not None:
            import_status = "sunset_scheduled"
        else:
            import_status = "migration_only"

        return {
            "mode": "migration_bridge",
            "status": import_status,
            "legacy_imports_enabled": settings.legacy_imports_enabled,
            "sunset_date": sunset_date.isoformat() if sunset_date is not None else None,
            "rules": [
                "Legacy imports exist only for migration from desktop or spreadsheet assets.",
                "Do not add new authoring, export, or persistence features for project.json or legacy Excel semantics.",
                "The database-backed web model is the only long-term source of truth.",
            ],
            "capabilities": [
                {
                    "id": "excel_import",
                    "label": "Excel import",
                    "status": "migration_only",
                    "target": "suite_and_case_seed",
                },
                {
                    "id": "desktop_project_import",
                    "label": "Desktop project.json import",
                    "status": "migration_only",
                    "target": "suite_case_environment_and_history_seed",
                },
                {
                    "id": "desktop_run_report_import",
                    "label": "Desktop runsIndex/html/json history import",
                    "status": "migration_only",
                    "target": "historical_execution_backfill",
                },
                {
                    "id": "report_generator_wrapper",
                    "label": "Legacy import-path wrapper",
                    "status": "remove_when_unused",
                    "target": "refactor_compatibility_only",
                },
            ],
            "retirement_plan": [
                "Freeze legacy formats: no new fields, aliases, or write-back behavior.",
                "Keep imports read-only and limited to migration operators.",
                "Set a sunset date, then disable imports by configuration before code removal.",
                "Delete legacy import code and tests in a later v1.x cleanup once no active migration remains.",
            ],
        }

    def ensure_legacy_imports_available(self) -> None:
        policy = self.get_legacy_policy()
        if policy["status"] in {"disabled", "expired"}:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Legacy migration imports are no longer available. Use the web data model directly.",
            )
