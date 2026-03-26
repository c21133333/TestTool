from __future__ import annotations

import enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AiArtifactCapability(str, enum.Enum):
    test_point = "test_point"
    coverage = "coverage"
    diagnosis = "diagnosis"
    assertion = "assertion"
    test_data = "test_data"
    mock = "mock"
    report_summary = "report_summary"


class AiArtifactTargetType(str, enum.Enum):
    project = "project"
    suite = "suite"
    case = "case"
    execution = "execution"
    report = "report"


class AiArtifactStatus(str, enum.Enum):
    draft = "draft"
    accepted = "accepted"
    rejected = "rejected"
    applied = "applied"
    superseded = "superseded"


class AiArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    artifact_id: str
    capability: AiArtifactCapability
    target_type: AiArtifactTargetType
    target_id: int
    project_id: int | None = None
    suite_id: int | None = None
    case_id: int | None = None
    execution_id: int | None = None
    report_id: int | None = None
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    status: AiArtifactStatus
    provider: str = ""
    model: str = ""
    call_trace: AiCallTraceRead | None = None


class AiArtifactHistoryListRead(BaseModel):
    items: list[AiArtifactRead] = Field(default_factory=list)


class AiCopilotPreviewResponse(BaseModel):
    artifact_id: str
    capability: AiArtifactCapability
    status: AiArtifactStatus
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    call_trace: AiCallTraceRead | None = None


class AiProviderConfigRead(BaseModel):
    provider: str
    model: str = ""
    base_url: str = ""
    timeout_seconds: int | None = None


class AiCallTraceRead(BaseModel):
    call_mode: str
    provider: AiProviderConfigRead | None = None
    latency_ms: int | None = None
    failure_category: str = ""
    trace_json: dict[str, Any] = Field(default_factory=dict)


class AiArtifactLineageNodeRead(BaseModel):
    artifact_id: str = ""
    resource_type: str
    resource_key: str
    link_type: str
    capability: AiArtifactCapability | None = None
    status: AiArtifactStatus | None = None
    created_at: str = ""


class AiArtifactLineageRead(BaseModel):
    root_artifact_id: str
    items: list[AiArtifactLineageNodeRead] = Field(default_factory=list)


class AiCoverageMissingDimensionInput(BaseModel):
    endpoint: str
    dimension: str
    reason: str = ""


class AiTestPointPreviewRequest(BaseModel):
    project_id: int | None = None
    suite_id: int | None = None
    markdown_text: str = ""
    prompt_hints: str = ""
    coverage_missing_dimensions: list[AiCoverageMissingDimensionInput] = Field(default_factory=list)


class AiTestPointGenerateDraftsRequest(BaseModel):
    artifact_id: str
    selected_point_ids: list[str] = Field(default_factory=list)
    project_id: int
    suite_name: str
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    timeout_seconds: int | None = None


class AiCoverageScanRequest(BaseModel):
    project_id: int | None = None
    suite_id: int | None = None

class AiTestPointRead(BaseModel):
    id: str
    title: str
    category: str
    risk_level: str
    reason: str
    covered_by_existing_cases: bool = False
    suggested_case_count: int = 0
    confidence: float = 0.85


class AiTestPointResult(BaseModel):
    test_points: list[AiTestPointRead] = Field(default_factory=list)


class AiCoverageMissingDimension(BaseModel):
    endpoint: str
    dimension: str
    reason: str


class AiCoverageSuggestedPoint(BaseModel):
    title: str
    category: str
    priority: str
    reason: str


class AiCoverageResult(BaseModel):
    coverage_score: int = 0
    missing_dimensions: list[AiCoverageMissingDimension] = Field(default_factory=list)
    suggested_points: list[AiCoverageSuggestedPoint] = Field(default_factory=list)


class AiTestDataVariantRead(BaseModel):
    variant_id: str
    name: str
    category: str
    payload_patch: dict[str, Any] = Field(default_factory=dict)
    target_fields: list[str] = Field(default_factory=list)
    reason: str
    suggested_assertions: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.85


class AiTestDataResult(BaseModel):
    data_variants: list[AiTestDataVariantRead] = Field(default_factory=list)


class AiMockTemplateRead(BaseModel):
    template_id: str
    scenario_name: str
    status_code: int
    response_template: dict[str, Any] = Field(default_factory=dict)
    mock_rules: list[dict[str, Any]] = Field(default_factory=list)
    reason: str
    confidence: float = 0.85


class AiMockResult(BaseModel):
    mock_templates: list[AiMockTemplateRead] = Field(default_factory=list)


class AiDiagnosisPreviewRequest(BaseModel):
    execution_id: int


class AiAssertionPreviewRequest(BaseModel):
    case_id: int


class AiAssertionApplyRequest(BaseModel):
    override_existing: bool = False


class AiTestDataPreviewRequest(BaseModel):
    case_id: int


class AiTestDataApplyRequest(BaseModel):
    selected_variant_ids: list[str] = Field(default_factory=list)
    override_existing: bool = False


class AiMockPreviewRequest(BaseModel):
    case_id: int


class AiMockApplyRequest(BaseModel):
    selected_template_ids: list[str] = Field(default_factory=list)
    override_existing: bool = False


class AiReportSummaryPreviewRequest(BaseModel):
    report_id: int


class AiReportSummaryApplyRequest(BaseModel):
    pass


class AiChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = ""


class AiChatSessionSummaryRead(BaseModel):
    session_id: int
    title: str = ""
    chat_mode: Literal["project", "free"] = "project"
    project_id: int | None = None
    project_name: str | None = None
    latest_message_preview: str = ""
    message_count: int = 0
    updated_at: str


class AiChatSessionListRead(BaseModel):
    items: list[AiChatSessionSummaryRead] = Field(default_factory=list)


class AiChatMessageRead(BaseModel):
    message_id: int
    role: Literal["user", "assistant"]
    content: str = ""
    created_at: str


class AiChatSessionRead(AiChatSessionSummaryRead):
    page_path: str = ""
    page_title: str = ""
    messages: list[AiChatMessageRead] = Field(default_factory=list)


class AiChatStreamRequest(BaseModel):
    session_id: int | None = None
    chat_mode: Literal["project", "free"] = "project"
    project_id: int | None = None
    page_path: str = ""
    page_title: str = ""
    messages: list[AiChatMessage] = Field(default_factory=list)
