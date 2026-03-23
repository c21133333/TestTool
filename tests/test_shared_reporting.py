from __future__ import annotations

import json
from pathlib import Path

from requesttool.shared.reporting import ReportGenerator


def test_report_generator_writes_json_and_html(tmp_path):
    template_path = tmp_path / "report.html"
    template_path.write_text("<html><body>$suite_name|$summary_html|$items_html</body></html>", encoding="utf-8")
    generator = ReportGenerator(str(template_path))

    paths = generator.generate(
        {
            "suite_name": "Smoke",
            "base_url": "https://example.com",
            "execute_time": "2026-03-23T10:00:00",
            "summary": {"total": 1, "ok": 1, "ng": 0, "pass_rate": 100.0, "duration_ms": 12},
            "items": [
                {
                    "name": "Health check",
                    "request": {"method": "GET", "url": "/health"},
                    "response": {"status_code": 200},
                    "assertions": [{"name": "status_code", "passed": True}],
                    "result": "OK",
                }
            ],
        },
        str(tmp_path / "reports"),
    )

    json_payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    html_payload = Path(paths["html"]).read_text(encoding="utf-8")

    assert json_payload["suite_name"] == "Smoke"
    assert "Smoke" in html_payload
    assert "Health check" in html_payload
