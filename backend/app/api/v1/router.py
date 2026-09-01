"""Aggregate router for API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import employees, salary_records

api_router = APIRouter()
api_router.include_router(employees.router)
api_router.include_router(salary_records.router)
