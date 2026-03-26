from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.base import Base
from backend.app.models.execution import Execution, ExecutionItem, ExecutionScope, ExecutionStatus
from backend.app.schemas.ai_copilot import (
    AiArtifactCapability,
    AiArtifactStatus,
    AiArtifactTargetType,
    AiCopilotPreviewResponse,
    AiMockApplyRequest,
    AiMockPreviewRequest,
    AiMockResult,
    AiTestPointResult,
    AiTestDataApplyRequest,
    AiTestDataPreviewRequest,
    AiTestDataResult,
)
from backend.app.repositories.ai_artifact_repository import AiArtifactRepository
from backend.app.schemas.workspace import ApiCaseCreate, EnvironmentCreate, ProjectCreate, SuiteCreate
from backend.app.services.ai_context_assembler import AiContextAssembler
from backend.app.services.ai_copilot_service import AiCopilotService
from backend.app.services.ai_mock_service import AiMockService
from backend.app.services.ai_mock_template_seed_service import AiMockTemplateSeedService
from backend.app.services.ai_test_data_service import AiTestDataService
from backend.app.services.ai_test_data_seed_service import AiTestDataSeedService
from backend.app.services.ai_test_point_service import AiTestPointService
from backend.app.services.workspace_service import WorkspaceService


class _FakeTestDataLlmService:
    def __init__(self) -> None:
        self.last_call_trace = {
            "call_mode": "llm",
            "provider": {
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "timeout_seconds": 30,
            },
            "latency_ms": 87,
            "failure_category": "",
            "trace_json": {"request_id": "test-data-phase3-trace"},
        }

    def resolve_runtime(self):
        return object()

    def analyze_variants(self, *, runtime, input_snapshot, baseline_variants, has_rule_baseline):
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


class _FakeMockLlmService:
    def __init__(self) -> None:
        self.last_call_trace = {
            "call_mode": "llm",
            "provider": {
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "timeout_seconds": 30,
            },
            "latency_ms": 92,
            "failure_category": "",
            "trace_json": {"request_id": "mock-phase3-trace"},
        }

    def resolve_runtime(self):
        return object()

    def analyze_templates(self, *, runtime, input_snapshot, baseline_templates, has_rule_baseline):
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


class _FakeTestPointLlmService:
    def __init__(self) -> None:
        self.last_call_trace = {
            "call_mode": "llm",
            "provider": {
                "provider": "openai_compatible",
                "model": "gpt-5.4",
                "base_url": "https://example.com",
                "timeout_seconds": 30,
            },
            "latency_ms": 64,
            "failure_category": "",
            "trace_json": {"request_id": "test-point-phase3-trace"},
        }

    def resolve_runtime(self):
        return object()

    def analyze_points(
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
        if not has_rule_baseline:
            return (
                [
                    {
                        "id": "tp_post_orders_happy_path",
                        "title": "POST /orders happy_path",
                        "category": "happy_path",
                        "risk_level": "high",
                        "reason": "low-confidence draft point inferred from the provided design context.",
                        "covered_by_existing_cases": False,
                        "suggested_case_count": 1,
                        "confidence": 0.71,
                    }
                ],
                ["Low confidence draft output. Please review before generating drafts."],
            )
        return (
            [
                *baseline_points,
                {
                    "id": "tp_get_profile_negative_path",
                    "title": "GET /profile negative_path",
                    "category": "negative_path",
                    "risk_level": "medium",
                    "reason": "Token expiry and permission failures are worth keeping visible in regression coverage.",
                    "covered_by_existing_cases": True,
                    "suggested_case_count": 2,
                    "confidence": 0.91,
                },
            ],
            [],
        )


def _make_test_data_service(session: Session) -> AiTestDataService:
    return AiTestDataService(session, llm_service=_FakeTestDataLlmService())


def _make_mock_service(session: Session) -> AiMockService:
    return AiMockService(session, llm_service=_FakeMockLlmService())


def _make_test_point_service(session: Session) -> AiTestPointService:
    return AiTestPointService(session, llm_service=_FakeTestPointLlmService())


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def _seed_case_context_workspace(session: Session) -> tuple[int, int]:
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Phase 3 Project", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Case Prep Suite", description=""))
    environment = workspace.create_environment(
        EnvironmentCreate(
            project_id=project.id,
            name="staging",
            base_url="https://example.com",
            variables_json={"region": "cn", "tenant": "demo", "auth_token": "remove-me"},
        )
    )
    api_case = workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Update profile",
            method="POST",
            url="/users/{user_id}/profile?page=1&include=roles",
            headers_json={"Authorization": "Bearer secret", "X-Trace": "trace-001", "Cookie": "session=secret"},
            body_json={
                "username": "demo",
                "password": "secret-pass",
                "profile": {"age": 18, "tags": ["smoke"]},
            },
            assertions_json=[{"type": "status_code", "operator": "==", "expected": 200, "enabled": True}],
            metadata_json={"category": "happy_path", "priority": "P0", "owner": "qa", "token": "drop-me"},
        )
    )

    success_execution = Execution(
        project_id=project.id,
        suite_id=suite.id,
        environment_id=environment.id,
        scope=ExecutionScope.case,
        status=ExecutionStatus.success,
        target_name=api_case.name,
        summary_json={"passed": 1},
        error_message="",
    )
    session.add(success_execution)
    session.flush()
    session.add(
        ExecutionItem(
            execution_id=success_execution.id,
            case_id=api_case.id,
            order_index=1,
            case_name=api_case.name,
            status="PASS",
            elapsed_ms=12,
            request_json={
                "method": "POST",
                "url": "/users/42/profile?page=1&include=roles",
                "headers": {"Authorization": "Bearer secret", "X-Trace": "trace-001"},
                "body": {"username": "demo", "password": "secret-pass", "profile": {"age": 18}},
            },
            response_json={
                "status_code": 200,
                "headers": {"Set-Cookie": "session=rotated", "X-Request-Id": "req-1"},
                "response_json": {"code": 0, "message": "ok", "data": {"user_id": 42, "token": "mask-me"}},
            },
            assertion_results_json=[{"type": "status_code", "result": "PASS"}],
            failure_message="",
        )
    )

    failed_execution = Execution(
        project_id=project.id,
        suite_id=suite.id,
        environment_id=environment.id,
        scope=ExecutionScope.case,
        status=ExecutionStatus.failed,
        target_name=api_case.name,
        summary_json={"failed": 1},
        error_message="permission denied",
    )
    session.add(failed_execution)
    session.flush()
    session.add(
        ExecutionItem(
            execution_id=failed_execution.id,
            case_id=api_case.id,
            order_index=1,
            case_name=api_case.name,
            status="FAIL",
            elapsed_ms=20,
            request_json={
                "method": "POST",
                "url": "/users/42/profile?page=1&include=roles",
                "headers": {"Cookie": "session=secret", "X-Trace": "trace-002"},
                "body": {"username": "demo", "password": "secret-pass", "profile": {"age": 18}},
            },
            response_json={
                "status_code": 403,
                "headers": {"Set-Cookie": "session=expired"},
                "response_json": {"code": 40301, "message": "permission denied"},
            },
            assertion_results_json=[{"type": "status_code", "result": "FAIL"}],
            failure_message="permission denied",
        )
    )
    session.commit()
    return api_case.id, environment.id


def test_ai_copilot_capability_enum_includes_test_data_and_mock():
    capability_values = {item.value for item in AiArtifactCapability}

    assert "test_data" in capability_values
    assert "mock" in capability_values


def test_ai_test_point_preview_merges_rule_baseline_with_llm_guidance():
    session = _make_session()
    service = _make_test_point_service(session)

    result = service.generate_preview(
        {
            "capability": "test_point",
            "target_type": "suite",
            "target_id": 1,
            "enable_llm": True,
            "markdown_text": "GET /profile",
            "prompt_hints": "Keep auth-adjacent risks visible.",
            "input_snapshot": {
                "case_summary": {
                    "unique_endpoints": [{"method": "GET", "path": "/profile"}],
                },
                "cases": [
                    {
                        "method": "GET",
                        "url": "/profile",
                        "metadata_json": {"category": "negative_path"},
                    }
                ],
            },
        }
    )

    payload = AiTestPointResult.model_validate(result["result"])
    point = next(item for item in payload.test_points if item.id == "tp_get_profile_negative_path")

    assert result["call_trace"]["call_mode"] == "llm"
    assert point.confidence == 0.91
    assert "Token expiry" in point.reason


