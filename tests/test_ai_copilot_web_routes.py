from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import session_scope
from backend.app.main import create_application
from backend.app.models.api_case import ApiCase
from backend.app.models.ai_artifact import AiArtifact
from backend.app.models.base import Base
from backend.app.models.execution import Execution, ExecutionItem, ExecutionScope, ExecutionStatus
from backend.app.models.registry import load_model_metadata
from backend.app.models.report import Report
from backend.app.models.audit_log import AuditLog
from backend.app.models.user import UserRole
from backend.app.schemas.ai_copilot import AiArtifactCapability, AiArtifactTargetType, AiCoverageResult
from backend.app.schemas.workspace import ApiCaseCreate, EnvironmentCreate, ProjectCreate, SuiteCreate
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.ai_test_point_draft_service import AiTestPointDraftService
from backend.app.services.auth_service import AuthService
from backend.app.services.execution_service import ExecutionService
from backend.app.services.workspace_service import WorkspaceService


class _FakeLlmCaseGenerationService:
    def generate_drafts(
        self,
        *,
        section_title: str,
        section_content: str,
        runtime,
        prompt_hints: str = "",
    ) -> tuple[list[dict], list[str]]:
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


def _mock_coverage_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _analyze(self, runtime, target_type, target_id, input_snapshot, scan_result):
        self.last_call_trace = {
            "call_mode": "llm",
            "provider": {
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "timeout_seconds": 30,
            },
            "latency_ms": 88,
            "failure_category": "",
            "trace_json": {"request_id": "coverage-route-trace"},
        }
        return (
            AiCoverageResult.model_validate(
                {
                    "coverage_score": scan_result.coverage_score,
                    "missing_dimensions": [
                        {
                            "endpoint": item.endpoint,
                            "dimension": item.dimension,
                            "reason": f"AI 已确认 {item.endpoint} 仍缺少 {item.dimension} 覆盖。",
                        }
                        for item in scan_result.missing_dimensions
                    ],
                    "suggested_points": [
                        {
                            "title": "补充 GET /profile 的异常流程覆盖",
                            "category": "negative_path",
                            "priority": "high",
                            "reason": "建议补充 GET /profile 的失败路径检查。",
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

    monkeypatch.setattr(
        "backend.app.services.ai_coverage_llm_service.AiCoverageLlmService.resolve_runtime",
        lambda self: object(),
    )
    monkeypatch.setattr(
        "backend.app.services.ai_coverage_llm_service.AiCoverageLlmService.analyze_coverage",
        _analyze,
    )


def _mock_test_point_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _analyze(
        self,
        *,
        runtime,
        input_snapshot,
        baseline_points,
        markdown_text,
        prompt_hints,
        has_rule_baseline,
        required_pairs=None,
        enforce_required_pairs=False,
    ):
        self.last_call_trace = {
            "call_mode": "llm",
            "provider": {
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "timeout_seconds": 30,
            },
            "latency_ms": 61,
            "failure_category": "",
            "trace_json": {"request_id": "test-point-route-trace"},
        }
        merged = list(baseline_points)
        if merged:
            merged[0] = {
                **merged[0],
                "reason": "LLM refined point rationale for route smoke coverage.",
                "confidence": 0.92,
            }
        return merged, []

    monkeypatch.setattr(
        "backend.app.services.ai_test_point_llm_service.AiTestPointLlmService.resolve_runtime",
        lambda self: object(),
    )
    monkeypatch.setattr(
        "backend.app.services.ai_test_point_llm_service.AiTestPointLlmService.analyze_points",
        _analyze,
    )


def _mock_assertion_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _analyze(self, runtime, input_snapshot, baseline_suggestions, existing_assertions, has_success_sample):
        self.last_call_trace = {
            "call_mode": "llm",
            "provider": {
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "timeout_seconds": 30,
            },
            "latency_ms": 66,
            "failure_category": "",
            "trace_json": {"request_id": "assertion-route-trace"},
        }
        if not has_success_sample:
            return (
                [
                    {
                        "type": "status_code",
                        "operator": "==",
                        "expected": 200,
                        "enabled": True,
                        "reason": "建议先补一个成功状态码断言，作为新用例的基础草案。",
                        "confidence": 0.84,
                    },
                    {
                        "type": "json_path",
                        "path": "$.code",
                        "operator": "==",
                        "expected": 0,
                        "enabled": True,
                        "reason": "建议预留业务码断言草案，后续可按真实响应再校准。",
                        "confidence": 0.71,
                    },
                ],
                ["当前未发现真实成功响应，本次输出为基于请求结构推断的草案断言。"],
            )
        return (
            [
                {
                    "type": "status_code",
                    "operator": "==",
                    "expected": 200,
                    "enabled": True,
                    "reason": "建议固定成功响应状态码，便于第一时间发现异常返回。",
                    "confidence": 0.97,
                },
                {
                    "type": "json_path",
                    "path": "$.code",
                    "operator": "==",
                    "expected": 0,
                    "enabled": True,
                    "reason": "建议校验业务码字段，确保成功语义稳定。",
                    "confidence": 0.91,
                },
                {
                    "type": "json_path",
                    "path": "$.message",
                    "operator": "contains",
                    "expected": "ok",
                    "enabled": True,
                    "reason": "建议补充响应文案断言，增强返回内容校验。",
                    "confidence": 0.84,
                },
            ],
            [],
        )

    monkeypatch.setattr(
        "backend.app.services.ai_assertion_llm_service.AiAssertionLlmService.resolve_runtime",
        lambda self: object(),
    )
    monkeypatch.setattr(
        "backend.app.services.ai_assertion_llm_service.AiAssertionLlmService.analyze_assertions",
        _analyze,
    )


def _mock_test_data_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _analyze(self, runtime, input_snapshot, baseline_variants, has_rule_baseline):
        self.last_call_trace = {
            "call_mode": "llm",
            "provider": {
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "timeout_seconds": 30,
            },
            "latency_ms": 71,
            "failure_category": "",
            "trace_json": {"request_id": "test-data-route-trace"},
        }
        if not has_rule_baseline:
            return (
                [
                    {
                        "variant_id": "tv_draft_username_empty",
                        "name": "draft_empty_string",
                        "category": "boundary_path",
                        "payload_patch": {"username": ""},
                        "target_fields": ["username"],
                        "reason": "建议先补一个空字符串输入草案，验证基础参数边界。",
                        "suggested_assertions": [{"type": "status_code", "operator": "==", "expected": 400, "enabled": True}],
                        "confidence": 0.72,
                    }
                ],
                ["当前规则未能产出稳定测试数据，本次结果为草案建议。"],
            )
        return (
            [
                *baseline_variants,
                {
                    "variant_id": "tv_profile_age_zero",
                    "name": "zero_boundary",
                    "category": "boundary_path",
                    "payload_patch": {"username": "demo", "profile": {"age": 0}},
                    "target_fields": ["profile.age"],
                    "reason": "建议补充 age=0 的边界输入，增强数值边界覆盖。",
                    "suggested_assertions": [{"type": "status_code", "operator": "==", "expected": 400, "enabled": True}],
                    "confidence": 0.89,
                },
            ],
            [],
        )

    monkeypatch.setattr(
        "backend.app.services.ai_test_data_llm_service.AiTestDataLlmService.resolve_runtime",
        lambda self: object(),
    )
    monkeypatch.setattr(
        "backend.app.services.ai_test_data_llm_service.AiTestDataLlmService.analyze_variants",
        _analyze,
    )


def _mock_mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _analyze(self, runtime, input_snapshot, baseline_templates, has_rule_baseline):
        self.last_call_trace = {
            "call_mode": "llm",
            "provider": {
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "timeout_seconds": 30,
            },
            "latency_ms": 74,
            "failure_category": "",
            "trace_json": {"request_id": "mock-route-trace"},
        }
        if not has_rule_baseline:
            return (
                [
                    {
                        "template_id": "mt_draft_validation_error",
                        "scenario_name": "validation_error",
                        "status_code": 400,
                        "response_template": {"code": 40001, "message": "参数错误"},
                        "mock_rules": [{"method": "POST", "path": "/orders", "status_code": 400}],
                        "reason": "建议预留一个参数错误模板草案，便于前期联调。",
                        "confidence": 0.7,
                    }
                ],
                ["当前规则未能产出稳定 Mock 模板，本次结果为草案建议。"],
            )
        return (
            [
                *baseline_templates,
                {
                    "template_id": "mt_validation_error_post_users_profile",
                    "scenario_name": "validation_error",
                    "status_code": 400,
                    "response_template": {"code": 40001, "message": "参数错误"},
                    "mock_rules": [{"method": "POST", "path": "/users/{user_id}/profile", "status_code": 400}],
                    "reason": "建议补充参数校验失败模板，覆盖更常见的联调异常分支。",
                    "confidence": 0.88,
                },
            ],
            [],
        )

    monkeypatch.setattr(
        "backend.app.services.ai_mock_llm_service.AiMockLlmService.resolve_runtime",
        lambda self: object(),
    )
    monkeypatch.setattr(
        "backend.app.services.ai_mock_llm_service.AiMockLlmService.analyze_templates",
        _analyze,
    )


def _mock_chat_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.ai_provider_registry.AiProviderRegistry.resolve_runtime",
        lambda self: object(),
    )

    def _stream_text(self, *, runtime, system_prompt, messages):
        assert "system tables" in system_prompt
        assert messages
        prompt = messages[-1]["content"]
        assert "Bearer secret" not in prompt
        assert "remove-me" not in prompt
        assert "Read-only project context" in prompt or "Free chat context" in prompt
        return (
            iter([]),
            {
                "call_mode": "llm",
                "provider": {
                    "provider": "openai_compatible",
                    "model": "gpt-5.4",
                    "base_url": "https://example.com",
                    "timeout_seconds": 30,
                },
                "latency_ms": None,
                "failure_category": "",
                "trace_json": {"request_id": "chat-stream-route-trace"},
            },
        )

    def _generate_text(self, *, runtime, system_prompt, messages):
        return (
            "基于当前项目快照，最近失败执行主要集中在权限与鉴权相关场景。",
            {
                "call_mode": "llm",
                "provider": {
                    "provider": "openai_compatible",
                    "model": "gpt-5.4",
                    "base_url": "https://example.com",
                    "timeout_seconds": 30,
                },
                "latency_ms": 320,
                "failure_category": "",
                "trace_json": {"request_id": "chat-fallback-route-trace"},
            },
        )

    monkeypatch.setattr(
        "backend.app.services.ai_client_service.AiClientService.stream_text",
        _stream_text,
    )
    monkeypatch.setattr(
        "backend.app.services.ai_client_service.AiClientService.generate_text",
        _generate_text,
    )


def _build_api_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, sessionmaker]:
    load_model_metadata()
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    monkeypatch.setattr("backend.app.main.bootstrap_database", lambda: None)
    monkeypatch.setattr("backend.app.main.SessionLocal", testing_session_local)

    app = create_application()

    def override_session_scope() -> Generator[Session, None, None]:
        session = testing_session_local()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[session_scope] = override_session_scope
    client = TestClient(app)
    return client, testing_session_local


def _issue_token(factory: sessionmaker, username: str, display_name: str, password: str, role: UserRole) -> str:
    with factory() as session:
        auth_service = AuthService(session)
        user = auth_service.create_user(username, display_name, password, role)
        session.commit()
        auth_session = auth_service.build_session(user)
        session.commit()
        return auth_session.access_token


def _seed_case(factory: sessionmaker, *, with_existing_assertion: bool = False) -> tuple[int, int]:
    with factory() as session:
        workspace = WorkspaceService(session)
        project = workspace.create_project(ProjectCreate(name="AI Seed", description=""))
        suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Suite A", description=""))
        environment = workspace.create_environment(EnvironmentCreate(project_id=project.id, name="dev", base_url="https://example.com"))
        case = workspace.create_case(
            ApiCaseCreate(
                suite_id=suite.id,
                name="Profile",
                method="GET",
                url="/profile",
                assertions_json=[{"type": "status_code", "operator": "==", "expected": 200, "enabled": True}] if with_existing_assertion else [],
            )
        )
        session.commit()
        return case.id, environment.id


def _seed_phase3_case(factory: sessionmaker) -> tuple[int, int]:
    with factory() as session:
        workspace = WorkspaceService(session)
        project = workspace.create_project(ProjectCreate(name="Phase 3 Route Seed", description=""))
        suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Case Prep Suite", description=""))
        environment = workspace.create_environment(
            EnvironmentCreate(
                project_id=project.id,
                name="staging",
                base_url="https://example.com",
                variables_json={"region": "cn", "tenant": "demo", "auth_token": "remove-me"},
            )
        )
        case = workspace.create_case(
            ApiCaseCreate(
                suite_id=suite.id,
                name="Update profile",
                method="POST",
                url="/users/{user_id}/profile?page=1&include=roles",
                headers_json={"Authorization": "Bearer secret", "X-Trace": "trace-001"},
                body_json={"username": "demo", "profile": {"age": 18}, "tags": ["smoke"]},
                metadata_json={"category": "happy_path"},
            )
        )

        success_execution = Execution(
            project_id=project.id,
            suite_id=suite.id,
            environment_id=environment.id,
            scope=ExecutionScope.case,
            status=ExecutionStatus.success,
            target_name=case.name,
            summary_json={"passed": 1},
            error_message="",
        )
        session.add(success_execution)
        session.flush()
        session.add(
            ExecutionItem(
                execution_id=success_execution.id,
                case_id=case.id,
                order_index=1,
                case_name=case.name,
                status="PASS",
                elapsed_ms=12,
                request_json={"method": "POST", "url": case.url, "body": case.body_json},
                response_json={"status_code": 200, "response_json": {"code": 0, "message": "ok"}},
                assertion_results_json=[],
                failure_message="",
            )
        )

        failed_execution = Execution(
            project_id=project.id,
            suite_id=suite.id,
            environment_id=environment.id,
            scope=ExecutionScope.case,
            status=ExecutionStatus.failed,
            target_name=case.name,
            summary_json={"failed": 1},
            error_message="permission denied",
        )
        session.add(failed_execution)
        session.flush()
        session.add(
            ExecutionItem(
                execution_id=failed_execution.id,
                case_id=case.id,
                order_index=1,
                case_name=case.name,
                status="FAIL",
                elapsed_ms=18,
                request_json={"method": "POST", "url": case.url, "body": case.body_json},
                response_json={"status_code": 403, "response_json": {"code": 40301, "message": "permission denied"}},
                assertion_results_json=[],
                failure_message="permission denied",
            )
        )
        session.commit()
        return case.id, environment.id


def _seed_coverage_suite(factory: sessionmaker) -> tuple[int, int]:
    with factory() as session:
        workspace = WorkspaceService(session)
        project = workspace.create_project(ProjectCreate(name="Coverage Seed", description=""))
        suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Coverage Suite", description=""))
        workspace.create_case(
            ApiCaseCreate(
                suite_id=suite.id,
                name="Profile success",
                method="GET",
                url="/profile",
                assertions_json=[
                    {"type": "status_code", "operator": "==", "expected": 200, "enabled": True},
                    {"type": "json_path", "path": "$.code", "operator": "==", "expected": 0, "enabled": True},
                ],
                metadata_json={"category": "happy_path", "priority": "P0", "tags": ["smoke"]},
            )
        )
        workspace.create_case(
            ApiCaseCreate(
                suite_id=suite.id,
                name="Login boundary",
                method="POST",
                url="/login",
                assertions_json=[
                    {"type": "json_path", "path": "$.message", "operator": "contains", "expected": "ok", "enabled": True},
                ],
                metadata_json={"category": "boundary_path", "priority": "P1", "tags": ["auth"]},
            )
        )
        session.commit()
        return project.id, suite.id


def test_ai_copilot_diagnosis_routes_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    case_id, _ = _seed_case(factory)
    token = _issue_token(factory, "tester-ai-diag", "Tester", "Tester#AIDiag2026", UserRole.tester)

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

    with factory() as session:
        execution = ExecutionService(session).run_case_now(case_id, None, None)
        session.commit()
        execution_id = execution.id

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/diagnosis/preview", json={"execution_id": execution_id}, headers=headers)
        history_response = client.get(f"/api/v1/ai-copilot/diagnosis/history?execution_id={execution_id}", headers=headers)

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]
    assert preview_payload["capability"] == "diagnosis"
    assert preview_payload["result"]["diagnosis_category"] == "dependency_timeout"

    assert history_response.status_code == 200
    history_payload = history_response.json()["data"]["items"]
    assert len(history_payload) == 1
    assert history_payload[0]["artifact_id"] == preview_payload["artifact_id"]
    assert history_payload[0]["status"] == "draft"


def test_ai_copilot_report_summary_routes_apply_and_status_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "tester-ai-report", "Tester", "Tester#AIReport2026", UserRole.tester)
    case_id, environment_id = _seed_case(factory)

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": False, "status_code": 500, "elapsed_ms": 11, "response_json": {"ok": False}},
            "assertion_results": [{"type": "status_code", "result": "FAIL", "message": "status mismatch"}],
            "result": "FAIL",
        },
    )
    monkeypatch.setattr(
        "backend.app.services.report_service.ReportGenerator.generate",
        lambda self, run_data, output_dir: {"json": "web_runs/test-route-report.json", "html": "web_runs/test-route-report.html"},
    )

    with factory() as session:
        execution = ExecutionService(session).run_case_now(case_id, environment_id, None)
        session.commit()
        report = session.query(Report).filter(Report.execution_id == execution.id, Report.report_type == "json").one()
        report_id = report.id

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/report-summary/preview", json={"report_id": report_id}, headers=headers)
        artifact_id = preview_response.json()["data"]["artifact_id"]
        apply_response = client.post(f"/api/v1/ai-copilot/report-summary/{artifact_id}/apply", json={}, headers=headers)

    assert preview_response.status_code == 200
    assert apply_response.status_code == 200
    applied_payload = apply_response.json()["data"]
    assert applied_payload["report_id"] == report_id
    assert applied_payload["ai_summary"]["executive_summary"]

    with factory() as session:
        stored_report = session.get(Report, report_id)
        stored_artifact = session.query(AiArtifact).filter(AiArtifact.artifact_id == artifact_id).one()
        assert stored_report is not None
        assert stored_report.metadata_json["ai_summary"]["executive_summary"]
        assert stored_artifact.status == "applied"


def test_ai_copilot_assertion_apply_is_idempotent_for_append(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_assertion_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "tester-ai-assert", "Tester", "Tester#AIAssert2026", UserRole.tester)
    case_id, environment_id = _seed_case(factory, with_existing_assertion=True)

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

    with factory() as session:
        ExecutionService(session).run_case_now(case_id, environment_id, None)
        session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/assertions/preview", json={"case_id": case_id}, headers=headers)
        artifact_id = preview_response.json()["data"]["artifact_id"]
        first_apply_response = client.post(
            f"/api/v1/ai-copilot/assertions/{artifact_id}/apply",
            json={"override_existing": False},
            headers=headers,
        )
        second_apply_response = client.post(
            f"/api/v1/ai-copilot/assertions/{artifact_id}/apply",
            json={"override_existing": False},
            headers=headers,
        )

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]
    assert preview_payload["call_trace"]["call_mode"] == "llm"
    assert first_apply_response.status_code == 200
    assert second_apply_response.status_code == 200

    first_assertions = first_apply_response.json()["data"]["assertions_json"]
    second_assertions = second_apply_response.json()["data"]["assertions_json"]
    assert first_assertions == second_assertions
    assert sum(1 for item in second_assertions if item["type"] == "status_code") == 1
    assert any(item["type"] == "json_path" and item["path"] == "$.code" for item in second_assertions)
    assert any(item["type"] == "json_path" and item["path"] == "$.message" for item in second_assertions)


def test_ai_copilot_assertion_preview_returns_draft_without_execution_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_assertion_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "tester-ai-assert-draft", "Tester", "Tester#AIAssertDraft2026", UserRole.tester)
    case_id, _ = _seed_case(factory, with_existing_assertion=False)

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/assertions/preview", json={"case_id": case_id}, headers=headers)

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]
    assert preview_payload["call_trace"]["call_mode"] == "llm"
    assert len(preview_payload["result"]["suggested_assertions"]) > 0
    assert all(item["confidence"] <= 0.68 for item in preview_payload["result"]["suggested_assertions"])
    assert any("草案" in item["reason"] for item in preview_payload["result"]["suggested_assertions"])
    assert any("未基于真实成功响应验证" in warning for warning in preview_payload["warnings"])


def test_ai_copilot_coverage_routes_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_coverage_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    _, suite_id = _seed_coverage_suite(factory)
    token = _issue_token(factory, "tester-ai-coverage", "Tester", "Tester#AICoverage2026", UserRole.tester)

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/coverage/scan", json={"suite_id": suite_id}, headers=headers)
        history_response = client.get(f"/api/v1/ai-copilot/coverage/history?target_type=suite&target_id={suite_id}", headers=headers)

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]
    assert preview_payload["capability"] == "coverage"
    assert preview_payload["result"]["coverage_score"] == 55
    assert len(preview_payload["result"]["suggested_points"]) > 0
    assert preview_payload["call_trace"]["call_mode"] == "llm"

    assert history_response.status_code == 200
    history_payload = history_response.json()["data"]["items"]
    assert len(history_payload) == 1
    assert history_payload[0]["artifact_id"] == preview_payload["artifact_id"]
    assert history_payload[0]["target_type"] == "suite"
    assert history_payload[0]["status"] == "draft"
    assert history_payload[0]["model"] == "gpt-5.4"


def test_ai_copilot_coverage_routes_support_project_target(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_coverage_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    project_id, _ = _seed_coverage_suite(factory)
    token = _issue_token(factory, "tester-ai-coverage-project", "Tester", "Tester#AICoverageProject2026", UserRole.tester)

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/coverage/scan", json={"project_id": project_id}, headers=headers)
        history_response = client.get(f"/api/v1/ai-copilot/coverage/history?target_type=project&target_id={project_id}", headers=headers)

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]
    assert preview_payload["capability"] == "coverage"
    assert preview_payload["result"]["coverage_score"] > 0

    assert history_response.status_code == 200
    history_payload = history_response.json()["data"]["items"]
    assert len(history_payload) == 1
    assert history_payload[0]["artifact_id"] == preview_payload["artifact_id"]
    assert history_payload[0]["target_type"] == "project"
    assert history_payload[0]["target_id"] == project_id


def test_ai_copilot_test_point_preview_route_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_test_point_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    _, suite_id = _seed_coverage_suite(factory)
    token = _issue_token(factory, "tester-ai-test-point", "Tester", "Tester#AITestPoint2026", UserRole.tester)

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post(
            "/api/v1/ai-copilot/test-points/preview",
            json={"suite_id": suite_id, "markdown_text": "## Auth\nGET /profile\nPOST /login", "prompt_hints": "Focus on core coverage."},
            headers=headers,
        )
        history_response = client.get(f"/api/v1/ai-copilot/test-points/history?target_type=suite&target_id={suite_id}", headers=headers)

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]
    assert preview_payload["capability"] == "test_point"
    assert len(preview_payload["result"]["test_points"]) > 0
    assert any(item["covered_by_existing_cases"] is True for item in preview_payload["result"]["test_points"])

    assert history_response.status_code == 200
    history_payload = history_response.json()["data"]["items"]
    assert len(history_payload) == 1
    assert history_payload[0]["artifact_id"] == preview_payload["artifact_id"]
    assert history_payload[0]["target_type"] == "suite"


