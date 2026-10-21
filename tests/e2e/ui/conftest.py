"""Fixtures for browser smoke tests against the deployed console."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, expect

UI_URL = os.getenv("UI_URL", "").rstrip("/")
KFP_NAMESPACE = os.getenv("KFP_NAMESPACE", "").strip()


@pytest.fixture(scope="session", autouse=True)
def require_deployed_console() -> None:
    """Fail early unless the deployed app's readiness endpoint is healthy."""
    if not UI_URL:
        pytest.fail("UI_URL is not set; run this suite with `make test-ui-e2e`.")

    try:
        with urlopen(f"{UI_URL}/api/health", timeout=15) as response:
            assert (
                response.status == 200
            ), f"Console health endpoint returned HTTP {response.status}"
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        pytest.fail(f"Console health endpoint is not reachable at {UI_URL}: {exc}")

    assert payload.get("status") == "ok", f"Console health check failed: {payload}"
    if KFP_NAMESPACE:
        assert payload.get("namespace") == KFP_NAMESPACE, (
            f"Console is connected to namespace {payload.get('namespace')!r}; "
            f"expected {KFP_NAMESPACE!r}"
        )


@pytest.fixture(autouse=True)
def open_console(page: Page):
    """Open the console and wait until its live cluster status is rendered."""
    page.set_default_timeout(15_000)
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    response = page.goto(UI_URL, wait_until="domcontentloaded")
    assert response is not None and response.status == 200, "Console page did not return HTTP 200"
    expect(page.locator(".cu-brand-title")).to_have_text("Code Understanding")
    expect(page.locator("#status")).to_contain_text("Connected")

    yield

    assert not page_errors, f"Browser reported JavaScript errors: {page_errors}"
