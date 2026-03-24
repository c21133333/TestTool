from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import bearer_scheme, require_authenticated_user
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.user import User
from backend.app.schemas.auth import AuthSessionRead, LoginRequest
from backend.app.schemas.user import UserRead
from backend.app.services.auth_service import AuthService

router = APIRouter()


@router.post("/login", response_model=ApiResponse[AuthSessionRead])
def login(payload: LoginRequest, session: Session = Depends(session_scope)) -> ApiResponse[AuthSessionRead]:
    auth_service = AuthService(session)
    user = auth_service.authenticate(payload.username, payload.password)
    result = auth_service.build_session(user)
    return ApiResponse.ok(data=result, message="Login succeeded.")


@router.get("/me", response_model=ApiResponse[UserRead])
def current_user(current_actor: User = Depends(require_authenticated_user)) -> ApiResponse[UserRead]:
    return ApiResponse.ok(data=UserRead.model_validate(current_actor), message="Current user loaded.")


@router.post("/logout", response_model=ApiResponse[None])
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(session_scope),
) -> ApiResponse[None]:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        AuthService(session).revoke_access_token(credentials.credentials)
    return ApiResponse.ok(message="Logged out.")
