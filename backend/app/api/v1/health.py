"""Liveness and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import SessionDep, SettingsDep
from app.schemas.common import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health(settings: SettingsDep) -> HealthResponse:
    """Report that the process is up. Touches no dependencies by design."""
    return HealthResponse(status="ok", environment=settings.environment.value, version="0.1.0")


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"description": "A dependency is unavailable"}},
)
def readiness(session: SessionDep) -> ReadinessResponse | JSONResponse:
    """Report whether the service can actually serve traffic.

    Separate from liveness so an orchestrator restarts a wedged process but
    merely stops routing to one whose database is briefly unreachable.
    """
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "database": "unreachable"},
        )
    return ReadinessResponse(status="ok", database="reachable")
