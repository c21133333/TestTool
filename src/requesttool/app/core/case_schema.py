from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseSchema:
    case_id: str
    name: str
    endpoint: str
    category: str = ""
    precondition: str = ""
    request_json: dict[str, Any] = field(default_factory=dict)
    expected_http_status: int = 200
    expected_business_code: str | int | None = None
    expected_result: str = ""
    assertion_points: str = ""
    priority: str = ""
    test_result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "name": self.name,
            "endpoint": self.endpoint,
            "category": self.category,
            "precondition": self.precondition,
            "request_json": self.request_json,
            "expected_http_status": self.expected_http_status,
            "expected_business_code": self.expected_business_code,
            "expected_result": self.expected_result,
            "assertion_points": self.assertion_points,
            "priority": self.priority,
            "test_result": self.test_result,
        }
