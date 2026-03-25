from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.api_case import ApiCase
from backend.app.models.environment import Environment
from backend.app.models.project import Project
from backend.app.models.suite import Suite
from backend.app.repositories.workspace_repository import WorkspaceRepository
from backend.app.schemas.workspace import ApiCaseCreate, EnvironmentCreate, ProjectCreate, SuiteCreate


class WorkspaceService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._workspace = WorkspaceRepository(session)

    def list_projects(self) -> list[Project]:
        return self._workspace.list_projects()

    def list_projects_page(self, *, page: int = 1, page_size: int = 20) -> tuple[list[Project], int]:
        return self._workspace.list_projects_page(page=page, page_size=page_size)

    def create_project(self, payload: ProjectCreate) -> Project:
        project = Project(name=payload.name.strip(), description=payload.description.strip())
        return self._workspace.create_project(project)

    def update_project(self, project_id: int, payload: ProjectCreate) -> Project:
        project = self.get_project(project_id)
        project.name = payload.name.strip()
        project.description = payload.description.strip()
        return self._workspace.save_project(project)

    def delete_project(self, project_id: int) -> None:
        project = self.get_project(project_id)
        self._workspace.delete_project(project)

    def get_project(self, project_id: int) -> Project:
        project = self._workspace.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
        return project

    def list_suites(self, project_id: int | None = None) -> list[Suite]:
        return self._workspace.list_suites(project_id)

    def list_suites_page(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        project_id: int | None = None,
    ) -> tuple[list[Suite], int]:
        return self._workspace.list_suites_page(page=page, page_size=page_size, project_id=project_id)

    def create_suite(self, payload: SuiteCreate) -> Suite:
        self.get_project(payload.project_id)
        suite = Suite(project_id=payload.project_id, name=payload.name.strip(), description=payload.description.strip())
        return self._workspace.create_suite(suite)

    def update_suite(self, suite_id: int, payload: SuiteCreate) -> Suite:
        suite = self.get_suite(suite_id)
        self.get_project(payload.project_id)
        suite.project_id = payload.project_id
        suite.name = payload.name.strip()
        suite.description = payload.description.strip()
        return self._workspace.save_suite(suite)

    def delete_suite(self, suite_id: int) -> None:
        suite = self.get_suite(suite_id)
        self._workspace.delete_suite(suite)

    def get_suite(self, suite_id: int) -> Suite:
        suite = self._workspace.get_suite(suite_id)
        if suite is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found.")
        return suite

    def list_cases(self, suite_id: int | None = None) -> list[ApiCase]:
        return self._workspace.list_cases(suite_id)

    def list_cases_page(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        suite_id: int | None = None,
    ) -> tuple[list[ApiCase], int]:
        return self._workspace.list_cases_page(page=page, page_size=page_size, suite_id=suite_id)

    def create_case(self, payload: ApiCaseCreate) -> ApiCase:
        self.get_suite(payload.suite_id)
        case = ApiCase(
            suite_id=payload.suite_id,
            name=payload.name.strip(),
            method=payload.method.upper(),
            url=payload.url.strip(),
            description=payload.description.strip(),
            headers_json=payload.headers_json,
            body_json=payload.body_json,
            assertions_json=payload.assertions_json,
            pre_processors_json=payload.pre_processors_json,
            post_processors_json=payload.post_processors_json,
            metadata_json=payload.metadata_json,
        )
        return self._workspace.create_case(case)

    def update_case(self, case_id: int, payload: ApiCaseCreate) -> ApiCase:
        case = self.get_case(case_id)
        self.get_suite(payload.suite_id)
        case.suite_id = payload.suite_id
        case.name = payload.name.strip()
        case.method = payload.method.upper()
        case.url = payload.url.strip()
        case.description = payload.description.strip()
        case.headers_json = payload.headers_json
        case.body_json = payload.body_json
        case.assertions_json = payload.assertions_json
        case.pre_processors_json = payload.pre_processors_json
        case.post_processors_json = payload.post_processors_json
        case.metadata_json = payload.metadata_json
        return self._workspace.save_case(case)

    def save_case(self, case: ApiCase) -> ApiCase:
        return self._workspace.save_case(case)

    def save_ai_test_data_variants(
        self,
        case_id: int,
        variants: list[dict],
        *,
        override_existing: bool = False,
    ) -> ApiCase:
        case = self.get_case(case_id)
        metadata_json = dict(case.metadata_json or {})
        existing_variants = [
            item for item in metadata_json.get("ai_test_data_variants", []) if isinstance(item, dict)
        ]
        metadata_json["ai_test_data_variants"] = self._merge_named_items(
            existing_items=existing_variants,
            incoming_items=variants,
            identity_key="variant_id",
            override_existing=override_existing,
        )
        case.metadata_json = metadata_json
        return self._workspace.save_case(case)

    def save_ai_mock_templates(
        self,
        case_id: int,
        templates: list[dict],
        *,
        override_existing: bool = False,
    ) -> ApiCase:
        case = self.get_case(case_id)
        metadata_json = dict(case.metadata_json or {})
        existing_templates = [
            item for item in metadata_json.get("ai_mock_templates", []) if isinstance(item, dict)
        ]
        metadata_json["ai_mock_templates"] = self._merge_named_items(
            existing_items=existing_templates,
            incoming_items=templates,
            identity_key="template_id",
            override_existing=override_existing,
        )
        case.metadata_json = metadata_json
        return self._workspace.save_case(case)

    def list_ai_test_data_variants(self, case_id: int) -> list[dict]:
        case = self.get_case(case_id)
        metadata_json = dict(case.metadata_json or {})
        return [dict(item) for item in metadata_json.get("ai_test_data_variants", []) if isinstance(item, dict)]

    def list_ai_mock_templates(self, case_id: int) -> list[dict]:
        case = self.get_case(case_id)
        metadata_json = dict(case.metadata_json or {})
        return [dict(item) for item in metadata_json.get("ai_mock_templates", []) if isinstance(item, dict)]

    def delete_case(self, case_id: int) -> None:
        case = self.get_case(case_id)
        self._workspace.delete_case(case)

    def get_case(self, case_id: int) -> ApiCase:
        case = self._workspace.get_case(case_id)
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
        return case

    def list_environments(self, project_id: int | None = None) -> list[Environment]:
        return self._workspace.list_environments(project_id)

    def list_environments_page(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        project_id: int | None = None,
    ) -> tuple[list[Environment], int]:
        return self._workspace.list_environments_page(page=page, page_size=page_size, project_id=project_id)

    def create_environment(self, payload: EnvironmentCreate) -> Environment:
        self.get_project(payload.project_id)
        environment = Environment(
            project_id=payload.project_id,
            name=payload.name.strip(),
            base_url=payload.base_url.strip(),
            description=payload.description.strip(),
            headers_json=payload.headers_json,
            variables_json=payload.variables_json,
        )
        return self._workspace.create_environment(environment)

    def update_environment(self, environment_id: int, payload: EnvironmentCreate) -> Environment:
        environment = self.get_environment(environment_id)
        self.get_project(payload.project_id)
        environment.project_id = payload.project_id
        environment.name = payload.name.strip()
        environment.base_url = payload.base_url.strip()
        environment.description = payload.description.strip()
        environment.headers_json = payload.headers_json
        environment.variables_json = payload.variables_json
        return self._workspace.save_environment(environment)

    def delete_environment(self, environment_id: int) -> None:
        environment = self.get_environment(environment_id)
        self._workspace.delete_environment(environment)

    def get_environment(self, environment_id: int) -> Environment:
        environment = self._workspace.get_environment(environment_id)
        if environment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found.")
        return environment

    def _merge_named_items(
        self,
        *,
        existing_items: list[dict],
        incoming_items: list[dict],
        identity_key: str,
        override_existing: bool,
    ) -> list[dict]:
        normalized_incoming = [dict(item) for item in incoming_items if isinstance(item, dict)]
        if override_existing:
            return normalized_incoming

        merged_items = [dict(item) for item in existing_items if isinstance(item, dict)]
        seen_identities = {str(item.get(identity_key) or "") for item in merged_items}
        for item in normalized_incoming:
            identity = str(item.get(identity_key) or "")
            if identity and identity in seen_identities:
                continue
            merged_items.append(item)
            if identity:
                seen_identities.add(identity)
        return merged_items
