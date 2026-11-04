"""FastAPI APIRouter for the v2 pipelines endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
import traceback  # noqa: E402

from . import pipeline_service  # noqa: E402

router = APIRouter()


class Repo(BaseModel):
    git_repo: str
    git_branch: str = "main"


class RunPipelinesRequest(BaseModel):
    repos: list[Repo] = Field(default_factory=list)
    analysis_only: bool = False
    multi_repo: bool = False


@router.post("/pipelines")
async def post_pipeline_service(
    body: RunPipelinesRequest,
    cu_namespace: str | None = Cookie(default=None),
) -> dict[str, Any]:
    repos = [r.model_dump() for r in body.repos]
    try:
        return await asyncio.to_thread(
            pipeline_service.submit_pipeline_run,
            repos,
            cu_namespace,
            analysis_only=body.analysis_only,
            multi_repo=body.multi_repo,
        )
    except ValueError as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/pipelines/runs")
async def list_pipeline_runs(cu_namespace: str | None = Cookie(default=None)) -> dict[str, Any]:
    return {"runs": await asyncio.to_thread(pipeline_service.list_pipeline_runs, cu_namespace)}


@router.get("/pipelines/runs/{run_id}")
async def get_run_status(
    run_id: str,
    cu_namespace: str | None = Cookie(default=None),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(pipeline_service.get_run_status, run_id, cu_namespace)
    except ValueError as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc
