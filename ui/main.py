"""FastAPI backend for the Code Understanding console."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Expose the project-root api/ package to the import system
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import Cookie, FastAPI, HTTPException, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.requests import Request  # noqa: E402

import catalog  # noqa: E402
import cluster  # noqa: E402
import indexes  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
NAMESPACE_COOKIE = "cu_namespace"


class FrameAncestorsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
        response.headers["X-Frame-Options"] = "ALLOWALL"
        return response


app = FastAPI(title="Code Understanding console", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.add_middleware(FrameAncestorsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.pipelines import router as _v2_router  # noqa: E402
from api.queries import router as _v2_queries_router  # noqa: E402

app.include_router(_v2_router, prefix="/api/v2")
app.include_router(_v2_queries_router, prefix="/api/v2")


class NamespaceRequest(BaseModel):
    namespace: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health(
    cu_namespace: str | None = Cookie(alias=NAMESPACE_COOKIE, default=None)
) -> dict[str, str]:
    status = cluster.cluster_status(ns=cu_namespace)
    if not status.get("ok"):
        raise HTTPException(503, status.get("message") or "cluster unavailable")
    return {"status": "ok", "namespace": status["namespace"]}


@app.get("/api/status")
def status(
    cu_namespace: str | None = Cookie(alias=NAMESPACE_COOKIE, default=None)
) -> dict[str, Any]:
    return cluster.cluster_status(ns=cu_namespace)


@app.get("/api/namespaces")
def get_namespaces(
    cu_namespace: str | None = Cookie(alias=NAMESPACE_COOKIE, default=None)
) -> dict[str, Any]:
    return {
        "namespaces": cluster.available_namespaces(),
        "current": cluster.current_namespace(cu_namespace),
    }


@app.post("/api/namespace")
def set_namespace(body: NamespaceRequest, response: Response) -> dict[str, str]:
    ns = (body.namespace or "").strip()
    if not ns:
        raise HTTPException(400, "namespace must not be empty.")
    available = cluster.available_namespaces()
    if len(available) > 1 and ns not in available:
        raise HTTPException(400, f"Namespace {ns!r} is not in the available list.")
    response.set_cookie(key=NAMESPACE_COOKIE, value=ns, httponly=False, samesite="lax")
    return {"namespace": ns}


@app.get("/api/catalog")
def get_catalog() -> dict[str, Any]:
    entries = catalog.load_catalog()
    default = catalog.default_repo_entry()
    return {
        "repos": entries,
        "default_key": catalog.repo_key(default) if default else None,
    }


@app.get("/api/indexes")
def get_indexes() -> dict[str, Any]:
    data = indexes.list_indexed_repos()
    catalog_entries = catalog.load_catalog()
    options = indexes.queryable_repos(data.get("indexes") or [], catalog_entries)
    return {**data, "queryable": options}
