from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.base import Base
from backend.app.models.execution import ExecutionScope
from backend.app.models.registry import load_model_metadata
from backend.app.schemas.ai_copilot import (
    AiArtifactCapability,
    AiArtifactLineageNodeRead,
    AiArtifactLineageRead,
    AiArtifactStatus,
    AiArtifactTargetType,
    AiArtifactRead,
    AiCallTraceRead,
    AiProviderConfigRead,
)
from backend.app.schemas.execution import (
    AiExecutionPreparationRead,
    AiExecutionPreparationSelection,
    ExecutionCreateRequest,
)
from backend.app.schemas.ai_case_draft import AiCaseDraftPreviewRequest
from backend.app.schemas.workspace import ApiCaseCreate, ProjectCreate, SuiteCreate
from backend.app.services.ai_client_service import AiClientService
from backend.app.services.ai_artifact_lineage_service import AiArtifactLineageService
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.ai_case_draft_service import AiCaseDraftService
from backend.app.services.ai_provider_registry import AiProviderRegistry
from backend.app.services.execution_service import ExecutionService
from backend.app.services.ai_execution_preparation_service import AiExecutionPreparationService
from backend.app.services.ai_test_point_draft_service import AiTestPointDraftService
from backend.app.services.ai_copilot_service import AiCopilotService
from backend.app.services.llm_case_generation_service import AiGenerationRuntimeConfig, LlmCaseGenerationService
from backend.app.services.workspace_service import WorkspaceService


class _FakeLlmCaseGenerationService:
    def generate_drafts(
        self,
        *,
        section_title: str,
        section_content: str,
        runtime,
        prompt_hints: str = "",
    ) -> tuple[list[dict[str, Any]], list[str]]:
        return (
            [
                {
                    "name": f"{section_title} draft",
                    "method": "GET",
                    "url": "/profile",
                    "description": "generated from test point",
                    "assertions_json": [{"type": "status_code", "operator": "==", "expected": 200, "enabled": True}],
                    "metadata_json": {"category": "happy_path"},
                }
            ],
            [],
        )


class _FakeAiClientService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_json(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self.calls.append(
            {
                "runtime": runtime,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )
        return (
            {
                "drafts": [
                    {
                        "name": "Profile generated case",
                        "method": "GET",
                        "url": "/profile",
                        "description": "generated",
                        "headers_json": {},
                        "body_json": None,
                        "assertions_json": [{"type": "status_code", "operator": "==", "expected": 200, "enabled": True}],
                        "metadata_json": {"category": "happy_path"},
                    }
                ],
                "warnings": [],
            },
            {
                "call_mode": "llm",
                "provider": {
                    "provider": runtime.provider,
                    "model": runtime.model,
                    "base_url": runtime.endpoint,
                    "timeout_seconds": runtime.timeout_seconds,
                },
                "latency_ms": 128,
                "failure_category": "",
                "trace_json": {"provider": runtime.provider, "request_id": "trace_llm_001"},
            },
        )


def _make_session() -> Session:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def _seed_project(session: Session) -> tuple[int, int]:
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Phase 4 Project", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Design Suite", description=""))
    session.commit()
    return project.id, suite.id


def _seed_preparation_case(session: Session) -> int:
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Prep Project", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Prep Suite", description=""))
    api_case = workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Update profile",
            method="POST",
            url="/users/{user_id}/profile",
            body_json={"username": "demo", "profile": {"age": 18, "tags": ["smoke"]}},
            metadata_json={
                "ai_test_data_variants": [
                    {
                        "variant_id": "tv_boundary_age",
                        "name": "numeric_boundary",
                        "category": "boundary_path",
                        "payload_patch": {"profile": {"age": 19}},
                        "target_fields": ["profile.age"],
                        "reason": "boundary",
                        "suggested_assertions": [],
                    },
                    {
                        "variant_id": "tv_missing_username",
                        "name": "required_field_missing",
                        "category": "negative_path",
                        "payload_patch": {"username": None},
                        "target_fields": ["username"],
                        "reason": "required",
                        "suggested_assertions": [],
                    },
                ],
                "ai_mock_templates": [
                    {
                        "template_id": "mt_permission_denied",
                        "scenario_name": "permission_denied",
                        "status_code": 403,
                        "response_template": {"code": 40301, "message": "permission denied"},
                        "mock_rules": [{"method": "POST", "path": "/users/{user_id}/profile", "status_code": 403}],
                        "reason": "permission branch",
                    }
                ],
            },
        )
    )
    session.commit()
    return api_case.id


