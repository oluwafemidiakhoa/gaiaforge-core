"""Optional read-only FastAPI endpoints. Install with: pip install -e '.[api]'"""
from __future__ import annotations


from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .inspect import inspect_repo
from .models import PlanError, validate_plan
from .verification import compare_evaluations

app = FastAPI(title="GaiaForge Core", version="0.1.0")


class PlanInput(BaseModel):
    tasks: list[dict]


class ComparisonInput(BaseModel):
    baseline: dict
    candidate: dict


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/plans/validate")
def validate(request: PlanInput) -> dict:
    try:
        tasks = validate_plan(request.model_dump())
        return {"valid": True, "task_count": len(tasks)}
    except PlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/evaluations/compare")
def compare(request: ComparisonInput) -> dict:
    try:
        return compare_evaluations(request.baseline, request.candidate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
