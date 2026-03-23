from __future__ import annotations

from fastapi import APIRouter

from backend.app.core.config import settings
from backend.app.core.responses import ApiResponse
from backend.app.schemas.health import HealthRead

router = APIRouter()


@router.get("", response_model=ApiResponse[HealthRead])
def health_check() -> ApiResponse[HealthRead]:
    return ApiResponse.ok(
        data=HealthRead(status="ok", service=settings.app_name, version=settings.app_version),
        message="Service is healthy.",
    )
