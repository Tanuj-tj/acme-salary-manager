"""Translate exceptions into RFC 7807 problem+json responses.

The only place in the codebase that knows about both ``AppError`` and HTTP.
Every error response has the same shape, with a stable ``type`` slug clients
can branch on.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


def _problem(
    *,
    request: Request,
    status_code: int,
    error_type: str,
    title: str,
    detail: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"/errors/{error_type}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
    }
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content=body, media_type=PROBLEM_JSON)


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _problem(
        request=request,
        status_code=exc.status_code,
        error_type=exc.error_type,
        title=exc.title,
        detail=exc.detail,
        extra={"context": exc.context} if exc.context else None,
    )


async def handle_request_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"][1:]) or "body",
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return _problem(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        error_type="request-validation-error",
        title="Request Validation Error",
        detail="The request payload failed validation.",
        extra={"errors": errors},
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    return _problem(
        request=request,
        status_code=exc.status_code,
        error_type="http-error",
        title=str(exc.detail),
        detail=str(exc.detail),
    )


async def handle_integrity_error(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort net for a unique or check constraint reaching the database.

    Services check these up front for a good message; this catches the race and
    turns it into a 409 instead of a 500. The database message is logged but
    never returned -- it can contain column values.
    """
    logger.warning("Integrity error on %s: %s", request.url.path, exc)
    return _problem(
        request=request,
        status_code=status.HTTP_409_CONFLICT,
        error_type="integrity-conflict",
        title="Conflict",
        detail="The request conflicts with existing data.",
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Never leak an internal error message or stack trace to the client."""
    logger.exception("Unhandled error on %s", request.url.path, exc_info=exc)
    return _problem(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_type="internal-error",
        title="Internal Server Error",
        detail="An unexpected error occurred.",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(IntegrityError, handle_integrity_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
