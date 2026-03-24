from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "ok"
    data: T | None = None

    @classmethod
    def ok(cls, data: T | None = None, message: str = "ok") -> "ApiResponse[T]":
        return cls(success=True, message=message, data=data)

    @classmethod
    def paginated(
        cls,
        *,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
        message: str = "ok",
    ) -> "ApiResponse[PageData[T]]":
        return cls(
            success=True,
            message=message,
            data=PageData(items=items, total=total, page=page, page_size=page_size),
        )


class PageData(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ApiErrorDetail(BaseModel):
    code: str
    status: int
    details: Any | None = None
    request_id: str | None = None


class ApiErrorResponse(BaseModel):
    success: bool = False
    message: str
    error: ApiErrorDetail
    data: None = Field(default=None)