def test_phase4_execution_preparation_request_contract():
    selection = AiExecutionPreparationSelection(
        selected_test_data_variant_ids=["tv_boundary_age"],
        selected_mock_template_ids=["mt_permission_denied"],
    )
    request = ExecutionCreateRequest(
        scope=ExecutionScope.case,
        target_id=101,
        environment_id=3,
        ai_preparation=selection,
    )
    preparation = AiExecutionPreparationRead(
        case_id=101,
        request_body={"username": "demo", "profile": {"age": 19}},
        selected_test_data_variants=[{"variant_id": "tv_boundary_age"}],
        selected_mock_templates=[{"template_id": "mt_permission_denied"}],
        summary={"selected_variant_count": 1, "selected_template_count": 1},
    )

    assert request.ai_preparation is not None
    assert request.ai_preparation.selected_test_data_variant_ids == ["tv_boundary_age"]
    assert preparation.summary["selected_variant_count"] == 1


def test_phase4_artifact_lineage_contract():
    lineage = AiArtifactLineageRead(
        root_artifact_id="artifact_tp_001",
        items=[
            AiArtifactLineageNodeRead(
                artifact_id="artifact_tp_001",
                resource_type="ai_artifact",
                resource_key="artifact_tp_001",
                link_type="root",
                capability=AiArtifactCapability.test_point,
                status=AiArtifactStatus.draft,
            ),
            AiArtifactLineageNodeRead(
                artifact_id="",
                resource_type="ai_case_history",
                resource_key="history_001",
                link_type="generated_history",
            ),
        ],
    )

    assert lineage.root_artifact_id == "artifact_tp_001"
    assert lineage.items[1].resource_type == "ai_case_history"
    assert lineage.items[1].resource_key == "history_001"


def test_phase4_provider_trace_contract():
    trace = AiCallTraceRead(
        call_mode="llm",
        provider=AiProviderConfigRead(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com",
            timeout_seconds=30,
        ),
        latency_ms=1200,
        failure_category="",
        trace_json={"request_id": "trace_001"},
    )
    artifact = AiArtifactRead(
        artifact_id="artifact_diag_001",
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=301,
        input_json={},
        output_json={},
        warnings_json=[],
        status=AiArtifactStatus.draft,
        provider="openai_compatible",
        model="gpt-5.4",
        call_trace=trace,
    )

    assert artifact.call_trace is not None
    assert artifact.call_trace.provider is not None
    assert artifact.call_trace.provider.provider == "openai_compatible"
    assert artifact.call_trace.trace_json["request_id"] == "trace_001"


def test_artifact_lineage_links_test_point_artifact_to_case_history():
    session = _make_session()
    project_id, suite_id = _seed_project(session)
    artifact = AiArtifactService(session).create_draft_artifact(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
        input_json={"markdown_text": "## Profile\nGET /profile", "prompt_hints": "focus on profile"},
        output_json={
            "test_points": [
                {
                    "id": "tp_profile_happy",
                    "title": "GET /profile happy_path",
                    "category": "happy_path",
                    "risk_level": "medium",
                    "reason": "profile endpoint needs baseline coverage",
                }
            ]
        },
        warnings=[],
    )
    session.commit()

    batch = AiTestPointDraftService(
        session,
        llm_service=_FakeLlmCaseGenerationService(),
    ).generate_drafts_from_artifact(
        artifact_id=artifact.artifact_id,
        selected_point_ids=["tp_profile_happy"],
        project_id=project_id,
        suite_name="Derived Draft Suite",
        provider="openai_compatible",
        model="gpt-5.4",
        base_url="https://example.com",
        api_key="test-key",
        timeout_seconds=30,
    )

    lineage = AiArtifactLineageService(session).get_lineage(artifact.artifact_id)

    assert batch.history_id
    assert len(lineage.items) == 2
    assert lineage.items[1].resource_type == "ai_case_history"
    assert lineage.items[1].resource_key == batch.history_id


