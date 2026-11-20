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

    def open_console(*, indexed=True, runs=None, indexes=None, queryable=QUERYABLE):
        responses = {
            "/api/status": {"ok": True, "namespace": "test"},
            "/api/v2/repositories/catalog-repos": {"repos": REPOS, "default_key": None},
            "/api/indexes": {
                "ok": True,
                "indexes": indexes if indexes is not None else [],
                "queryable": queryable if indexed else [],
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
    assert submissions == [{"repos": REPOS[:repo_count], "analysis_goal": ""}]


def test_analyze_without_selected_repositories_is_disabled(page: Page, mock_console):
    mock_console()
    page.get_by_role("button", name="Clear", exact=True).click()

    analyze_btn = page.locator("#open-analyze")
    expect(analyze_btn).to_be_disabled()


@pytest.mark.parametrize("tab", ["repos", "runs"])
def test_uploaded_index_can_rerun_report(page: Page, mock_console, tab):
    index = {
        "run_id": "mlflow-upload",
        "kfp_run_id": "source-kfp-run",
        "git_slug": "example-prebuilt-main",
        "multi_repo": False,
        "uploaded": True,
    }
    repo = {"git_repo": "https://uploaded/example/prebuilt", "git_branch": "main"}
    submissions = mock_console(
        indexes=[index],
        queryable=[*QUERYABLE, {**repo, "git_slug": index["git_slug"]}],
        runs=[
            {
                "run_id": index["kfp_run_id"],
                "git_slug": index["git_slug"],
                "name": "Uploaded index",
                "status": "Succeeded",
                "uploaded": True,
                "source_pipeline_run_id": index["kfp_run_id"],
            },
        ],
    )
    if tab == "repos":
        row = page.locator("#repo-list .cu-repo").filter(has_text=index["git_slug"])
        expect(row.get_by_text("Uploaded", exact=True)).to_be_visible()
        row.get_by_role("button", name="Re-run").click()
    else:
        page.locator('.cu-nav-item[data-tab="runs"]').click()
        page.locator(".cu-run-select").check()
        expect(page.locator("#run-view-report")).to_be_disabled()
        page.locator("#run-rerun").click()

    expect(page.get_by_label("Re-run report only")).to_be_checked()
    expect(page.get_by_label("Re-run from scratch")).to_be_hidden()
    with page.expect_response(f"{CONSOLE_URL}/api/v2/pipelines/runs/mock-run"):
        page.locator("#rerun-confirm").click()
    assert submissions == [{"repos": [repo], "pipeline_run_id": index["kfp_run_id"]}]


def test_combined_upload_is_visible_without_rerun(page: Page, mock_console):
    mock_console(
        indexes=[
            {
                "run_id": "mlflow-upload",
                "kfp_run_id": "source-kfp-run",
                "git_slug": "",
                "multi_repo": True,
                "uploaded": True,
            },
        ],
        runs=[
            {
                "run_id": "source-kfp-run",
                "name": "Uploaded index",
                "status": "Succeeded",
                "uploaded": True,
                "source_pipeline_run_id": "source-kfp-run",
                "multi_repo": True,
            },
        ],
    )
    row = page.locator("#repo-list .cu-repo").filter(has_text="Combined multi-repo index")
    expect(row.get_by_text("Uploaded", exact=True)).to_be_visible()
    expect(row.get_by_role("button", name="Re-run")).to_have_count(0)
    page.locator('.cu-nav-item[data-tab="runs"]').click()
    page.locator(".cu-run-select").check()
    expect(page.locator("#run-rerun")).to_be_disabled()


def test_uploaded_index_without_source_run_id_cannot_rerun(page: Page, mock_console):
    mock_console(
        runs=[
            {
                "run_id": "mlflow-upload",
                "git_slug": "example-one-develop",
                "name": "Uploaded index",
                "status": "Succeeded",
                "uploaded": True,
                "source_pipeline_run_id": "",
            },
        ]
    )
    page.locator('.cu-nav-item[data-tab="runs"]').click()
    page.locator(".cu-run-select").check()
    expect(page.locator("#run-rerun")).to_be_disabled()


def test_uploaded_index_marks_existing_catalog_row_without_duplicating_it(
    page: Page, mock_console
):
    mock_console(
        indexes=[
            {
                "run_id": "mlflow-upload",
                "kfp_run_id": "source-kfp-run",
                "git_slug": "example-one-develop",
                "multi_repo": False,
                "uploaded": True,
            },
        ]
    )
    rows = page.locator("#repo-list .cu-repo")
    expect(rows).to_have_count(len(REPOS))
    expect(rows.first.get_by_text("Uploaded", exact=True)).to_be_visible()


@pytest.mark.parametrize("mode", ["scratch", "report"])
def test_existing_run_can_still_rerun(page: Page, mock_console, mode):
    runs = [{**MOCK_RUNS[0], "source_pipeline_run_id": "original-index"}, MOCK_RUNS[1]]
    submissions = mock_console(runs=runs)
    page.locator('.cu-nav-item[data-tab="runs"]').click()
    page.locator(".cu-run-select").first.check()
    page.locator("#run-rerun").click()

    expect(page.get_by_label("Re-run from scratch")).to_be_checked()
    expect(page.get_by_label("Re-run report only")).to_be_visible()
    expected = {"repos": [REPOS[0]]}
    if mode == "report":
        page.get_by_label("Re-run report only").check()
        expected["pipeline_run_id"] = "original-index"
    with page.expect_response(f"{CONSOLE_URL}/api/v2/pipelines/runs/mock-run"):
        page.locator("#rerun-confirm").click()
    assert submissions == [expected]


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