def test_ai_copilot_test_points_generate_drafts_route(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_test_point_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    project_id, suite_id = _seed_coverage_suite(factory)
    token = _issue_token(factory, "tester-ai-point-draft", "Tester", "Tester#AIPointDraft2026", UserRole.tester)

    monkeypatch.setattr(
        "backend.app.services.llm_case_generation_service.LlmCaseGenerationService.generate_drafts",
        lambda self, section_title, section_content, runtime, prompt_hints="": (
            [
                {
                    "name": f"{section_title} draft",
                    "method": "GET",
                    "url": "/profile",
                    "description": "from point",
                    "assertions_json": [{"type": "status_code", "operator": "==", "expected": 200, "enabled": True}],
                    "metadata_json": {"category": "happy_path"},
                }
            ],
            [],
        ),
    )

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post(
            "/api/v1/ai-copilot/test-points/preview",
            json={"suite_id": suite_id, "markdown_text": "## Auth\nGET /profile", "prompt_hints": "Focus on core coverage."},
            headers=headers,
        )
        preview_payload = preview_response.json()["data"]
        selected_point_id = preview_payload["result"]["test_points"][0]["id"]
        generate_response = client.post(
            "/api/v1/ai-copilot/test-points/generate-drafts",
            json={
                "artifact_id": preview_payload["artifact_id"],
                "selected_point_ids": [selected_point_id],
                "project_id": project_id,
                "suite_name": "Point Draft Suite",
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "api_key": "test-key",
                "timeout_seconds": 30,
            },
            headers=headers,
        )

    assert preview_response.status_code == 200
    assert generate_response.status_code == 200
    generate_payload = generate_response.json()["data"]
    assert generate_payload["history_id"]
    assert len(generate_payload["drafts"]) == 1
    assert generate_payload["drafts"][0]["source_location"]["test_point_id"] == selected_point_id


def test_ai_copilot_project_test_point_to_draft_mainline(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_coverage_llm(monkeypatch)
    _mock_test_point_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    project_id, _ = _seed_coverage_suite(factory)
    token = _issue_token(factory, "tester-ai-project-design", "Tester", "Tester#AIProjectDesign2026", UserRole.tester)

    monkeypatch.setattr(
        "backend.app.services.llm_case_generation_service.LlmCaseGenerationService.generate_drafts",
        lambda self, section_title, section_content, runtime, prompt_hints="": (
            [
                {
                    "name": f"{section_title} project draft",
                    "method": "GET",
                    "url": "/profile",
                    "description": "from project-level point",
                    "assertions_json": [{"type": "status_code", "operator": "==", "expected": 200, "enabled": True}],
                    "metadata_json": {"category": "happy_path"},
                }
            ],
            [],
        ),
    )

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        coverage_response = client.post("/api/v1/ai-copilot/coverage/scan", json={"project_id": project_id}, headers=headers)
        preview_response = client.post("/api/v1/ai-copilot/test-points/preview", json={"project_id": project_id}, headers=headers)
        preview_payload = preview_response.json()["data"]
        selected_point_id = preview_payload["result"]["test_points"][0]["id"]
        generate_response = client.post(
            "/api/v1/ai-copilot/test-points/generate-drafts",
            json={
                "artifact_id": preview_payload["artifact_id"],
                "selected_point_ids": [selected_point_id],
                "project_id": project_id,
                "suite_name": "Project Point Draft Suite",
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "api_key": "test-key",
                "timeout_seconds": 30,
            },
            headers=headers,
        )
        history_response = client.get(f"/api/v1/ai-copilot/test-points/history?target_type=project&target_id={project_id}", headers=headers)

    assert coverage_response.status_code == 200
    assert preview_response.status_code == 200
    assert generate_response.status_code == 200
    generate_payload = generate_response.json()["data"]
    assert generate_payload["history_id"]
    assert generate_payload["drafts"][0]["source_location"]["test_point_id"] == selected_point_id

    history_payload = history_response.json()["data"]["items"]
    assert len(history_payload) == 1
    assert history_payload[0]["target_type"] == "project"
    assert history_payload[0]["artifact_id"] == preview_payload["artifact_id"]


def test_ai_artifact_lineage_route_returns_bridge_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    project_id, suite_id = _seed_coverage_suite(factory)
    token = _issue_token(factory, "tester-ai-lineage", "Tester", "Tester#AILineage2026", UserRole.tester)

    with factory() as session:
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
        session.commit()
        artifact_id = artifact.artifact_id

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        response = client.get(f"/api/v1/ai-copilot/artifacts/{artifact_id}/lineage", headers=headers)

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["root_artifact_id"] == artifact_id
    assert [item["resource_type"] for item in payload["items"]] == ["ai_artifact", "ai_case_history"]
    assert payload["items"][1]["link_type"] == "generated_history"


def test_execution_route_accepts_case_preparation_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    with factory() as session:
        workspace = WorkspaceService(session)
        project = workspace.create_project(ProjectCreate(name="Exec Prep Project", description=""))
        suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Exec Prep Suite", description=""))
        api_case = workspace.create_case(
            ApiCaseCreate(
                suite_id=suite.id,
                name="Prepared case",
                method="POST",
                url="/users/{user_id}/profile",
                body_json={"username": "demo", "profile": {"age": 18}},
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
                        }
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
        case_id = api_case.id
    token = _issue_token(factory, "tester-execution-prep", "Tester", "Tester#ExecPrep2026", UserRole.tester)

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 5, "response_json": {"ok": True}},
            "assertion_results": [],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        response = client.post(
            "/api/v1/executions",
            json={
                "scope": "case",
                "target_id": case_id,
                "ai_preparation": {
                    "selected_test_data_variant_ids": ["tv_boundary_age"],
                    "selected_mock_template_ids": ["mt_permission_denied"],
                },
            },
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["summary_json"]["ai_preparation"]["selected_variant_ids"] == ["tv_boundary_age"]
    assert payload["summary_json"]["ai_preparation"]["selected_template_ids"] == ["mt_permission_denied"]
    assert payload["items"][0]["request_json"]["body"]["profile"]["age"] == 19


def test_ai_route_audit_log_includes_failure_category(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    case_id, _ = _seed_phase3_case(factory)
    token = _issue_token(factory, "tester-ai-audit-trace", "Tester", "Tester#AIAuditTrace2026", UserRole.tester)

    class _FakeCopilot:
        def preview(self, **kwargs):
            from backend.app.schemas.ai_copilot import AiArtifactCapability, AiArtifactStatus, AiCopilotPreviewResponse

            return AiCopilotPreviewResponse(
                artifact_id="artifact_trace_001",
                capability=AiArtifactCapability.test_data,
                status=AiArtifactStatus.draft,
                warnings=[],
                result={"data_variants": []},
                call_trace={
                    "call_mode": "llm",
                    "provider": {
                        "provider": "openai_compatible",
                        "model": "gpt-5.4",
                        "base_url": "https://example.com",
                        "timeout_seconds": 30,
                    },
                    "latency_ms": 450,
                    "failure_category": "provider_timeout",
                    "trace_json": {"request_id": "trace_route_001"},
                },
            )

    monkeypatch.setattr("backend.app.api.routes.ai_copilot._build_copilot_service", lambda session: _FakeCopilot())

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        response = client.post("/api/v1/ai-copilot/test-data/preview", json={"case_id": case_id}, headers=headers)

    assert response.status_code == 200
    with factory() as session:
        latest_log = session.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert latest_log is not None
        assert latest_log.details_json["failure_category"] == "provider_timeout"
        assert latest_log.details_json["call_mode"] == "llm"


def test_ai_chat_stream_route_uses_project_snapshot_and_masks_sensitive_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_chat_stream(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    case_id, _ = _seed_phase3_case(factory)
    token = _issue_token(factory, "tester-ai-chat", "Tester", "Tester#AIChat2026", UserRole.tester)

    with factory() as session:
        case = session.get(ApiCase, case_id)
        assert case is not None
        project_id = case.suite.project_id

    headers = {"Authorization": f"Bearer {token}"}
    with client.stream(
        "POST",
        "/api/v1/ai-copilot/chat/stream",
        json={
            "project_id": project_id,
            "page_path": "/workspace",
            "page_title": "工作台",
            "messages": [{"role": "user", "content": "最近失败执行集中在哪些场景？"}],
        },
        headers=headers,
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: meta" in body
    assert "event: delta" in body
    assert "event: done" in body
    assert "stream_fallback" in body


def test_ai_chat_stream_route_supports_free_mode_without_project_context(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_chat_stream(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "tester-ai-chat-free", "Tester", "Tester#AIChatFree2026", UserRole.tester)

    headers = {"Authorization": f"Bearer {token}"}
    with client.stream(
        "POST",
        "/api/v1/ai-copilot/chat/stream",
        json={
            "chat_mode": "free",
            "page_path": "/workspace",
            "page_title": "工作台",
            "messages": [{"role": "user", "content": "帮我解释什么是冒烟测试"}],
        },
        headers=headers,
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"chat_mode": "free"' in body
    assert "event: meta" in body
    assert "event: delta" in body
    assert "event: done" in body


def test_ai_test_data_web_routes_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_test_data_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    case_id, _ = _seed_phase3_case(factory)
    token = _issue_token(factory, "tester-ai-test-data", "Tester", "Tester#AITestData2026", UserRole.tester)

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/test-data/preview", json={"case_id": case_id}, headers=headers)
        preview_payload = preview_response.json()["data"]
        history_response = client.get(f"/api/v1/ai-copilot/test-data/history?case_id={case_id}", headers=headers)
        artifact_id = preview_payload["artifact_id"]
        selected_variant_ids = [item["variant_id"] for item in preview_payload["result"]["data_variants"][:2]]
        apply_response = client.post(
            f"/api/v1/ai-copilot/test-data/{artifact_id}/apply",
            json={"selected_variant_ids": selected_variant_ids, "override_existing": False},
            headers=headers,
        )
        export_response = client.get(f"/api/v1/ai-copilot/test-data/{artifact_id}/export", headers=headers)

    assert preview_response.status_code == 200
    assert preview_payload["capability"] == "test_data"
    assert len(preview_payload["result"]["data_variants"]) >= 3
    assert preview_payload["call_trace"]["call_mode"] == "llm"

    assert history_response.status_code == 200
    history_payload = history_response.json()["data"]["items"]
    assert len(history_payload) == 1
    assert history_payload[0]["artifact_id"] == artifact_id
    assert history_payload[0]["status"] == "draft"
    assert history_payload[0]["model"] == "gpt-5.4"

    assert apply_response.status_code == 200
    applied_payload = apply_response.json()["data"]
    assert [item["variant_id"] for item in applied_payload["metadata_json"]["ai_test_data_variants"]] == selected_variant_ids

    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("application/json")
    export_payload = json.loads(export_response.content.decode("utf-8"))
    assert export_payload["artifact_id"] == artifact_id
    assert export_payload["case_id"] == case_id
    assert len(export_payload["data_variants"]) >= 3


def test_ai_test_data_apply_is_idempotent_for_append(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_test_data_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    case_id, _ = _seed_phase3_case(factory)
    token = _issue_token(factory, "tester-ai-test-data-append", "Tester", "Tester#AITestDataAppend2026", UserRole.tester)

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/test-data/preview", json={"case_id": case_id}, headers=headers)
        preview_payload = preview_response.json()["data"]
        artifact_id = preview_payload["artifact_id"]
        selected_variant_ids = [item["variant_id"] for item in preview_payload["result"]["data_variants"][:2]]
        first_apply_response = client.post(
            f"/api/v1/ai-copilot/test-data/{artifact_id}/apply",
            json={"selected_variant_ids": selected_variant_ids, "override_existing": False},
            headers=headers,
        )
        second_apply_response = client.post(
            f"/api/v1/ai-copilot/test-data/{artifact_id}/apply",
            json={"selected_variant_ids": selected_variant_ids, "override_existing": False},
            headers=headers,
        )

    assert preview_response.status_code == 200
    assert first_apply_response.status_code == 200
    assert second_apply_response.status_code == 200

    first_variants = first_apply_response.json()["data"]["metadata_json"]["ai_test_data_variants"]
    second_variants = second_apply_response.json()["data"]["metadata_json"]["ai_test_data_variants"]
    assert first_variants == second_variants
    assert [item["variant_id"] for item in second_variants] == selected_variant_ids


def test_ai_test_data_preview_returns_draft_when_rule_baseline_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_test_data_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "tester-ai-test-data-draft", "Tester", "Tester#AITestDataDraft2026", UserRole.tester)
    case_id, _ = _seed_case(factory, with_existing_assertion=False)

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/test-data/preview", json={"case_id": case_id}, headers=headers)

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]
    assert preview_payload["call_trace"]["call_mode"] == "llm"
    assert len(preview_payload["result"]["data_variants"]) == 1
    assert preview_payload["result"]["data_variants"][0]["confidence"] <= 0.62
    assert any("可信度较低" in warning for warning in preview_payload["warnings"])


def test_ai_mock_web_routes_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_mock_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    case_id, _ = _seed_phase3_case(factory)
    token = _issue_token(factory, "tester-ai-mock", "Tester", "Tester#AIMock2026", UserRole.tester)

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/mock/preview", json={"case_id": case_id}, headers=headers)
        preview_payload = preview_response.json()["data"]
        history_response = client.get(f"/api/v1/ai-copilot/mock/history?case_id={case_id}", headers=headers)
        artifact_id = preview_payload["artifact_id"]
        selected_template_ids = [item["template_id"] for item in preview_payload["result"]["mock_templates"][:2]]
        apply_response = client.post(
            f"/api/v1/ai-copilot/mock/{artifact_id}/apply",
            json={"selected_template_ids": selected_template_ids, "override_existing": False},
            headers=headers,
        )
        export_response = client.get(f"/api/v1/ai-copilot/mock/{artifact_id}/export", headers=headers)

    assert preview_response.status_code == 200
    assert preview_payload["capability"] == "mock"
    assert len(preview_payload["result"]["mock_templates"]) >= 2
    assert preview_payload["call_trace"]["call_mode"] == "llm"

    assert history_response.status_code == 200
    history_payload = history_response.json()["data"]["items"]
    assert len(history_payload) == 1
    assert history_payload[0]["artifact_id"] == artifact_id
    assert history_payload[0]["status"] == "draft"
    assert history_payload[0]["model"] == "gpt-5.4"

    assert apply_response.status_code == 200
    applied_payload = apply_response.json()["data"]
    assert [item["template_id"] for item in applied_payload["metadata_json"]["ai_mock_templates"]] == selected_template_ids

    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("application/json")
    export_payload = json.loads(export_response.content.decode("utf-8"))
    assert export_payload["artifact_id"] == artifact_id
    assert export_payload["case_id"] == case_id
    assert len(export_payload["mock_templates"]) >= 2


def test_ai_mock_apply_is_idempotent_for_append(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_mock_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    case_id, _ = _seed_phase3_case(factory)
    token = _issue_token(factory, "tester-ai-mock-append", "Tester", "Tester#AIMockAppend2026", UserRole.tester)

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/mock/preview", json={"case_id": case_id}, headers=headers)
        preview_payload = preview_response.json()["data"]
        artifact_id = preview_payload["artifact_id"]
        selected_template_ids = [item["template_id"] for item in preview_payload["result"]["mock_templates"][:2]]
        first_apply_response = client.post(
            f"/api/v1/ai-copilot/mock/{artifact_id}/apply",
            json={"selected_template_ids": selected_template_ids, "override_existing": False},
            headers=headers,
        )
        second_apply_response = client.post(
            f"/api/v1/ai-copilot/mock/{artifact_id}/apply",
            json={"selected_template_ids": selected_template_ids, "override_existing": False},
            headers=headers,
        )

    assert preview_response.status_code == 200
    assert first_apply_response.status_code == 200
    assert second_apply_response.status_code == 200

    first_templates = first_apply_response.json()["data"]["metadata_json"]["ai_mock_templates"]
    second_templates = second_apply_response.json()["data"]["metadata_json"]["ai_mock_templates"]
    assert first_templates == second_templates
    assert [item["template_id"] for item in second_templates] == selected_template_ids


def test_ai_mock_preview_returns_draft_when_rule_baseline_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_mock_llm(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "tester-ai-mock-draft", "Tester", "Tester#AIMockDraft2026", UserRole.tester)
    case_id, _ = _seed_case(factory, with_existing_assertion=False)

    headers = {"Authorization": f"Bearer {token}"}
    with client:
        preview_response = client.post("/api/v1/ai-copilot/mock/preview", json={"case_id": case_id}, headers=headers)

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]
    assert preview_payload["call_trace"]["call_mode"] == "llm"
    assert len(preview_payload["result"]["mock_templates"]) == 1
    assert preview_payload["result"]["mock_templates"][0]["confidence"] <= 0.64
    assert any("可信度较低" in warning for warning in preview_payload["warnings"])
