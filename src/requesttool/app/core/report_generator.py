from __future__ import annotations

import json
from html import escape
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any


class ReportGenerator:
    def __init__(self, template_path: str) -> None:
        self._template_path = Path(template_path)

    def generate(self, run_data: dict, output_dir: str) -> dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = output_path / f"run_{timestamp}.json"
        html_path = output_path / f"run_{timestamp}.html"

        json_path.write_text(
            json.dumps(run_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        template = Template(self._template_path.read_text(encoding="utf-8"))
        html = template.safe_substitute(self._build_template_context(run_data))
        html_path.write_text(html, encoding="utf-8")
        return {"json": str(json_path), "html": str(html_path)}

    def _build_template_context(self, run_data: dict) -> dict[str, str]:
        summary = run_data.get("summary", {})
        suite_name = run_data.get("suite_name", "")
        base_url = run_data.get("base_url", "")
        execute_time = run_data.get("execute_time", "")
        total = summary.get("total", 0) or 0
        ok = summary.get("ok", 0) or 0
        ng = summary.get("ng", 0) or 0
        pass_rate = summary.get("pass_rate", 0)
        duration_ms = summary.get("duration_ms", 0)

        failure_html = self._render_failures(run_data.get("items") or [])
        items_html = self._render_items(run_data.get("items") or [])
        summary_html = (
            f"<div class='summary-card'>"
            f"<div><strong>Total</strong><span>{total}</span></div>"
            f"<div><strong>OK</strong><span>{ok}</span></div>"
            f"<div><strong>NG</strong><span>{ng}</span></div>"
            f"<div><strong>Pass Rate</strong><span>{pass_rate}%</span></div>"
            f"<div><strong>Duration</strong><span>{duration_ms} ms</span></div>"
            f"</div>"
        )
        chart_html = self._render_chart(total, ok, ng)
        return {
            "suite_name": str(suite_name),
            "base_url": str(base_url),
            "execute_time": str(execute_time),
            "summary_html": summary_html,
            "chart_html": chart_html,
            "failure_html": failure_html,
            "items_html": items_html,
        }

    def _render_chart(self, total: int, ok: int, ng: int) -> str:
        if total <= 0:
            return (
                "<div class='summary-chart'>"
                "<div class='chart-title'>Results</div>"
                "<div class='chart-empty'>No data.</div>"
                "</div>"
            )
        ok_pct = round(ok / total * 100, 1)
        ng_pct = round(ng / total * 100, 1)
        return (
            "<div class='summary-chart'>"
            "<div class='chart-title'>Results</div>"
            "<div class='chart-bar'>"
            f"<div class='chart-seg ok' style='width: {ok_pct}%;'></div>"
            f"<div class='chart-seg ng' style='width: {ng_pct}%;'></div>"
            "</div>"
            "<div class='chart-stats'>"
            f"<span class='legend ok'>OK {ok} ({ok_pct}%)</span>"
            f"<span class='legend ng'>NG {ng} ({ng_pct}%)</span>"
            "</div>"
            "</div>"
        )

    def _render_failures(self, items: list[dict]) -> str:
        groups: dict[str, dict[str, Any]] = {}
        for item in items:
            if item.get("result") != "NG":
                continue
            assertions = item.get("assertions") or []
            if not assertions:
                key = "request_error"
                entry = groups.setdefault(key, {"title": "request_error", "count": 0, "cases": []})
                entry["count"] += 1
                entry["cases"].append(item.get("name") or item.get("case_id"))
                continue
            for assertion in assertions:
                if assertion.get("passed"):
                    continue
                title = assertion.get("name") or "assertion"
                message = assertion.get("message") or ""
                key = f"{title}:{message}"
                entry = groups.setdefault(key, {"title": title, "message": message, "count": 0, "cases": []})
                entry["count"] += 1
                entry["cases"].append(item.get("name") or item.get("case_id"))

        if not groups:
            return "<p class='empty'>No failures.</p>"
        rows = []
        for entry in groups.values():
            cases = "<br>".join(escape(str(case)) for case in entry["cases"])
            message = escape(str(entry.get("message"))) if entry.get("message") else ""
            rows.append(
                "<div class='failure-item'>"
                f"<div><strong>{escape(str(entry['title']))}</strong> <span class='count'>{entry['count']}</span></div>"
                f"<div class='message'>{message}</div>"
                f"<div class='cases'>{cases}</div>"
                "</div>"
            )
        return "\n".join(rows)

    def _render_items(self, items: list[dict]) -> str:
        rows = []
        for item in items:
            request_info = json.dumps(item.get("request"), ensure_ascii=False, indent=2)
            response_info = json.dumps(item.get("response"), ensure_ascii=False, indent=2)
            assertions_info = json.dumps(item.get("assertions"), ensure_ascii=False, indent=2)
            status_class = "ok" if item.get("result") == "OK" else "ng"
            summary = (
                f"{item.get('name', '')} "
                f"<span class='badge {status_class}'>{item.get('result')}</span>"
            )
            detail = (
                "<div class='detail-grid'>"
                f"<div><h4>Request</h4><pre>{request_info}</pre></div>"
                f"<div><h4>Response</h4><pre>{response_info}</pre></div>"
                f"<div><h4>Assertions</h4><pre>{assertions_info}</pre></div>"
                "</div>"
            )
            rows.append(
                "<details class='case-item'>"
                f"<summary>{summary}</summary>"
                f"{detail}"
                "</details>"
            )
        return "\n".join(rows) if rows else "<p class='empty'>No items.</p>"