def test_ai_test_point_preview_marks_draft_points_low_confidence_without_rule_baseline():
    session = _make_session()
    service = _make_test_point_service(session)

    result = service.generate_preview(
        {
            "capability": "test_point",
            "target_type": "suite",
            "target_id": 999,
            "enable_llm": True,
            "markdown_text": "",
            "prompt_hints": "Focus on a tiny draft.",
            "input_snapshot": {},
        }
    )

    payload = AiTestPointResult.model_validate(result["result"])

    assert len(payload.test_points) == 1
    assert payload.test_points[0].confidence <= 0.62
    assert "low-confidence" in payload.test_points[0].reason
    assert any("low confidence" in warning.lower() for warning in result["warnings"])


def test_ai_test_data_preview_response_contract():
    preview_request = AiTestDataPreviewRequest(case_id=101)
    apply_request = AiTestDataApplyRequest(selected_variant_ids=["tv_required_missing"], override_existing=False)
    result = AiTestDataResult.model_validate(
        {
            "data_variants": [
                {
                    "variant_id": "tv_required_missing",
                    "name": "required_field_missing",
                    "category": "negative_path",
                    "payload_patch": {"username": ""},
                    "target_fields": ["username"],
                    "reason": "required field should be blank to verify validation",
                    "suggested_assertions": [
                        {"type": "status_code", "operator": "==", "expected": 400, "enabled": True}
                    ],
                }
            ]
        }
    )

    preview = AiCopilotPreviewResponse(
        artifact_id="artifact_td_001",
        capability=AiArtifactCapability.test_data,
        status=AiArtifactStatus.draft,
        warnings=[],
        result=result.model_dump(),
    )

    assert preview_request.case_id == 101
    assert apply_request.selected_variant_ids == ["tv_required_missing"]
    assert preview.capability == AiArtifactCapability.test_data
    assert preview.result["data_variants"][0]["category"] == "negative_path"
    assert preview.result["data_variants"][0]["target_fields"] == ["username"]


def test_ai_mock_preview_response_contract():
    preview_request = AiMockPreviewRequest(case_id=202)
    apply_request = AiMockApplyRequest(selected_template_ids=["mt_login_permission_denied"], override_existing=True)
    result = AiMockResult.model_validate(
        {
            "mock_templates": [
                {
                    "template_id": "mt_login_permission_denied",
                    "scenario_name": "login_permission_denied",
                    "status_code": 403,
                    "response_template": {"code": 40301, "message": "permission denied"},
                    "mock_rules": [{"method": "POST", "path": "/login", "status_code": 403}],
                    "reason": "permission branch is hard to reproduce against unstable downstreams",
                }
            ]
        }
    )

    preview = AiCopilotPreviewResponse(
        artifact_id="artifact_mock_001",
        capability=AiArtifactCapability.mock,
        status=AiArtifactStatus.draft,
        warnings=["当前 AI Mock 仍以导出模板为主，不会直接启用 runtime mock。"],
        result=result.model_dump(),
    )

    assert preview_request.case_id == 202
    assert apply_request.override_existing is True
    assert preview.capability == AiArtifactCapability.mock
    assert preview.warnings == ["当前 AI Mock 仍以导出模板为主，不会直接启用 runtime mock。"]
    assert preview.result["mock_templates"][0]["status_code"] == 403
    assert preview.result["mock_templates"][0]["mock_rules"][0]["path"] == "/login"


def test_case_context_contains_environment_variables_and_recent_execution_samples():
    session = _make_session()
    case_id, environment_id = _seed_case_context_workspace(session)

    context = AiContextAssembler(session).build_case_context(case_id)

    assert context["case_id"] == case_id
    assert context["project_name"] == "Phase 3 Project"
    assert context["suite_name"] == "Case Prep Suite"
    assert context["environments"] == [
        {
            "environment_id": environment_id,
            "name": "staging",
            "base_url": "https://example.com",
            "variables_json": {"region": "cn", "tenant": "demo"},
        }
    ]
    assert context["recent_success_sample"] is not None
    assert context["recent_failure_sample"] is not None


def test_case_context_extracts_request_shape_for_test_data():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)

    context = AiContextAssembler(session).build_case_context(case_id)

    assert context["request_shape"]["path_params"] == ["user_id"]
    assert context["request_shape"]["query_params"] == ["include", "page"]
    assert "username" in context["request_shape"]["body_field_paths"]
    assert "profile.age" in context["request_shape"]["body_field_paths"]
    assert "password" not in context["request_shape"]["body_field_paths"]


def test_case_context_extracts_response_shape_for_mock():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)

    context = AiContextAssembler(session).build_case_context(case_id)

    assert context["response_shape"]["status_codes"] == [200, 403]
    assert context["response_shape"]["top_level_keys"] == ["code", "data", "message"]
    assert context["response_shape"]["success_sample"]["status_code"] == 200
    assert context["response_shape"]["failure_sample"]["status_code"] == 403


def test_case_context_sanitizes_sensitive_fields_before_ai():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)

    context = AiContextAssembler(session).build_case_context(case_id)

    assert "Authorization" not in context["headers_json"]
    assert "Cookie" not in context["headers_json"]
    assert "password" not in context["body_json"]
    assert "token" not in context["metadata_json"]
    assert "auth_token" not in context["environments"][0]["variables_json"]
    assert "Authorization" not in context["recent_success_sample"]["request"]["headers"]
    assert "Set-Cookie" not in context["recent_success_sample"]["response"]["headers"]


def test_test_data_seed_service_extracts_required_and_boundary_variants():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    context = AiContextAssembler(session).build_case_context(case_id)

    result = AiTestDataSeedService().build_result(context)
    variants = {item.name: item for item in result.data_variants}

    assert "required_field_missing" in variants
    assert "empty_string" in variants
    assert "numeric_boundary" in variants
    assert variants["required_field_missing"].target_fields == ["username"]
    assert variants["required_field_missing"].payload_patch["username"] is None
    assert variants["numeric_boundary"].payload_patch["profile"]["age"] == 19


def test_test_data_seed_service_uses_recent_success_sample_as_baseline():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    context = AiContextAssembler(session).build_case_context(case_id)

    result = AiTestDataSeedService().build_result(context)
    variants = {item.name: item for item in result.data_variants}

    assert variants["empty_string"].payload_patch["username"] == ""
    assert variants["empty_string"].payload_patch["profile"]["age"] == 18
    assert variants["invalid_type"].payload_patch["profile"]["age"] == "invalid_type"


def test_test_data_seed_service_is_deterministic_without_llm():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    context = AiContextAssembler(session).build_case_context(case_id)
    service = AiTestDataSeedService()

    first = service.build_result(context)
    second = service.build_result(context)

    assert first.model_dump() == second.model_dump()


def test_ai_test_data_preview_persists_artifact():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    api_case = WorkspaceService(session).get_case(case_id)
    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_data.value: _make_test_data_service(session).generate_preview},
    )

    preview = service.preview(
        capability=AiArtifactCapability.test_data,
        target_type=AiArtifactTargetType.case,
        target_id=case_id,
        project_id=api_case.suite.project_id,
        suite_id=api_case.suite_id,
        case_id=case_id,
    )
    stored = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)

    assert preview.capability == AiArtifactCapability.test_data
    assert len(preview.result["data_variants"]) >= 3
    assert preview.call_trace is not None
    assert preview.call_trace.call_mode == "llm"
    assert stored is not None
    assert stored.capability == AiArtifactCapability.test_data.value
    assert stored.target_type == AiArtifactTargetType.case.value
    assert stored.case_id == case_id
    assert stored.model == "gpt-5.4"


def test_ai_test_data_apply_appends_variants_to_case_metadata():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    workspace = WorkspaceService(session)
    api_case = workspace.get_case(case_id)
    api_case.metadata_json = {
        **(api_case.metadata_json or {}),
        "ai_test_data_variants": [{"variant_id": "baseline", "name": "existing_variant"}],
    }
    workspace.save_case(api_case)
    session.commit()

    copilot = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_data.value: _make_test_data_service(session).generate_preview},
    )
    preview = copilot.preview(
        capability=AiArtifactCapability.test_data,
        target_type=AiArtifactTargetType.case,
        target_id=case_id,
        project_id=api_case.suite.project_id,
        suite_id=api_case.suite_id,
        case_id=case_id,
    )
    selected_variant_ids = [item["variant_id"] for item in preview.result["data_variants"][:2]]

    saved_case = _make_test_data_service(session).apply_artifact(
        preview.artifact_id,
        selected_variant_ids=selected_variant_ids,
        override_existing=False,
    )
    stored_artifact = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)
    stored_variants = saved_case.metadata_json["ai_test_data_variants"]

    assert len(stored_variants) == 3
    assert stored_variants[0]["variant_id"] == "baseline"
    assert [item["variant_id"] for item in stored_variants[1:]] == selected_variant_ids
    assert stored_artifact is not None
    assert stored_artifact.status == AiArtifactStatus.applied.value


