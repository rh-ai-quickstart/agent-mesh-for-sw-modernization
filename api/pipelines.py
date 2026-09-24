"""FastAPI APIRouter for the v2 pipelines endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
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


@router.post("/pipelines")
async def post_pipeline_service(body: RunPipelinesRequest) -> dict[str, Any]:
    repos = [r.model_dump() for r in body.repos]
    try:
        return await asyncio.to_thread(pipeline_service.submit_pipeline_run, repos)
    except ValueError as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/pipelines/runs")
async def list_pipeline_runs() -> dict[str, Any]:
    return {"runs": await asyncio.to_thread(pipeline_service.list_pipeline_runs)}


@router.get("/pipelines/runs/{run_id}")
async def get_run_status(run_id: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(pipeline_service.get_run_status, run_id)
    except ValueError as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc
