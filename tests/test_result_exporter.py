import json
from pathlib import Path

from requesttool.result_exporter import ResultExporter


def test_export_json(tmp_path):
    result = {"suite_name": "demo", "summary": {"total": 1, "pass": 1, "fail": 0}, "cases": []}
    exporter = ResultExporter()
    path = exporter.export_json(result, str(tmp_path))
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["suite_name"] == "demo"
    assert data["summary"]["pass"] == 1
