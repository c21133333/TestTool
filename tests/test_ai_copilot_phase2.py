from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.base import Base
from backend.app.models.execution import Execution, ExecutionScope, ExecutionStatus
from backend.app.models.report import Report
from backend.app.schemas.ai_copilot import (
    AiArtifactCapability,
    AiArtifactStatus,
    AiArtifactTargetType,
    AiCopilotPreviewResponse,
    AiCoverageResult,
    AiTestPointResult,
)
from backend.app.repositories.ai_artifact_repository import AiArtifactRepository
from backend.app.services.ai_copilot_service import AiCopilotService
from backend.app.services.ai_coverage_service import AiCoverageService
from backend.app.schemas.workspace import ApiCaseCreate, EnvironmentCreate, ProjectCreate, SuiteCreate
from backend.app.services.ai_coverage_scan_service import AiCoverageScanService
from backend.app.services.ai_context_assembler import AiContextAssembler
from backend.app.services.ai_test_point_draft_service import AiTestPointDraftService
from backend.app.services.ai_test_point_service import AiTestPointService
from backend.app.services.workspace_service import WorkspaceService


class _FakeCoverageLlmService:
    def __init__(self) -> None:
        self.last_call_trace = {
            "call_mode": "llm",
            "provider": {
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "timeout_seconds": 30,
            },
            "latency_ms": 123,
            "failure_category": "",
            "trace_json": {"request_id": "cov-test-trace"},
        }

    def resolve_runtime(self):
        return object()

    def analyze_coverage(self, *, runtime, target_type: str, target_id: int, input_snapshot: dict, scan_result: AiCoverageResult):
        enhanced_missing = []
        for item in scan_result.missing_dimensions:
            enhanced_missing.append(
                {
                    "endpoint": item.endpoint,
                    "dimension": item.dimension,
                    "reason": f"AI 已复核 {item.endpoint}，确认仍缺少{item.dimension}覆盖。",
                }
            )
        return (
            AiCoverageResult.model_validate(
                {
                    "coverage_score": scan_result.coverage_score,
                    "missing_dimensions": enhanced_missing,
                    "suggested_points": [
                        {
                            "title": "补充 GET /profile 的异常流程覆盖",
                            "category": "negative_path",
                            "priority": "high",
                            "reason": "建议补充 GET /profile 的失败路径或非法输入场景。",
                        },
                        {
                            "title": "补充 POST /login 的状态码断言覆盖",
                            "category": "assertion_hardening",
                            "priority": "high",
                            "reason": "建议为 POST /login 增加明确的状态码与业务结果断言。",
                        },
                    ],
                }
            ),
            [],
        )


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def _seed_design_workspace(session: Session) -> tuple[int, int, int, int]:
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Phase 2 Project", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Auth Suite", description=""))
    workspace.create_environment(EnvironmentCreate(project_id=project.id, name="dev", base_url="https://example.com"))
    profile_case = workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Profile success",
            method="GET",
            url="/profile",
            headers_json={"Authorization": "Bearer keep-out", "X-Trace": "trace-id"},
            body_json={"page": 1, "password": "hidden"},
            assertions_json=[
                {"type": "status_code", "operator": "==", "expected": 200, "enabled": True},
                {"type": "json_path", "path": "$.code", "operator": "==", "expected": 0, "enabled": True},
            ],
            metadata_json={
                "category": "happy_path",
                "priority": "P0",
                "tags": ["user", "smoke"],
                "owner": "qa",
                "auth_token": "remove-me",
            },
        )
    )
    login_case = workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Login boundary",
            method="POST",
            url="/login",
            headers_json={"Cookie": "session=secret"},
            body_json={"username": "demo", "password": "demo123"},
            assertions_json=[
                {"type": "json_path", "path": "$.message", "operator": "contains", "expected": "ok", "enabled": True},
            ],
            metadata_json={
                "category": "boundary_path",
                "priority": "P1",
                "tags": ["auth"],
            },
        )
    )

    execution = Execution(
        project_id=project.id,
        suite_id=suite.id,
        environment_id=None,
        scope=ExecutionScope.suite,
        status=ExecutionStatus.failed,
        target_name=suite.name,
        summary_json={"total": 2, "passed": 1, "failed": 1},
        error_message="",
    )
    session.add(execution)
    session.flush()

    report = Report(
        execution_id=execution.id,
        report_type="json",
        file_path="reports/phase2.json",
        metadata_json={"summary": {"total": 2, "failed": 1}},
    )
    session.add(report)
    session.commit()

    return project.id, suite.id, execution.id, report.id


def test_ai_copilot_capability_enum_includes_test_point_and_coverage():
    capability_values = {item.value for item in AiArtifactCapability}

    assert "test_point" in capability_values
    assert "coverage" in capability_values


def test_ai_test_point_preview_response_contract():
    result = AiTestPointResult.model_validate(
        {
            "test_points": [
                {
                    "id": "tp_login_happy",
                    "title": "登录成功主链路",
                    "category": "happy_path",
                    "risk_level": "high",
                    "reason": "核心登录入口",
                    "covered_by_existing_cases": False,
                    "suggested_case_count": 2,
                }
            ]
        }
    )

    preview = AiCopilotPreviewResponse(
        artifact_id="artifact_tp_001",
        capability=AiArtifactCapability.test_point,
        status=AiArtifactStatus.draft,
        warnings=[],
        result=result.model_dump(),
    )

    assert preview.capability == AiArtifactCapability.test_point
    assert preview.result["test_points"][0]["category"] == "happy_path"
    assert preview.result["test_points"][0]["covered_by_existing_cases"] is False


def test_ai_coverage_preview_response_contract():
    result = AiCoverageResult.model_validate(
        {
            "coverage_score": 67,
            "missing_dimensions": [
                {
                    "endpoint": "POST /api/login",
                    "dimension": "boundary",
                    "reason": "已有 case 仅覆盖成功和参数错误，缺少边界输入",
                }
            ],
            "suggested_points": [
                {
                    "title": "登录密码长度边界",
                    "category": "boundary_path",
                    "priority": "high",
                    "reason": "当前缺少密码长度最小值验证",
                }
            ],
        }
    )

    preview = AiCopilotPreviewResponse(
        artifact_id="artifact_cov_001",
        capability=AiArtifactCapability.coverage,
        status=AiArtifactStatus.draft,
        warnings=["coverage is deterministic-first"],
        result=result.model_dump(),
    )

    assert preview.capability == AiArtifactCapability.coverage
    assert preview.warnings == ["coverage is deterministic-first"]
    assert preview.result["coverage_score"] == 67
    assert preview.result["missing_dimensions"][0]["dimension"] == "boundary"
    assert preview.result["suggested_points"][0]["category"] == "boundary_path"


def test_project_context_contains_suites_and_case_summary():
    session = _make_session()
    project_id, suite_id, execution_id, report_id = _seed_design_workspace(session)

    context = AiContextAssembler(session).build_project_context(project_id)

    assert context["project_id"] == project_id
    assert context["suite_count"] == 1
    assert context["environment_count"] == 1
    assert context["case_summary"]["total_cases"] == 2
    assert context["case_summary"]["endpoint_count"] == 2
    assert context["suites"] == [{"suite_id": suite_id, "name": "Auth Suite", "case_count": 2}]
    assert {tuple(item.values()) for item in context["case_summary"]["unique_endpoints"]} == {("GET", "/profile"), ("POST", "/login")}
    assert context["recent_execution"]["execution_id"] == execution_id
    assert context["recent_report"]["report_id"] == report_id


def test_suite_context_contains_cases_and_assertion_breakdown():
    session = _make_session()
    _, suite_id, execution_id, report_id = _seed_design_workspace(session)

    context = AiContextAssembler(session).build_suite_context(suite_id)

    assert context["suite_id"] == suite_id
    assert len(context["cases"]) == 2
    assert context["case_summary"]["assertion_type_counts"] == {"json_path": 2, "status_code": 1}
    assert context["case_summary"]["metadata_summary"]["categories"] == {"boundary_path": 1, "happy_path": 1}
    assert context["case_summary"]["metadata_summary"]["priorities"] == {"P0": 1, "P1": 1}
    assert context["case_summary"]["metadata_summary"]["tags"] == {"auth": 1, "smoke": 1, "user": 1}
    assert context["recent_execution"]["execution_id"] == execution_id
    assert context["recent_report"]["report_id"] == report_id


def test_suite_context_sanitizes_sensitive_fields():
    session = _make_session()
    _, suite_id, _, _ = _seed_design_workspace(session)

    context = AiContextAssembler(session).build_suite_context(suite_id)
    profile_case = next(item for item in context["cases"] if item["name"] == "Profile success")

    assert "Authorization" not in profile_case["headers_json"]
    assert "password" not in profile_case["body_json"]
    assert "auth_token" not in profile_case["metadata_json"]


def test_coverage_scan_scores_suite_from_case_metadata_and_assertions():
    session = _make_session()
    _, suite_id, _, _ = _seed_design_workspace(session)

    result = AiCoverageScanService(session).scan(target_type="suite", target_id=suite_id)

    assert result.coverage_score == 55
    assert result.suggested_points == []


def test_coverage_scan_reports_missing_dimensions():
    session = _make_session()
    _, suite_id, _, _ = _seed_design_workspace(session)

    result = AiCoverageScanService(session).scan(target_type="suite", target_id=suite_id)
    missing_pairs = {(item.endpoint, item.dimension) for item in result.missing_dimensions}

    assert ("GET /profile", "negative_path") in missing_pairs
    assert ("GET /profile", "latency") in missing_pairs
    assert ("POST /login", "status") in missing_pairs
    assert ("POST /login", "schema") in missing_pairs


def test_coverage_scan_is_deterministic_without_llm():
    session = _make_session()
    project_id, _, _, _ = _seed_design_workspace(session)

    scanner = AiCoverageScanService(session)
    first = scanner.scan(target_type="project", target_id=project_id)
    second = scanner.scan(target_type="project", target_id=project_id)

    assert first.model_dump() == second.model_dump()


def test_ai_copilot_coverage_preview_persists_artifact():
    session = _make_session()
    project_id, suite_id, _, _ = _seed_design_workspace(session)
    service = AiCopilotService(
        session,
        capability_runners={
            AiArtifactCapability.coverage.value: AiCoverageService(
                session,
                llm_service=_FakeCoverageLlmService(),
            ).generate_preview
        },
    )

    preview = service.preview(
        capability=AiArtifactCapability.coverage,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
    )
    stored = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)

    assert preview.capability == AiArtifactCapability.coverage
    assert preview.result["coverage_score"] == 55
    assert stored is not None
    assert stored.capability == AiArtifactCapability.coverage.value
    assert stored.target_type == AiArtifactTargetType.suite.value
    assert stored.target_id == suite_id
    assert stored.suite_id == suite_id
    assert preview.call_trace is not None
    assert preview.call_trace.call_mode == "llm"
    assert stored.provider == "openai_compatible"
    assert stored.model == "gpt-5.4"


def test_ai_copilot_coverage_history_filters_by_suite():
    session = _make_session()
    project_id, suite_id, _, _ = _seed_design_workspace(session)
    other_project = WorkspaceService(session).create_project(ProjectCreate(name="Other Project", description=""))
    other_suite = WorkspaceService(session).create_suite(SuiteCreate(project_id=other_project.id, name="Other Suite", description=""))
    session.commit()

    service = AiCopilotService(
        session,
        capability_runners={
            AiArtifactCapability.coverage.value: AiCoverageService(
                session,
                llm_service=_FakeCoverageLlmService(),
            ).generate_preview
        },
    )
    first = service.preview(
        capability=AiArtifactCapability.coverage,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
    )
    second = service.preview(
        capability=AiArtifactCapability.coverage,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
    )
    service.preview(
        capability=AiArtifactCapability.coverage,
        target_type=AiArtifactTargetType.suite,
        target_id=other_suite.id,
        project_id=other_project.id,
        suite_id=other_suite.id,
    )

    history = service.list_history(
        capability=AiArtifactCapability.coverage,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
    )

    assert [item.artifact_id for item in history.items] == [second.artifact_id, first.artifact_id]


