"""FastAPI APIRouter for the v2 repositories endpoints."""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException

from . import repositories_service

logging.basicConfig(level=logging.INFO)

router = APIRouter()


@router.get("/repositories/run-repos/{run_id}")
async def get_run_repos(
    run_id: str,
    cu_namespace: str | None = Cookie(default=None),
) -> dict[str, Any]:
    try:
        repos = await asyncio.to_thread(repositories_service.get_run_repos, run_id, cu_namespace)
        return {"repos": repos}
    except Exception as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/repositories/catalog-repos")
async def get_catalog_repos(
    cu_namespace: str | None = Cookie(default=None),
) -> dict[str, Any]:
    try:
        repos = await asyncio.to_thread(repositories_service.get_catalog_repos, cu_namespace)
        return {"repos": repos}
    except Exception as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc
