from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class SuiteCreate(BaseModel):
    project_id: int
    name: str
    description: str = ""


class ApiCaseCreate(BaseModel):
    suite_id: int
    name: str
    method: str = "GET"
    url: str
    description: str = ""
    headers_json: dict[str, str] = Field(default_factory=dict)
    body_json: Any | None = None
    assertions_json: list[dict[str, Any]] = Field(default_factory=list)
    pre_processors_json: list[dict[str, Any]] = Field(default_factory=list)
    post_processors_json: list[dict[str, Any]] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class EnvironmentCreate(BaseModel):
    project_id: int
    name: str
    base_url: str = ""
    description: str = ""
    headers_json: dict[str, str] = Field(default_factory=dict)
    variables_json: dict[str, Any] = Field(default_factory=dict)


class ApiCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    suite_id: int
    name: str
    method: str
    url: str
    description: str
    headers_json: dict[str, Any]
    body_json: Any | None
    assertions_json: list[dict[str, Any]]
    pre_processors_json: list[dict[str, Any]]
    post_processors_json: list[dict[str, Any]]
    metadata_json: dict[str, Any]
    created_at: datetime


class SuiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: str
    created_at: datetime
    cases: list[ApiCaseRead] = Field(default_factory=list)


class EnvironmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    base_url: str
    description: str
    headers_json: dict[str, Any]
    variables_json: dict[str, Any]
    created_at: datetime


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    created_at: datetime
    suites: list[SuiteRead] = Field(default_factory=list)
    environments: list[EnvironmentRead] = Field(default_factory=list)
