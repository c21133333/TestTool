from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.api_case import ApiCase
from backend.app.models.environment import Environment
from backend.app.models.project import Project
from backend.app.models.suite import Suite


class WorkspaceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_projects(self) -> list[Project]:
        stmt = select(Project).options(selectinload(Project.suites), selectinload(Project.environments)).order_by(Project.name)
        return list(self._session.scalars(stmt).unique().all())

    def list_projects_page(self, *, page: int, page_size: int) -> tuple[list[Project], int]:
        stmt = select(Project).options(selectinload(Project.suites), selectinload(Project.environments)).order_by(Project.name)
        count_stmt = select(func.count(Project.id)).select_from(Project)
        total = int(self._session.scalar(count_stmt) or 0)
        paged_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        return list(self._session.scalars(paged_stmt).unique().all()), total

    def get_project(self, project_id: int) -> Project | None:
        stmt = (
            select(Project)
            .where(Project.id == project_id)
            .options(
                selectinload(Project.suites).selectinload(Suite.cases),
                selectinload(Project.environments),
            )
        )
        return self._session.scalar(stmt)

    def create_project(self, project: Project) -> Project:
        self._session.add(project)
        self._session.flush()
        return project

    def save_project(self, project: Project) -> Project:
        self._session.add(project)
        self._session.flush()
        return project

    def delete_project(self, project: Project) -> None:
        self._session.delete(project)

    def list_suites(self, project_id: int | None = None) -> list[Suite]:
        stmt = select(Suite).options(selectinload(Suite.cases)).order_by(Suite.name)
        if project_id is not None:
            stmt = stmt.where(Suite.project_id == project_id)
        return list(self._session.scalars(stmt).unique().all())

    def list_suites_page(self, *, page: int, page_size: int, project_id: int | None = None) -> tuple[list[Suite], int]:
        stmt = select(Suite).options(selectinload(Suite.cases)).order_by(Suite.name)
        count_stmt = select(func.count(Suite.id)).select_from(Suite)
        if project_id is not None:
            stmt = stmt.where(Suite.project_id == project_id)
            count_stmt = count_stmt.where(Suite.project_id == project_id)
        total = int(self._session.scalar(count_stmt) or 0)
        paged_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        return list(self._session.scalars(paged_stmt).unique().all()), total

    def get_suite(self, suite_id: int) -> Suite | None:
        stmt = select(Suite).where(Suite.id == suite_id).options(selectinload(Suite.cases))
        return self._session.scalar(stmt)

    def create_suite(self, suite: Suite) -> Suite:
        self._session.add(suite)
        self._session.flush()
        return suite

    def save_suite(self, suite: Suite) -> Suite:
        self._session.add(suite)
        self._session.flush()
        return suite

    def delete_suite(self, suite: Suite) -> None:
        self._session.delete(suite)

    def list_cases(self, suite_id: int | None = None) -> list[ApiCase]:
        stmt = select(ApiCase).order_by(ApiCase.created_at.desc())
        if suite_id is not None:
            stmt = stmt.where(ApiCase.suite_id == suite_id)
        return list(self._session.scalars(stmt).all())

    def list_cases_page(self, *, page: int, page_size: int, suite_id: int | None = None) -> tuple[list[ApiCase], int]:
        stmt = select(ApiCase).order_by(ApiCase.created_at.desc())
        count_stmt = select(func.count(ApiCase.id)).select_from(ApiCase)
        if suite_id is not None:
            stmt = stmt.where(ApiCase.suite_id == suite_id)
            count_stmt = count_stmt.where(ApiCase.suite_id == suite_id)
        total = int(self._session.scalar(count_stmt) or 0)
        paged_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        return list(self._session.scalars(paged_stmt).all()), total

    def get_case(self, case_id: int) -> ApiCase | None:
        return self._session.get(ApiCase, case_id)

    def create_case(self, case: ApiCase) -> ApiCase:
        self._session.add(case)
        self._session.flush()
        return case

    def save_case(self, case: ApiCase) -> ApiCase:
        self._session.add(case)
        self._session.flush()
        return case

    def delete_case(self, case: ApiCase) -> None:
        self._session.delete(case)

    def list_environments(self, project_id: int | None = None) -> list[Environment]:
        stmt = select(Environment).order_by(Environment.name)
        if project_id is not None:
            stmt = stmt.where(Environment.project_id == project_id)
        return list(self._session.scalars(stmt).all())

    def list_environments_page(
        self,
        *,
        page: int,
        page_size: int,
        project_id: int | None = None,
    ) -> tuple[list[Environment], int]:
        stmt = select(Environment).order_by(Environment.name)
        count_stmt = select(func.count(Environment.id)).select_from(Environment)
        if project_id is not None:
            stmt = stmt.where(Environment.project_id == project_id)
            count_stmt = count_stmt.where(Environment.project_id == project_id)
        total = int(self._session.scalar(count_stmt) or 0)
        paged_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        return list(self._session.scalars(paged_stmt).all()), total

    def get_environment(self, environment_id: int) -> Environment | None:
        return self._session.get(Environment, environment_id)

    def create_environment(self, environment: Environment) -> Environment:
        self._session.add(environment)
        self._session.flush()
        return environment

    def save_environment(self, environment: Environment) -> Environment:
        self._session.add(environment)
        self._session.flush()
        return environment

    def delete_environment(self, environment: Environment) -> None:
        self._session.delete(environment)
