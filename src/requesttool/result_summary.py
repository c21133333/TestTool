from __future__ import annotations


def build_summary(cases: list[dict]) -> dict:
    total = len(cases)
    passed = sum(1 for case in cases if case.get("result") == "PASS")
    failed = total - passed
    return {
        "total": total,
        "pass": passed,
        "fail": failed,
    }