def test_ai_test_data_apply_override_replaces_existing_variants():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    workspace = WorkspaceService(session)
    api_case = workspace.get_case(case_id)
    api_case.metadata_json = {
        **(api_case.metadata_json or {}),
        "ai_test_data_variants": [{"variant_id": "baseline", "name": "existing_variant"}],
    }
    workspace.save_case(api_case)
    session.commit()

    copilot = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_data.value: _make_test_data_service(session).generate_preview},
    )
    preview = copilot.preview(
        capability=AiArtifactCapability.test_data,
        target_type=AiArtifactTargetType.case,
        target_id=case_id,
        project_id=api_case.suite.project_id,
        suite_id=api_case.suite_id,
        case_id=case_id,
    )
    selected_variant_id = preview.result["data_variants"][0]["variant_id"]

    saved_case = _make_test_data_service(session).apply_artifact(
        preview.artifact_id,
        selected_variant_ids=[selected_variant_id],
        override_existing=True,
    )

    assert saved_case.metadata_json["ai_test_data_variants"] == [preview.result["data_variants"][0]]


def test_ai_test_data_export_returns_json_bundle():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    api_case = WorkspaceService(session).get_case(case_id)
    preview = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_data.value: _make_test_data_service(session).generate_preview},
    ).preview(
        capability=AiArtifactCapability.test_data,
        target_type=AiArtifactTargetType.case,
        target_id=case_id,
        project_id=api_case.suite.project_id,
        suite_id=api_case.suite_id,
        case_id=case_id,
    )

    bundle = _make_test_data_service(session).export_artifact(preview.artifact_id)

    assert bundle["artifact_id"] == preview.artifact_id
    assert bundle["case_id"] == case_id
    assert bundle["capability"] == "test_data"
    assert len(bundle["data_variants"]) >= 3


def test_ai_test_data_preview_returns_draft_variants_without_rule_baseline():
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Draft Test Data", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Draft Suite", description=""))
    api_case = workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Draft case", method="POST", url="/orders"))
    session.commit()

    preview = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.test_data.value: _make_test_data_service(session).generate_preview},
    ).preview(
        capability=AiArtifactCapability.test_data,
        target_type=AiArtifactTargetType.case,
        target_id=api_case.id,
        project_id=project.id,
        suite_id=suite.id,
        case_id=api_case.id,
    )

    assert preview.call_trace is not None
    assert preview.call_trace.call_mode == "llm"
    assert len(preview.result["data_variants"]) == 1
    assert preview.result["data_variants"][0]["confidence"] <= 0.62
    assert "草案" in preview.result["data_variants"][0]["reason"]
    assert any("可信度较低" in warning for warning in preview.warnings)


def test_mock_seed_service_extracts_response_templates_from_history():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    context = AiContextAssembler(session).build_case_context(case_id)

    result = AiMockTemplateSeedService().build_result(context)
    templates = {item.scenario_name: item for item in result.mock_templates}

    assert "happy_path" in templates
    assert "permission_denied" in templates
    assert templates["happy_path"].response_template["code"] == 0
    assert templates["permission_denied"].response_template["message"] == "permission denied"


def test_mock_seed_service_builds_status_and_path_rules():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    context = AiContextAssembler(session).build_case_context(case_id)

    result = AiMockTemplateSeedService().build_result(context)
    rules_by_scenario = {item.scenario_name: item.mock_rules[0] for item in result.mock_templates}

    assert rules_by_scenario["happy_path"]["method"] == "POST"
    assert rules_by_scenario["happy_path"]["path"] == "/users/{user_id}/profile"
    assert rules_by_scenario["happy_path"]["status_code"] == 200
    assert rules_by_scenario["permission_denied"]["status_code"] == 403


def test_mock_seed_service_is_deterministic_without_llm():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    context = AiContextAssembler(session).build_case_context(case_id)
    service = AiMockTemplateSeedService()

    first = service.build_result(context)
    second = service.build_result(context)

    assert first.model_dump() == second.model_dump()


def test_ai_mock_preview_persists_artifact():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    api_case = WorkspaceService(session).get_case(case_id)
    service = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.mock.value: _make_mock_service(session).generate_preview},
    )

    preview = service.preview(
        capability=AiArtifactCapability.mock,
        target_type=AiArtifactTargetType.case,
        target_id=case_id,
        project_id=api_case.suite.project_id,
        suite_id=api_case.suite_id,
        case_id=case_id,
    )
    stored = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)

    assert preview.capability == AiArtifactCapability.mock
    assert len(preview.result["mock_templates"]) >= 2
    assert preview.call_trace is not None
    assert preview.call_trace.call_mode == "llm"
    assert stored is not None
    assert stored.capability == AiArtifactCapability.mock.value
    assert stored.target_type == AiArtifactTargetType.case.value
    assert stored.case_id == case_id
    assert stored.model == "gpt-5.4"


