from __future__ import annotations

from requesttool.shared.assertions import AssertionEngine
from requesttool import http_client, processor_engine


def execute_case_payload(case_payload: dict) -> dict:
    engine = AssertionEngine()
    return processor_engine.execute_case(case_payload, http_client, engine)
