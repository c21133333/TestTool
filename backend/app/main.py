from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from backend.app.api.router import api_router
from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, bootstrap_database
from backend.app.services.auth_service import AuthService


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    bootstrap_database()
    session = SessionLocal()
    try:
        AuthService(session).ensure_bootstrap_admin()
    finally:
        session.close()
    yield


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Web migration backend for Eazy Test.",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix=settings.api_prefix)
    _register_frontend_routes(application)
    return application


def _register_frontend_routes(application: FastAPI) -> None:
    frontend_dist_dir = settings.project_root / "frontend" / "dist"
    index_file = frontend_dist_dir / "index.html"
    if not index_file.exists():
        return

    @application.get("/", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(index_file)

    @application.get("/{asset_path:path}", include_in_schema=False)
    def frontend_asset_or_index(asset_path: str) -> FileResponse:
        requested_path = _resolve_frontend_path(frontend_dist_dir, asset_path)
        if requested_path.is_file():
            return FileResponse(requested_path)
        return FileResponse(index_file)


def _resolve_frontend_path(frontend_dist_dir: Path, asset_path: str) -> Path:
    candidate = (frontend_dist_dir / asset_path).resolve()
    frontend_root = frontend_dist_dir.resolve()
    try:
        candidate.relative_to(frontend_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not Found") from exc
    return candidate


app = create_application()