def test_artifact_lineage_lists_derived_nodes_in_order():
    session = _make_session()
    project_id, suite_id = _seed_project(session)
    artifact = AiArtifactService(session).create_draft_artifact(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
        input_json={"markdown_text": "## Profile\nGET /profile", "prompt_hints": ""},
        output_json={
            "test_points": [
                {
                    "id": "tp_profile_happy",
                    "title": "GET /profile happy_path",
                    "category": "happy_path",
                    "risk_level": "medium",
                    "reason": "profile endpoint needs baseline coverage",
                }
            ]
        },
        warnings=[],
    )
    session.commit()

    AiTestPointDraftService(
        session,
        llm_service=_FakeLlmCaseGenerationService(),
    ).generate_drafts_from_artifact(
        artifact_id=artifact.artifact_id,
        selected_point_ids=["tp_profile_happy"],
        project_id=project_id,
        suite_name="Derived Draft Suite",
        provider="openai_compatible",
        model="gpt-5.4",
        base_url="https://example.com",
        api_key="test-key",
        timeout_seconds=30,
    )

    lineage = AiArtifactLineageService(session).get_lineage(artifact.artifact_id)

    assert [item.resource_type for item in lineage.items] == ["ai_artifact", "ai_case_history"]
    assert lineage.items[0].artifact_id == artifact.artifact_id
    assert lineage.items[1].link_type == "generated_history"


def test_execution_preparation_resolves_selected_test_data_variants():
    session = _make_session()
    case_id = _seed_preparation_case(session)

    preparation = AiExecutionPreparationService(session).build_case_preparation(
        case_id=case_id,
        selection=AiExecutionPreparationSelection(selected_test_data_variant_ids=["tv_boundary_age"]),
    )

    assert preparation.request_body == {"username": "demo", "profile": {"age": 19, "tags": ["smoke"]}}
    assert preparation.summary["selected_variant_ids"] == ["tv_boundary_age"]
    assert preparation.summary["selected_template_ids"] == []


def test_execution_preparation_resolves_selected_mock_templates():
    session = _make_session()
    case_id = _seed_preparation_case(session)

    preparation = AiExecutionPreparationService(session).build_case_preparation(
        case_id=case_id,
        selection=AiExecutionPreparationSelection(selected_mock_template_ids=["mt_permission_denied"]),
    )

    assert preparation.request_body == {"username": "demo", "profile": {"age": 18, "tags": ["smoke"]}}
    assert [item["template_id"] for item in preparation.selected_mock_templates] == ["mt_permission_denied"]
    assert preparation.summary["selected_template_ids"] == ["mt_permission_denied"]


def test_execution_preparation_rejects_unknown_variant_or_template():
    session = _make_session()
    case_id = _seed_preparation_case(session)

    with pytest.raises(HTTPException) as variant_error:
        AiExecutionPreparationService(session).build_case_preparation(
            case_id=case_id,
            selection=AiExecutionPreparationSelection(selected_test_data_variant_ids=["missing_variant"]),
        )

    with pytest.raises(HTTPException) as template_error:
        AiExecutionPreparationService(session).build_case_preparation(
            case_id=case_id,
            selection=AiExecutionPreparationSelection(selected_mock_template_ids=["missing_template"]),
        )

    assert variant_error.value.status_code == 400
    assert template_error.value.status_code == 400


def test_run_case_now_applies_selected_test_data_variant_to_request_body(monkeypatch):
    session = _make_session()
    case_id = _seed_preparation_case(session)
    captured_payloads: list[dict[str, Any]] = []

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: (
            captured_payloads.append(payload)
            or {
                "name": payload["name"],
                "request": payload["request"],
                "response": {"success": True, "status_code": 200, "elapsed_ms": 8, "response_json": {"ok": True}},
                "assertion_results": [],
                "result": "PASS",
            }
        ),
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    execution = ExecutionService(session).run_case_now(
        case_id,
        None,
        None,
        ai_preparation=AiExecutionPreparationSelection(selected_test_data_variant_ids=["tv_boundary_age"]),
    )

    assert execution.status.value == "success"
    assert captured_payloads[0]["request"]["body"]["profile"]["age"] == 19
    assert execution.items[0].request_json["body"]["profile"]["age"] == 19


