"""Exercise real UI controls with all network traffic intercepted by Playwright.

The API routing tests own pipeline selection; these tests own the requests the UI
produces. No server, cluster, or pipeline execution is needed.
"""

from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Route, expect

STATIC_DIR = Path(__file__).resolve().parents[2] / "ui" / "static"
CONSOLE_URL = "http://console.test"
REPOS = [
    {"git_repo": "https://github.com/example/one", "git_branch": "develop"},
    {"git_repo": "https://github.com/example/two", "git_branch": "release"},
]
QUERYABLE = [
    {
        **repo,
        "key": f"{repo['git_repo']}|{repo['git_branch']}",
        "label": f"{repo['git_repo'].rsplit('/', 1)[-1]} @ {repo['git_branch']}",
        "use_global": False,
        "kfp_run_id": f"kfp-run-{i}",
    }
    for i, repo in enumerate(REPOS)
] + [
    {
        "git_repo": "",
        "git_branch": "main",
        "key": "__multi_repo__",
        "label": "Combined multi-repo index",
        "use_global": True,
        "kfp_run_id": "kfp-run-combined",
    }
]
MOCK_RUNS = [
    {
        "run_id": "run-1",
        "name": "run-1",
        "git_repo": "https://github.com/example/one",
        "git_branch": "develop",
        "status": "Succeeded",
        "start_time": "2026-01-01T00:00:00Z",
    },
    {
        "run_id": "run-2",
        "name": "run-2",
        "git_repo": "https://github.com/example/two",
        "git_branch": "release",
        "status": "Failed",
        "start_time": "2026-01-02T00:00:00Z",
    },
]


@pytest.fixture
def mock_console(page: Page):
    submissions = []
    unexpected_requests = []
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def open_console(*, indexed=True, runs=None):
        responses = {
            "/api/status": {"ok": True, "namespace": "test"},
            "/api/v2/repositories/catalog-repos": {"repos": REPOS, "default_key": None},
            "/api/indexes": {
                "ok": True,
                "indexes": [],
                "queryable": QUERYABLE if indexed else [],
            },
            "/api/namespaces": {"namespaces": ["test"], "current": "test"},
            "/api/v2/pipelines/runs": {"runs": runs if runs is not None else []},
            "/api/v2/pipelines/runs/mock-run": {"status": "running"},
        }
        static_files = {
            "/": STATIC_DIR / "index.html",
            **{f"/static/vendor/{path.name}": path for path in (STATIC_DIR / "vendor").iterdir()},
        }

        def handle_request(route: Route):
            request = route.request
            url = urlsplit(request.url)
            if f"{url.scheme}://{url.netloc}" == CONSOLE_URL:
                if request.method == "POST" and url.path == "/api/v2/pipelines":
                    submissions.append(request.post_data_json)
                    route.fulfill(json={"job_id": "mock-run"})
                    return
                if request.method == "GET" and url.path in responses:
                    route.fulfill(json=responses[url.path])
                    return
                if request.method == "GET" and url.path in static_files:
                    route.fulfill(path=static_files[url.path])
                    return
            unexpected_requests.append(f"{request.method} {request.url}")
            route.abort()

        # Never fall through to the network, including for unexpected submissions.
        page.route("**/*", handle_request)
        page.goto(CONSOLE_URL, wait_until="networkidle")
        expect(page.locator("#status")).to_contain_text("Connected")
        expect(page.locator("#repo-list input[type=checkbox]")).to_have_count(2)
        return submissions

    yield open_console

    assert not unexpected_requests, f"Unexpected requests: {unexpected_requests}"
    assert not page_errors, f"Browser JavaScript errors: {page_errors}"


@pytest.mark.parametrize("repo_count", [1, 2], ids=["single-repo", "multi-repo"])
def test_analyze_submits_selected_repositories(page: Page, mock_console, repo_count):
    submissions = mock_console()
    checkboxes = page.locator("#repo-list input[type=checkbox]")
    for index in range(repo_count):
        checkboxes.nth(index).check()

    # Click Analyze to open the confirmation modal.
    page.locator("#open-analyze").click()
    expect(page.locator("#analyze-modal")).to_be_visible()

    # Confirm the analysis.
    with page.expect_response(f"{CONSOLE_URL}/api/v2/pipelines/runs/mock-run"):
        page.locator("#start-analysis").click()
    page.wait_for_load_state("networkidle")
    assert submissions == [{"repos": REPOS[:repo_count]}]


def test_analyze_without_selected_repositories_is_disabled(page: Page, mock_console):
    mock_console()
    page.get_by_role("button", name="Clear", exact=True).click()

    analyze_btn = page.locator("#open-analyze")
    expect(analyze_btn).to_be_disabled()


def test_runs_tab_renders_run_list(page: Page, mock_console):
    mock_console(runs=MOCK_RUNS)
    page.locator('.cu-nav-item[data-tab="runs"]').click()
    expect(page.locator("#tab-runs")).to_be_visible()

    rows = page.locator("#run-list tr")
    expect(rows).to_have_count(2)


def test_failed_run_shows_failed_chip(page: Page, mock_console):
    mock_console(runs=MOCK_RUNS)
    page.locator('.cu-nav-item[data-tab="runs"]').click()

    failed_chip = page.locator("#run-list .cu-chip.failed")
    expect(failed_chip).to_have_count(1)
    expect(failed_chip).to_have_text("Failed")


def test_theme_toggle_persists_in_local_storage(page: Page, mock_console):
    mock_console()

    # Default is light — body should not have dark class.
    body = page.locator("body")
    expect(body).not_to_have_class("dark")

    # Switch to dark mode.
    page.locator('input[name="theme-mode"][value="dark"]').check(force=True)
    expect(body).to_have_class("dark")

    # Verify localStorage was set.
    theme = page.evaluate("localStorage.getItem('theme')")
    assert theme == "dark"

    # Switch back to light mode.
    page.locator('input[name="theme-mode"][value="light"]').check(force=True)
    expect(body).not_to_have_class("dark")
    theme = page.evaluate("localStorage.getItem('theme')")
    assert theme == "light"


def test_select_all_and_clear_buttons(page: Page, mock_console):
    mock_console()
    checkboxes = page.locator("#repo-list input[type=checkbox]")

    page.get_by_role("button", name="Select all", exact=True).click()
    for i in range(checkboxes.count()):
        expect(checkboxes.nth(i)).to_be_checked()

    page.get_by_role("button", name="Clear", exact=True).click()
    for i in range(checkboxes.count()):
        expect(checkboxes.nth(i)).not_to_be_checked()


def test_namespace_dropdown_is_visible(page: Page, mock_console):
    mock_console()
    ns_row = page.locator("#ns-row")
    expect(ns_row).to_be_visible()
    expect(page.locator("#ns-select")).to_have_value("test")
