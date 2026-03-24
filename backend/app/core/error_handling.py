from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.core.observability import get_logger, get_request_id, log_event
from backend.app.core.responses import ApiErrorDetail, ApiErrorResponse

logger = get_logger("errors")

ERROR_CODE_BY_STATUS = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
}

DEFAULT_ERROR_MESSAGE_BY_STATUS = {
    status.HTTP_400_BAD_REQUEST: "Bad request.",
    status.HTTP_401_UNAUTHORIZED: "Authentication required.",
    status.HTTP_403_FORBIDDEN: "Permission denied.",
    status.HTTP_404_NOT_FOUND: "Resource not found.",
    status.HTTP_409_CONFLICT: "Conflict detected.",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "Request validation failed.",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal server error.",
}


def build_api_error_responses() -> dict[int | str, dict[str, Any]]:
    return {
        400: {"model": ApiErrorResponse, "description": DEFAULT_ERROR_MESSAGE_BY_STATUS[400]},
        401: {"model": ApiErrorResponse, "description": DEFAULT_ERROR_MESSAGE_BY_STATUS[401]},
        403: {"model": ApiErrorResponse, "description": DEFAULT_ERROR_MESSAGE_BY_STATUS[403]},
        404: {"model": ApiErrorResponse, "description": DEFAULT_ERROR_MESSAGE_BY_STATUS[404]},
        409: {"model": ApiErrorResponse, "description": DEFAULT_ERROR_MESSAGE_BY_STATUS[409]},
        422: {"model": ApiErrorResponse, "description": DEFAULT_ERROR_MESSAGE_BY_STATUS[422]},
        500: {"model": ApiErrorResponse, "description": DEFAULT_ERROR_MESSAGE_BY_STATUS[500]},
    }


def install_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)


def _build_error_response(
    *,
    status_code: int,
    message: str,
    details: Any = None,
) -> JSONResponse:
    request_id = get_request_id()
    payload = ApiErrorResponse(
        message=message,
        error=ApiErrorDetail(
            code=ERROR_CODE_BY_STATUS.get(status_code, "unknown_error"),
            status=status_code,
            details=details,
            request_id=request_id,
        ),
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    message = DEFAULT_ERROR_MESSAGE_BY_STATUS.get(exc.status_code, "Request failed.")
    details: Any = None
    if isinstance(exc.detail, str) and exc.detail.strip():
        message = exc.detail
    elif isinstance(exc.detail, dict):
        details = exc.detail
        message = str(exc.detail.get("message") or message)
    elif isinstance(exc.detail, list):
        details = exc.detail
    if exc.status_code >= 500:
        log_event(logger, "api.http_exception", level=logging.ERROR, status_code=exc.status_code, message=message)
    return _build_error_response(status_code=exc.status_code, message=message, details=details)


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = {
        "errors": exc.errors(),
    }
    return _build_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        message=DEFAULT_ERROR_MESSAGE_BY_STATUS[status.HTTP_422_UNPROCESSABLE_CONTENT],
        details=details,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log_event(
        logger,
        "api.unhandled_exception",
        level=logging.ERROR,
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
        message=str(exc),
    )
    return _build_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=DEFAULT_ERROR_MESSAGE_BY_STATUS[status.HTTP_500_INTERNAL_SERVER_ERROR],
    )
