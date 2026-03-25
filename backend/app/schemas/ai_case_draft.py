from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


_KNOWN_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


class AiCaseDraftPreviewRequest(BaseModel):
    project_id: int
    suite_name: str = Field(min_length=1)
    markdown_text: str = Field(min_length=1)
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    prompt_preset: str = "balanced"
    prompt_hints: str = ""

    @field_validator("suite_name", "markdown_text", "provider", "model", "base_url", "api_key", "prompt_hints", "prompt_preset")
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        return value.strip()


class AiCaseDraftPayload(BaseModel):
    name: str = ""
    method: str = "GET"
    url: str = ""
    description: str = ""
    headers_json: dict[str, str] = Field(default_factory=dict)
    body_json: Any | None = None
    assertions_json: list[dict[str, Any]] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "method", "url", "description", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        normalized = value.strip().upper() or "GET"
        if normalized not in _KNOWN_HTTP_METHODS:
            return normalized
        return normalized

    @field_validator("headers_json", mode="before")
    @classmethod
    def normalize_headers(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {str(key).strip(): "" if item is None else str(item) for key, item in value.items()}

    @field_validator("assertions_json", mode="before")
    @classmethod
    def normalize_assertions(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    @field_validator("metadata_json", mode="before")
    @classmethod
    def normalize_metadata(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return dict(value)


class AiCaseDraftRead(BaseModel):
    draft_id: str
    selected: bool = True
    validation_status: Literal["valid", "warning", "invalid"] = "valid"
    validation_errors: list[str] = Field(default_factory=list)
    review_warnings: list[str] = Field(default_factory=list)
    case: AiCaseDraftPayload
    source_excerpt: str = ""
    source_location: dict[str, Any] = Field(default_factory=dict)


class AiCaseDraftBatchSummary(BaseModel):
    section_count: int = 0
    endpoint_count: int = 0


class AiCaseDraftBatchRead(BaseModel):
    history_id: str = ""
    created_at: str = ""
    suite_name: str
    doc_summary: AiCaseDraftBatchSummary
    drafts: list[AiCaseDraftRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    prompt_preset: str = "balanced"
    prompt_hints_effective: str = ""


class AiCaseDraftHistorySummaryRead(BaseModel):
    history_id: str
    created_at: str
    project_id: int
    suite_name: str
    provider: str
    model: str
    prompt_preset: str
    draft_count: int
    warning_count: int


class AiCaseDraftHistoryListRead(BaseModel):
    items: list[AiCaseDraftHistorySummaryRead] = Field(default_factory=list)


class AiCaseDraftRerunRequest(BaseModel):
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)


class AiCaseDraftImportRow(BaseModel):
    draft_id: str
    selected: bool = True
    case: dict[str, Any] = Field(default_factory=dict)
    source_excerpt: str = ""
    source_location: dict[str, Any] = Field(default_factory=dict)


class AiCaseDraftImportRequest(BaseModel):
    project_id: int
    suite_name: str = Field(min_length=1)
    drafts: list[AiCaseDraftImportRow] = Field(default_factory=list)

    @field_validator("suite_name")
    @classmethod
    def strip_suite_name(cls, value: str) -> str:
        return value.strip()


class AiCaseDraftImportFailure(BaseModel):
    draft_id: str
    reason: str


class AiCaseDraftImportResult(BaseModel):
    suite_id: int
    suite_name: str
    created_cases: int
    skipped_cases: int
    failures: list[AiCaseDraftImportFailure] = Field(default_factory=list)
