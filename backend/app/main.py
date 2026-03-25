from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from backend.app.api.router import api_router
from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, bootstrap_database
from backend.app.core.error_handling import install_exception_handlers
from backend.app.core.observability import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
    get_request_id,
    log_event,
)
from backend.app.services.auth_service import AuthService

logger = get_logger("api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging(component="api")
    log_event(
        logger,
        "api.startup.begin",
        deployment_env=settings.deployment_env,
        api_prefix=settings.api_prefix,
        version=settings.app_version,
    )
    settings.validate_runtime_requirements("api")
    bootstrap_database()
    session = SessionLocal()
    try:
        AuthService(session).ensure_bootstrap_admin()
    finally:
        session.close()
    log_event(logger, "api.startup.ready", deployment_env=settings.deployment_env)
    yield
    log_event(logger, "api.shutdown", deployment_env=settings.deployment_env)


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Web migration backend for Eazy Test.",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    _register_request_logging(application)
    install_exception_handlers(application)
    application.include_router(api_router, prefix=settings.api_prefix)
    _register_frontend_routes(application)
    return application


def _register_request_logging(application: FastAPI) -> None:
    @application.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID")
        request_token = bind_request_context(request_id)
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            log_event(
                logger,
                "http.request.failed",
                level=logging.ERROR,
                method=request.method,
                path=request.url.path,
                query=request.url.query or "",
                duration_ms=duration_ms,
                client_ip=request.client.host if request.client is not None else None,
            )
            clear_request_context(request_token)
            raise
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        response.headers["X-Request-ID"] = get_request_id() or ""
        log_event(
            logger,
            "http.request.completed",
            method=request.method,
            path=request.url.path,
            query=request.url.query or "",
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=request.client.host if request.client is not None else None,
        )
        clear_request_context(request_token)
        return response


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
        if asset_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found.")
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
