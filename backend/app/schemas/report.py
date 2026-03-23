from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    execution_id: int
    report_type: str
    file_path: str
    metadata_json: dict
    created_at: datetime
