from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProjectStore:
    def load_project(self, path: str | Path) -> dict[str, Any]:
        project_path = Path(path)
        if not project_path.exists():
            return self._default_project()
        try:
            payload = json.loads(project_path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_project()
        if not isinstance(payload, dict):
            return self._default_project()
        return self._normalize_project(payload)

    def save_project(self, path: str | Path, project: dict[str, Any]) -> None:
        project_path = Path(path)
        project_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = self._normalize_project(project)
        project_path.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _default_project(self) -> dict[str, Any]:
        return {
            "suites": [],
            "envs": [
                {
                    "name": "default",
                    "baseUrl": "",
                    "headers": {},
                    "vars": {},
                }
            ],
            "runsIndex": [],
            "ui_state": {},
            "save_dir": "",
            "recent_collections": [],
        }

    def _normalize_project(self, project: dict[str, Any]) -> dict[str, Any]:
        suites = project.get("suites")
        envs = project.get("envs")
        runs_index = project.get("runsIndex")
        ui_state = project.get("ui_state")
        save_dir = project.get("save_dir")
        recent_collections = project.get("recent_collections")
        return {
            "suites": suites if isinstance(suites, list) else [],
            "envs": envs if isinstance(envs, list) else [],
            "runsIndex": runs_index if isinstance(runs_index, list) else [],
            "ui_state": ui_state if isinstance(ui_state, dict) else {},
            "save_dir": save_dir if isinstance(save_dir, str) else "",
            "recent_collections": recent_collections if isinstance(recent_collections, list) else [],
        }
