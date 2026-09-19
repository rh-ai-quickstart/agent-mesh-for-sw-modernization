"""FastAPI APIRouter for the v2 queries endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import query_service

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
        return await asyncio.to_thread(lambda: query_service.run_query(**body.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
