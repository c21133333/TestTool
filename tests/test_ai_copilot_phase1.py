from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import AiArtifact, Report
from backend.app.models.base import Base
from backend.app.repositories.ai_artifact_repository import AiArtifactRepository
from backend.app.schemas.ai_copilot import AiArtifactCapability, AiArtifactStatus, AiArtifactTargetType
from backend.app.schemas.workspace import ApiCaseCreate, EnvironmentCreate, ProjectCreate, SuiteCreate
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.ai_assertion_service import AiAssertionService
from backend.app.services.ai_copilot_service import AiCopilotService
from backend.app.services.ai_context_assembler import AiContextAssembler
from backend.app.services.ai_diagnosis_service import AiDiagnosisService
from backend.app.services.execution_service import ExecutionService
from backend.app.services.report_service import ReportService
from backend.app.services.ai_report_summary_service import AiReportSummaryService
from backend.app.services.workspace_service import WorkspaceService


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def test_ai_artifact_repository_creates_preview_artifact():
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="AI Copilot", description=""))
    session.commit()

    repository = AiArtifactRepository(session)
    artifact = repository.create(
        AiArtifact(
            artifact_id="artifact_preview_001",
            capability="diagnosis",
            target_type="execution",
            target_id=101,
            project_id=project.id,
            execution_id=101,
            input_json={"execution_id": 101},
            output_json={"diagnosis_category": "dependency_timeout"},
            warnings_json=["low confidence"],
            status="draft",
            provider="openai_compatible",
            model="gpt-5.4",
        )
    )
    session.commit()

    stored = repository.get_by_artifact_id("artifact_preview_001")

    assert artifact.id is not None
    assert stored is not None
    assert stored.capability == "diagnosis"
    assert stored.target_type == "execution"
    assert stored.target_id == 101
    assert stored.status == "draft"
    assert stored.output_json["diagnosis_category"] == "dependency_timeout"
    assert stored.warnings_json == ["low confidence"]


def test_ai_artifact_repository_lists_history_by_target():
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="AI Copilot", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Smoke", description=""))
    session.commit()

    repository = AiArtifactRepository(session)
    repository.create(
        AiArtifact(
            artifact_id="artifact_history_old",
            capability="assertion",
            target_type="case",
            target_id=201,
            project_id=project.id,
            suite_id=suite.id,
            case_id=201,
            input_json={"case_id": 201},
            output_json={"suggested_assertions": [{"type": "status_code"}]},
            warnings_json=[],
            status="draft",
            provider="openai_compatible",
            model="gpt-5.4",
        )
    )
    repository.create(
        AiArtifact(
            artifact_id="artifact_history_new",
            capability="assertion",
            target_type="case",
            target_id=201,
            project_id=project.id,
            suite_id=suite.id,
            case_id=201,
            input_json={"case_id": 201},
            output_json={"suggested_assertions": [{"type": "json_path"}]},
            warnings_json=[],
            status="draft",
            provider="openai_compatible",
            model="gpt-5.4",
        )
    )
    repository.create(
        AiArtifact(
            artifact_id="artifact_other_target",
            capability="assertion",
            target_type="case",
            target_id=202,
            project_id=project.id,
            suite_id=suite.id,
            case_id=202,
            input_json={"case_id": 202},
            output_json={"suggested_assertions": [{"type": "response_time"}]},
            warnings_json=[],
            status="draft",
            provider="openai_compatible",
            model="gpt-5.4",
        )
    )
    session.commit()

    history = repository.list_history(capability="assertion", target_type="case", target_id=201)

    assert [item.artifact_id for item in history] == ["artifact_history_new", "artifact_history_old"]


def test_ai_artifact_repository_updates_status_to_applied():
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="AI Copilot", description=""))
    session.commit()

    repository = AiArtifactRepository(session)
    artifact = repository.create(
        AiArtifact(
            artifact_id="artifact_apply_001",
            capability="report_summary",
            target_type="report",
            target_id=301,
            project_id=project.id,
            report_id=301,
            input_json={"report_id": 301},
            output_json={"executive_summary": "summary"},
            warnings_json=[],
            status="draft",
            provider="openai_compatible",
            model="gpt-5.4",
        )
    )
    session.commit()

    artifact.status = "accepted"
    repository.save(artifact)
    artifact.status = "applied"
    repository.save(artifact)
    session.commit()

    stored = repository.get_by_artifact_id("artifact_apply_001")

    assert stored is not None
    assert stored.status == "applied"


def test_ai_copilot_preview_returns_artifact_envelope():
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="AI Copilot", description=""))
    session.commit()

    class FakeContextAssembler:
        def build_context(self, *, capability, target_type, target_id):
            return {
                "capability": capability,
                "target_type": target_type,
                "target_id": target_id,
                "input_snapshot": {"execution_id": target_id, "summary": {"ng": 1}},
            }

    def fake_diagnosis_runner(context):
        assert context["target_id"] == 401
        return {
            "result": {
                "diagnosis_category": "dependency_timeout",
                "root_cause_hypothesis": "downstream timeout",
            },
            "warnings": ["review manually"],
        }

    service = AiCopilotService(
        session,
        context_assembler=FakeContextAssembler(),
        capability_runners={AiArtifactCapability.diagnosis.value: fake_diagnosis_runner},
    )

    preview = service.preview(
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=401,
        project_id=project.id,
        execution_id=401,
        provider="openai_compatible",
        model="gpt-5.4",
    )

    stored = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)

    assert preview.capability == AiArtifactCapability.diagnosis
    assert preview.status == AiArtifactStatus.draft
    assert preview.result["diagnosis_category"] == "dependency_timeout"
    assert preview.warnings == ["review manually"]
    assert stored is not None
    assert stored.execution_id == 401
    assert stored.input_json["input_snapshot"]["execution_id"] == 401


def test_ai_copilot_history_filters_by_capability_and_target():
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="AI Copilot", description=""))
    session.commit()

    artifact_service = AiArtifactService(session)
    artifact_service.create_draft_artifact(
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=501,
        project_id=project.id,
        execution_id=501,
        input_json={"input_snapshot": {"execution_id": 501}},
        output_json={"diagnosis_category": "timeout"},
        warnings=["first"],
    )
    artifact_service.create_draft_artifact(
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=501,
        project_id=project.id,
        execution_id=501,
        input_json={"input_snapshot": {"execution_id": 501}},
        output_json={"diagnosis_category": "auth_issue"},
        warnings=[],
    )
    artifact_service.create_draft_artifact(
        capability=AiArtifactCapability.report_summary,
        target_type=AiArtifactTargetType.report,
        target_id=601,
        project_id=project.id,
        report_id=601,
        input_json={"input_snapshot": {"report_id": 601}},
        output_json={"executive_summary": "summary"},
        warnings=[],
    )
    session.commit()

    service = AiCopilotService(session)
    history = service.list_history(
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=501,
    )

    assert [item.output_json["diagnosis_category"] for item in history.items] == ["auth_issue", "timeout"]
    assert all(item.capability == AiArtifactCapability.diagnosis for item in history.items)
    assert all(item.target_type == AiArtifactTargetType.execution for item in history.items)
    assert all(item.target_id == 501 for item in history.items)


def test_execution_context_contains_first_failure_and_retry_history(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Context", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Smoke", description=""))
    case = workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Timeout Case",
            method="GET",
            url="/timeout",
            assertions_json=[{"type": "status_code", "operator": "==", "expected": 200}],
        )
    )
    session.commit()

    attempts = {"count": 0}

    def fake_execute_case_payload(payload):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return {
                "name": payload["name"],
                "request": payload["request"],
                "response": {"success": False, "error_type": "Timeout", "error_message": "request timed out"},
                "assertion_results": [],
                "result": "FAIL",
            }
        return {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": False, "status_code": 500, "elapsed_ms": 11, "response_json": {"ok": False}},
            "assertion_results": [{"type": "status_code", "result": "FAIL", "message": "status mismatch"}],
            "result": "FAIL",
        }

    monkeypatch.setattr("backend.app.services.execution_service.settings.execution_retry_limit", 1)
    monkeypatch.setattr("backend.app.services.execution_service.execute_case_payload", fake_execute_case_payload)
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    execution = ExecutionService(session).run_case_now(case.id, None, None)

    context = AiContextAssembler(session).build_execution_context(execution.id)

    assert context["summary"]["first_failure"]["category"] in {"timeout", "assertion_failed", "request_error"}
    assert context["first_failure"]["message"]
    assert len(context["retry_history"]) == 1
    assert context["items"][0]["failure_message"]


def test_report_context_contains_summary_and_recent_execution_reference(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Reports", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Suite A", description=""))
    environment = workspace.create_environment(EnvironmentCreate(project_id=project.id, name="dev", base_url="https://example.com"))
    case = workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Health", method="GET", url="/health"))
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 8, "response_json": {"ok": True}},
            "assertion_results": [],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.report_service.ReportGenerator.generate", lambda self, run_data, output_dir: {"json": "web_runs/fake-1.json", "html": "web_runs/fake-1.html"})

    first_execution = ExecutionService(session).run_case_now(case.id, environment.id, None)
    second_execution = ExecutionService(session).run_case_now(case.id, environment.id, None)
    session.commit()

    report = session.query(Report).filter(Report.execution_id == second_execution.id, Report.report_type == "json").one()

    context = AiContextAssembler(session).build_report_context(report.id)

    assert context["metadata"]["summary"]["ok"] == 1
    assert context["execution_summary"]["ok"] == 1
    assert context["recent_suite_execution"]["execution_id"] == second_execution.id
    assert context["recent_suite_execution"]["summary"]["ok"] == 1
    assert first_execution.id != second_execution.id


def test_case_context_contains_existing_assertions_and_recent_success_sample(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Cases", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Suite A", description=""))
    environment = workspace.create_environment(EnvironmentCreate(project_id=project.id, name="dev", base_url="https://example.com"))
    case = workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Login",
            method="POST",
            url="/login",
            assertions_json=[{"type": "status_code", "operator": "==", "expected": 200}],
        )
    )
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 6, "response_json": {"code": 0, "token": "secret-token"}},
            "assertion_results": [{"type": "status_code", "result": "PASS", "expected": 200, "actual": 200, "message": ""}],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    ExecutionService(session).run_case_now(case.id, environment.id, None)

    context = AiContextAssembler(session).build_case_context(case.id)

    assert context["assertions_json"][0]["type"] == "status_code"
    assert context["recent_success_sample"]["response"]["response_json"]["code"] == 0
    assert "token" not in context["recent_success_sample"]["response"]["response_json"]


def test_diagnosis_preview_creates_draft_artifact(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Diagnosis", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Smoke", description=""))
    case = workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Timeout Case", method="GET", url="/timeout"))
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": False, "error_type": "Timeout", "error_message": "request timed out"},
            "assertion_results": [],
            "result": "FAIL",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.settings.execution_retry_limit", 0)
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    execution = ExecutionService(session).run_case_now(case.id, None, None)

    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.diagnosis.value: AiDiagnosisService().generate_preview},
    )
    preview = service.preview(
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=execution.id,
        project_id=project.id,
        execution_id=execution.id,
        provider="openai_compatible",
        model="gpt-5.4",
    )

    stored = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)

    assert preview.capability == AiArtifactCapability.diagnosis
    assert preview.result["diagnosis_category"] == "dependency_timeout"
    assert preview.result["next_actions"]
    assert stored is not None
    assert stored.execution_id == execution.id


def test_diagnosis_history_returns_existing_artifacts(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Diagnosis", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Smoke", description=""))
    case = workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Auth Case", method="GET", url="/me"))
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": False, "status_code": 401, "response_json": {"message": "token expired"}},
            "assertion_results": [{"type": "status_code", "result": "FAIL", "message": "expected 200 got 401"}],
            "result": "FAIL",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.settings.execution_retry_limit", 0)
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    execution = ExecutionService(session).run_case_now(case.id, None, None)
    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.diagnosis.value: AiDiagnosisService().generate_preview},
    )
    service.preview(
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=execution.id,
        project_id=project.id,
        execution_id=execution.id,
    )
    service.preview(
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=execution.id,
        project_id=project.id,
        execution_id=execution.id,
    )
    session.commit()

    history = service.list_history(
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=execution.id,
    )

    assert len(history.items) == 2
    assert all(item.capability == AiArtifactCapability.diagnosis for item in history.items)
    assert all(item.execution_id == execution.id for item in history.items)


def test_report_summary_preview_creates_artifact(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Reports", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Suite A", description=""))
    environment = workspace.create_environment(EnvironmentCreate(project_id=project.id, name="dev", base_url="https://example.com"))
    case = workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Health", method="GET", url="/health"))
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 8, "response_json": {"ok": True}},
            "assertion_results": [],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.report_service.ReportGenerator.generate", lambda self, run_data, output_dir: {"json": "web_runs/fake-rs-1.json", "html": "web_runs/fake-rs-1.html"})

    execution = ExecutionService(session).run_case_now(case.id, environment.id, None)
    session.commit()
    report = session.query(Report).filter(Report.execution_id == execution.id, Report.report_type == "json").one()

    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.report_summary.value: AiReportSummaryService().generate_preview},
    )
    preview = service.preview(
        capability=AiArtifactCapability.report_summary,
        target_type=AiArtifactTargetType.report,
        target_id=report.id,
        project_id=project.id,
        report_id=report.id,
    )

    stored = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)

    assert preview.capability == AiArtifactCapability.report_summary
    assert preview.result["executive_summary"]
    assert preview.result["risk_summary"]
    assert stored is not None
    assert stored.report_id == report.id