def test_ai_copilot_coverage_result_contains_suggested_points():
    session = _make_session()
    _, suite_id, _, _ = _seed_design_workspace(session)

    result = AiCoverageService(session, llm_service=_FakeCoverageLlmService()).generate_preview(
        {
            "capability": "coverage",
            "target_type": "suite",
            "target_id": suite_id,
            "input_snapshot": AiContextAssembler(session).build_suite_context(suite_id),
        }
    )

    assert result["warnings"] == []
    assert result["result"]["coverage_score"] == 55
    assert len(result["result"]["suggested_points"]) > 0
    assert all("priority" in item for item in result["result"]["suggested_points"])
    assert result["call_trace"]["call_mode"] == "llm"
    assert result["result"]["missing_dimensions"][0]["reason"].startswith("AI 已复核 ")


def test_ai_test_point_preview_marks_existing_coverage_overlap():
    session = _make_session()
    project_id, suite_id, _, _ = _seed_design_workspace(session)
    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_point.value: AiTestPointService(session).generate_preview},
    )

    preview = service.preview(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
        supplemental_input={
            "markdown_text": "## Profile\nGET /profile\n\n## Orders\nPOST /orders",
            "prompt_hints": "Focus on smoke and obvious failures.",
        },
    )

    profile_happy = next(item for item in preview.result["test_points"] if item["title"] == "GET /profile happy_path")
    orders_happy = next(item for item in preview.result["test_points"] if item["title"] == "POST /orders happy_path")

    assert profile_happy["covered_by_existing_cases"] is True
    assert orders_happy["covered_by_existing_cases"] is False


def test_ai_test_point_preview_supports_markdown_plus_suite_context():
    session = _make_session()
    _, suite_id, _, _ = _seed_design_workspace(session)

    result = AiTestPointService(session).generate_preview(
        {
            "capability": "test_point",
            "target_type": "suite",
            "target_id": suite_id,
            "markdown_text": "## Auth API\nGET /profile\nPOST /login",
            "prompt_hints": "Cover core regression paths.",
            "input_snapshot": AiContextAssembler(session).build_suite_context(suite_id),
        }
    )

    assert result["warnings"] == []
    assert {item["category"] for item in result["result"]["test_points"]} == {"happy_path", "negative_path", "boundary_path"}
    assert any(item["title"] == "GET /profile happy_path" for item in result["result"]["test_points"])
    assert any(item["title"] == "POST /login boundary_path" for item in result["result"]["test_points"])


def test_ai_test_point_history_filters_by_target():
    session = _make_session()
    project_id, suite_id, _, _ = _seed_design_workspace(session)
    other_project = WorkspaceService(session).create_project(ProjectCreate(name="TP Other Project", description=""))
    other_suite = WorkspaceService(session).create_suite(SuiteCreate(project_id=other_project.id, name="TP Other Suite", description=""))
    session.commit()

    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_point.value: AiTestPointService(session).generate_preview},
    )
    first = service.preview(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
        supplemental_input={"markdown_text": "GET /profile"},
    )
    second = service.preview(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
        supplemental_input={"markdown_text": "POST /login"},
    )
    service.preview(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.suite,
        target_id=other_suite.id,
        project_id=other_project.id,
        suite_id=other_suite.id,
        supplemental_input={"markdown_text": "GET /other"},
    )

    history = service.list_history(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
    )

    assert [item.artifact_id for item in history.items] == [second.artifact_id, first.artifact_id]


def test_ai_test_point_preview_supports_project_context_without_markdown():
    session = _make_session()
    project_id, _, _, _ = _seed_design_workspace(session)

    preview = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_point.value: AiTestPointService(session).generate_preview},
    ).preview(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.project,
        target_id=project_id,
        project_id=project_id,
    )

    assert preview.capability == AiArtifactCapability.test_point
    assert any(item["title"] == "GET /profile happy_path" for item in preview.result["test_points"])
    assert any(item["title"] == "POST /login negative_path" for item in preview.result["test_points"])
    assert all(item["covered_by_existing_cases"] is True for item in preview.result["test_points"])