def test_ai_mock_preview_returns_draft_templates_without_rule_baseline():
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Draft Mock", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Draft Suite", description=""))
    api_case = workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Draft case", method="POST", url="/orders"))
    session.commit()

    preview = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.mock.value: _make_mock_service(session).generate_preview},
    ).preview(
        capability=AiArtifactCapability.mock,
        target_type=AiArtifactTargetType.case,
        target_id=api_case.id,
        project_id=project.id,
        suite_id=suite.id,
        case_id=api_case.id,
    )

    assert preview.call_trace is not None
    assert preview.call_trace.call_mode == "llm"
    assert len(preview.result["mock_templates"]) == 1
    assert preview.result["mock_templates"][0]["confidence"] <= 0.64
    assert "草案" in preview.result["mock_templates"][0]["reason"]
    assert any("可信度较低" in warning for warning in preview.warnings)


def test_ai_mock_apply_appends_templates_to_case_metadata():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    workspace = WorkspaceService(session)
    api_case = workspace.get_case(case_id)
    api_case.metadata_json = {
        **(api_case.metadata_json or {}),
        "ai_mock_templates": [{"template_id": "baseline", "scenario_name": "existing_template"}],
    }
    workspace.save_case(api_case)
    session.commit()

    preview = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.mock.value: _make_mock_service(session).generate_preview},
    ).preview(
        capability=AiArtifactCapability.mock,
        target_type=AiArtifactTargetType.case,
        target_id=case_id,
        project_id=api_case.suite.project_id,
        suite_id=api_case.suite_id,
        case_id=case_id,
    )
    selected_template_ids = [item["template_id"] for item in preview.result["mock_templates"][:2]]

    saved_case = _make_mock_service(session).apply_artifact(
        preview.artifact_id,
        selected_template_ids=selected_template_ids,
        override_existing=False,
    )
    stored_artifact = AiArtifactRepository(session).get_by_artifact_id(preview.artifact_id)
    stored_templates = saved_case.metadata_json["ai_mock_templates"]

    assert len(stored_templates) == 3
    assert stored_templates[0]["template_id"] == "baseline"
    assert [item["template_id"] for item in stored_templates[1:]] == selected_template_ids
    assert stored_artifact is not None
    assert stored_artifact.status == AiArtifactStatus.applied.value


def test_ai_mock_apply_override_replaces_existing_templates():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    workspace = WorkspaceService(session)
    api_case = workspace.get_case(case_id)
    api_case.metadata_json = {
        **(api_case.metadata_json or {}),
        "ai_mock_templates": [{"template_id": "baseline", "scenario_name": "existing_template"}],
    }
    workspace.save_case(api_case)
    session.commit()

    preview = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.mock.value: _make_mock_service(session).generate_preview},
    ).preview(
        capability=AiArtifactCapability.mock,
        target_type=AiArtifactTargetType.case,
        target_id=case_id,
        project_id=api_case.suite.project_id,
        suite_id=api_case.suite_id,
        case_id=case_id,
    )
    selected_template_id = preview.result["mock_templates"][0]["template_id"]

    saved_case = _make_mock_service(session).apply_artifact(
        preview.artifact_id,
        selected_template_ids=[selected_template_id],
        override_existing=True,
    )

    assert saved_case.metadata_json["ai_mock_templates"] == [preview.result["mock_templates"][0]]


def test_ai_mock_export_returns_json_bundle():
    session = _make_session()
    case_id, _ = _seed_case_context_workspace(session)
    api_case = WorkspaceService(session).get_case(case_id)
    preview = AiCopilotService(
        session,
        capability_runners={AiArtifactCapability.mock.value: _make_mock_service(session).generate_preview},
    ).preview(
        capability=AiArtifactCapability.mock,
        target_type=AiArtifactTargetType.case,
        target_id=case_id,
        project_id=api_case.suite.project_id,
        suite_id=api_case.suite_id,
        case_id=case_id,
    )

    bundle = _make_mock_service(session).export_artifact(preview.artifact_id)

    assert bundle["artifact_id"] == preview.artifact_id
    assert bundle["case_id"] == case_id
    assert bundle["capability"] == "mock"
    assert len(bundle["mock_templates"]) >= 2
