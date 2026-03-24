from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.schemas.health import HealthRead
from backend.app.services.health_service import HealthService

router = APIRouter()


@router.get("", response_model=ApiResponse[HealthRead])
def health_check(session: Session = Depends(session_scope)) -> ApiResponse[HealthRead]:
    return ApiResponse.ok(
        data=HealthService(session).build_health_snapshot(),
        message="Service health loaded.",
    )
