from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def export_test_result(
    output_dir: str | Path,
    case_info: dict,
    request_info: dict,
    response_info: dict,
    assertion_results: list[dict],
    elapsed_ms: int | None,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = output_path / f"test_result_{timestamp}.json"

    payload: dict[str, Any] = {
        "case_info": case_info,
        "request_info": request_info,
        "response_info": response_info,
        "assertion_results": assertion_results,
        "elapsed_ms": elapsed_ms,
        "timestamp": timestamp,
    }

    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)

    return file_path
