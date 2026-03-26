from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models.base import Base
from backend.app.models.registry import load_model_metadata
from backend.app.schemas.workspace import ApiCaseCreate, ProjectCreate, SuiteCreate
from backend.app.services.ai_chat_context_service import AiChatContextService
from backend.app.services.workspace_service import WorkspaceService


def _build_session() -> Session:
    load_model_metadata()
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def _seed_project_with_37_cases(session: Session) -> tuple[int, int]:
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Chat Snapshot", description=""))
    suite_a = workspace.create_suite(SuiteCreate(project_id=project.id, name="Suite A", description=""))
    target_suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="ai生产case", description=""))

    for index in range(24):
        workspace.create_case(
            ApiCaseCreate(
                suite_id=suite_a.id,
                name=f"Suite A Case {index + 1}",
                method="GET",
                url=f"/suite-a/{index + 1}",
            )
        )

    for index in range(13):
        workspace.create_case(
            ApiCaseCreate(
                suite_id=target_suite.id,
                name=f"AI Case {index + 1}",
                method="POST",
                url=f"/ai-suite/{index + 1}",
            )
        )

    session.commit()
    return project.id, target_suite.id


def test_build_project_snapshot_uses_full_suite_case_counts() -> None:
    session = _build_session()
    try:
        project_id, target_suite_id = _seed_project_with_37_cases(session)

        snapshot = AiChatContextService(session).build_project_snapshot(project_id)

        suite_summary = next(item for item in snapshot["suites"] if item["id"] == target_suite_id)
        assert suite_summary["case_count"] == 13
        assert "37 个用例" in snapshot["summary"]
    finally:
        session.close()


def test_build_project_snapshot_samples_cases_from_later_suite() -> None:
    session = _build_session()
    try:
        project_id, target_suite_id = _seed_project_with_37_cases(session)

        snapshot = AiChatContextService(session).build_project_snapshot(project_id)

        target_suite_cases = [item for item in snapshot["cases"] if item["suite_id"] == target_suite_id]
        assert target_suite_cases
        assert {item["name"] for item in target_suite_cases} >= {"AI Case 1", "AI Case 2", "AI Case 3"}
    finally:
        session.close()