def test_report_summary_apply_writes_metadata_json_ai_summary(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Reports", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Suite A", description=""))
    environment = workspace.create_environment(EnvironmentCreate(project_id=project.id, name="dev", base_url="https://example.com"))
    case = workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Health", method="GET", url="/health"))
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": False, "status_code": 500, "elapsed_ms": 13, "response_json": {"ok": False}},
            "assertion_results": [{"type": "status_code", "result": "FAIL", "message": "status mismatch"}],
            "result": "FAIL",
        },
    )
    monkeypatch.setattr("backend.app.services.report_service.ReportGenerator.generate", lambda self, run_data, output_dir: {"json": "web_runs/fake-rs-2.json", "html": "web_runs/fake-rs-2.html"})

    execution = ExecutionService(session).run_case_now(case.id, environment.id, None)
    session.commit()
    report = session.query(Report).filter(Report.execution_id == execution.id, Report.report_type == "json").one()

    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.report_summary.value: AiReportSummaryService().generate_preview},
    )
    preview = service.preview(
        capability=AiArtifactCapability.report_summary,
        target_type=AiArtifactTargetType.report,
        target_id=report.id,
        project_id=project.id,
        report_id=report.id,
    )

    updated = ReportService(session).apply_ai_summary(preview.artifact_id)
    stored_artifact = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)

    assert "ai_summary" in updated.metadata_json
    assert updated.metadata_json["ai_summary"]["executive_summary"]
    assert stored_artifact is not None
    assert stored_artifact.status == "applied"


def test_assertion_preview_returns_suggestions_for_case(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Assertions", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Suite A", description=""))
    environment = workspace.create_environment(EnvironmentCreate(project_id=project.id, name="dev", base_url="https://example.com"))
    case = workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Profile", method="GET", url="/profile"))
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 9, "response_json": {"code": 0, "message": "ok", "data": {"user_id": 7}}},
            "assertion_results": [],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    ExecutionService(session).run_case_now(case.id, environment.id, None)

    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.assertion.value: AiAssertionService().generate_preview},
    )
    preview = service.preview(
        capability=AiArtifactCapability.assertion,
        target_type=AiArtifactTargetType.case,
        target_id=case.id,
        project_id=project.id,
        suite_id=suite.id,
        case_id=case.id,
    )

    stored = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)
    suggestions = preview.result["suggested_assertions"]

    assert preview.capability == AiArtifactCapability.assertion
    assert suggestions
    assert any(item["type"] == "status_code" for item in suggestions)
    assert any(item["type"] == "json_path" and item["path"] == "$.code" for item in suggestions)
    assert stored is not None
    assert stored.case_id == case.id


def test_assertion_apply_appends_assertions_without_overwriting_by_default(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Assertions", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Suite A", description=""))
    environment = workspace.create_environment(EnvironmentCreate(project_id=project.id, name="dev", base_url="https://example.com"))
    case = workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Profile",
            method="GET",
            url="/profile",
            assertions_json=[{"type": "status_code", "operator": "==", "expected": 200, "enabled": True}],
        )
    )
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 9, "response_json": {"code": 0, "message": "ok"}},
            "assertion_results": [{"type": "status_code", "result": "PASS", "expected": 200, "actual": 200, "message": ""}],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    ExecutionService(session).run_case_now(case.id, environment.id, None)

    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.assertion.value: AiAssertionService().generate_preview},
    )
    preview = service.preview(
        capability=AiArtifactCapability.assertion,
        target_type=AiArtifactTargetType.case,
        target_id=case.id,
        project_id=project.id,
        suite_id=suite.id,
        case_id=case.id,
    )

    updated = AiAssertionService(session).apply_artifact(preview.artifact_id, override_existing=False)
    stored_artifact = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)

    assert updated.assertions_json[0]["type"] == "status_code"
    assert len(updated.assertions_json) > 1
    assert any(item["type"] == "json_path" and item["path"] == "$.code" for item in updated.assertions_json)
    assert stored_artifact is not None
    assert stored_artifact.status == "applied"


def test_assertion_apply_requires_explicit_override_when_replacing_existing_assertions(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Assertions", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Suite A", description=""))
    environment = workspace.create_environment(EnvironmentCreate(project_id=project.id, name="dev", base_url="https://example.com"))
    case = workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Profile",
            method="GET",
            url="/profile",
            assertions_json=[{"type": "status_code", "operator": "==", "expected": 200, "enabled": True}],
        )
    )
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 9, "response_json": {"code": 0, "message": "ok"}},
            "assertion_results": [{"type": "status_code", "result": "PASS", "expected": 200, "actual": 200, "message": ""}],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    ExecutionService(session).run_case_now(case.id, environment.id, None)

    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.assertion.value: AiAssertionService().generate_preview},
    )
    preview = service.preview(
        capability=AiArtifactCapability.assertion,
        target_type=AiArtifactTargetType.case,
        target_id=case.id,
        project_id=project.id,
        suite_id=suite.id,
        case_id=case.id,
    )

    updated = AiAssertionService(session).apply_artifact(preview.artifact_id, override_existing=True)

    assert all(not (item["type"] == "status_code" and item.get("path") is None) for item in updated.assertions_json)
    assert updated.assertions_json == preview.result["suggested_assertions"]