def test_run_case_now_persists_preparation_summary_into_execution(monkeypatch):
    session = _make_session()
    case_id = _seed_preparation_case(session)

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 7, "response_json": {"ok": True}},
            "assertion_results": [],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    execution = ExecutionService(session).run_case_now(
        case_id,
        None,
        None,
        ai_preparation=AiExecutionPreparationSelection(
            selected_test_data_variant_ids=["tv_missing_username"],
            selected_mock_template_ids=["mt_permission_denied"],
        ),
    )

    assert execution.summary_json["ai_preparation"]["selected_variant_ids"] == ["tv_missing_username"]
    assert execution.summary_json["ai_preparation"]["selected_template_ids"] == ["mt_permission_denied"]


def test_provider_registry_resolves_openai_compatible_runtime():
    runtime = AiProviderRegistry().resolve_runtime(
        provider="openai_compatible",
        model="gpt-5.4",
        base_url="https://example.com",
        api_key="test-key",
        timeout_seconds=30,
    )

    assert runtime.provider == "openai_compatible"
    assert runtime.endpoint == "https://example.com"
    assert runtime.model == "gpt-5.4"


def test_llm_draft_flow_consumes_unified_ai_client():
    session = _make_session()
    project_id, _ = _seed_project(session)
    fake_client = _FakeAiClientService()
    draft_service = AiCaseDraftService(
        session,
        llm_service=LlmCaseGenerationService(
            ai_client=fake_client,
            provider_registry=AiProviderRegistry(),
        ),
    )

    batch = draft_service.preview_drafts(
        AiCaseDraftPreviewRequest(
            project_id=project_id,
            suite_name="Generated Suite",
            markdown_text="## Profile\nGET /profile",
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com",
            api_key="test-key",
            timeout_seconds=30,
        )
    )

    assert len(batch.drafts) == 1
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["runtime"].provider == "openai_compatible"


def test_provider_registry_rejects_unknown_provider():
    with pytest.raises(HTTPException) as exc:
        AiProviderRegistry().resolve_runtime(
            provider="unknown_vendor",
            model="gpt-5.4",
            base_url="https://example.com",
            api_key="test-key",
            timeout_seconds=30,
        )

    assert exc.value.status_code == 400


def test_artifact_persists_call_trace_for_llm_capability():
    session = _make_session()
    project_id, suite_id = _seed_project(session)
    api_case = WorkspaceService(session).create_case(
        ApiCaseCreate(suite_id=suite_id, name="Case", method="GET", url="/profile")
    )
    session.commit()

    preview = AiCopilotService(
        session,
        capability_runners={
            AiArtifactCapability.test_data.value: lambda context: {
                "result": {"data_variants": []},
                "warnings": [],
                "call_trace": {
                    "call_mode": "llm",
                    "provider": {
                        "provider": "openai_compatible",
                        "model": "gpt-5.4",
                        "base_url": "https://example.com",
                        "timeout_seconds": 30,
                    },
                    "latency_ms": 210,
                    "failure_category": "",
                    "trace_json": {"request_id": "trace_001"},
                },
            }
        },
    ).preview(
        capability=AiArtifactCapability.test_data,
        target_type=AiArtifactTargetType.case,
        target_id=api_case.id,
        project_id=project_id,
        suite_id=suite_id,
        case_id=api_case.id,
    )
    stored = AiArtifactService(session).get_artifact_or_404(preview.artifact_id)

    assert stored.call_mode == "llm"
    assert stored.latency_ms == 210
    assert stored.trace_json["request_id"] == "trace_001"


def test_artifact_marks_deterministic_capability_without_llm_call():
    session = _make_session()
    project_id, suite_id = _seed_project(session)
    api_case = WorkspaceService(session).create_case(
        ApiCaseCreate(suite_id=suite_id, name="Case", method="GET", url="/profile")
    )
    session.commit()

    preview = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.mock.value: lambda context: {"result": {"mock_templates": []}, "warnings": []}},
    ).preview(
        capability=AiArtifactCapability.mock,
        target_type=AiArtifactTargetType.case,
        target_id=api_case.id,
        project_id=project_id,
        suite_id=suite_id,
        case_id=api_case.id,
    )
    stored = AiArtifactService(session).get_artifact_or_404(preview.artifact_id)

    assert stored.call_mode == "deterministic"
    assert stored.failure_category == ""
    assert stored.trace_json == {}