def test_generate_drafts_from_selected_test_points_returns_ai_case_batch(monkeypatch):
    session = _make_session()
    project_id, suite_id, _, _ = _seed_design_workspace(session)
    copilot = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_point.value: AiTestPointService(session).generate_preview},
    )
    preview = copilot.preview(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
        supplemental_input={"markdown_text": "GET /profile\nPOST /login"},
    )
    point_id = preview.result["test_points"][0]["id"]

    monkeypatch.setattr(
        "backend.app.services.llm_case_generation_service.LlmCaseGenerationService.generate_drafts",
        lambda self, section_title, section_content, runtime, prompt_hints="": (
            [
                {
                    "draft_id": "draft_from_point_1",
                    "name": f"{section_title} case",
                    "method": "GET",
                    "url": "/profile",
                    "description": "generated from selected point",
                    "assertions_json": [{"type": "status_code", "operator": "==", "expected": 200, "enabled": True}],
                    "metadata_json": {"category": "happy_path"},
                }
            ],
            [],
        ),
    )

    batch = AiTestPointDraftService(session).generate_drafts_from_artifact(
        artifact_id=preview.artifact_id,
        selected_point_ids=[point_id],
        project_id=project_id,
        suite_name="Generated Suite",
        provider="openai_compatible",
        model="gpt-5.4",
        base_url="https://example.com",
        api_key="test-key",
        timeout_seconds=30,
    )

    assert batch.history_id
    assert batch.suite_name == "Generated Suite"
    assert len(batch.drafts) == 1
    assert batch.drafts[0].case.name.endswith("case")


def test_generate_drafts_from_selected_test_points_requires_selection(monkeypatch):
    session = _make_session()
    project_id, suite_id, _, _ = _seed_design_workspace(session)
    preview = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_point.value: AiTestPointService(session).generate_preview},
    ).preview(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
        supplemental_input={"markdown_text": "GET /profile"},
    )

    with pytest.raises(Exception) as exc_info:
        AiTestPointDraftService(session).generate_drafts_from_artifact(
            artifact_id=preview.artifact_id,
            selected_point_ids=[],
            project_id=project_id,
            suite_name="Generated Suite",
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://example.com",
            api_key="test-key",
            timeout_seconds=30,
        )

    assert "selected test point" in str(exc_info.value).lower()


def test_generated_drafts_keep_source_mapping_to_test_point(monkeypatch):
    session = _make_session()
    project_id, suite_id, _, _ = _seed_design_workspace(session)
    preview = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_point.value: AiTestPointService(session).generate_preview},
    ).preview(
        capability=AiArtifactCapability.test_point,
        target_type=AiArtifactTargetType.suite,
        target_id=suite_id,
        project_id=project_id,
        suite_id=suite_id,
        supplemental_input={"markdown_text": "GET /profile"},
    )
    selected_point = preview.result["test_points"][0]

    monkeypatch.setattr(
        "backend.app.services.llm_case_generation_service.LlmCaseGenerationService.generate_drafts",
        lambda self, section_title, section_content, runtime, prompt_hints="": (
            [
                {
                    "name": "Point linked draft",
                    "method": "GET",
                    "url": "/profile",
                    "description": "linked",
                    "assertions_json": [{"type": "status_code", "operator": "==", "expected": 200, "enabled": True}],
                    "metadata_json": {"category": "happy_path"},
                }
            ],
            [],
        ),
    )

    batch = AiTestPointDraftService(session).generate_drafts_from_artifact(
        artifact_id=preview.artifact_id,
        selected_point_ids=[selected_point["id"]],
        project_id=project_id,
        suite_name="Generated Suite",
        provider="openai_compatible",
        model="gpt-5.4",
        base_url="https://example.com",
        api_key="test-key",
        timeout_seconds=30,
    )

    assert batch.drafts[0].source_location["test_point_id"] == selected_point["id"]
    assert batch.drafts[0].source_location["test_point_title"] == selected_point["title"]
