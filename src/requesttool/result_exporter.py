from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class ResultExporter:
    def export_json(self, result: dict, output_dir: str) -> str:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        suite_name = str(result.get("suite_name", "suite"))
        safe_name = "".join(ch for ch in suite_name if ch.isalnum() or ch in ("-", "_"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = output_path / f"{safe_name}_{timestamp}.json"

        payload: dict[str, Any] = dict(result)
        payload.setdefault("execute_time", datetime.now().isoformat())

        with file_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        return str(file_path)
