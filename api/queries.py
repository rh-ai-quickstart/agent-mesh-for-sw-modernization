"""FastAPI APIRouter for the v2 queries endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
import traceback  # noqa: E402

from . import query_service  # noqa: E402

router = APIRouter()


class RunQueryRequest(BaseModel):
    question: str
    retry_count: int = 3
    use_global: bool = True
    git_repo: str = ""
    git_branch: str = "main"
    multi_repo: bool = False


@router.post("/queries")
async def post_query(body: RunQueryRequest) -> dict[str, Any]:
    try:
        return query_service.submit_query(**body.model_dump())
    except ValueError as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/queries/{query_id}")
async def get_query_status(query_id: str) -> dict[str, Any]:
    try:
        return query_service.get_query_status(query_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc
