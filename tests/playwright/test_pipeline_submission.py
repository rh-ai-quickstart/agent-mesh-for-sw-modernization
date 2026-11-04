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
    }
    for repo in REPOS
] + [
    {
        "git_repo": "",
        "git_branch": "main",
        "key": "__multi_repo__",
        "label": "Combined multi-repo index",
        "use_global": True,
    }
]


@pytest.fixture
def mock_console(page: Page):
    submissions = []
    unexpected_requests = []
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def open_console(*, indexed=True):
        responses = {
            "/api/status": {"ok": True, "namespace": "test"},
            "/api/catalog": {"repos": REPOS, "default_key": None},
            "/api/indexes": {
                "ok": True,
                "indexes": [],
                "queryable": QUERYABLE if indexed else [],
            },
            "/api/namespaces": {"namespaces": ["test"], "current": "test"},
            "/api/v2/pipelines/runs": {"runs": []},
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
def test_indexing_submits_selected_repositories(page: Page, mock_console, repo_count):
    submissions = mock_console()
    checkboxes = page.locator("#repo-list input[type=checkbox]")
    for index in range(repo_count):
        checkboxes.nth(index).check()
    page.locator('.cu-tabs button[data-tab="pipelines"]').click()

    with page.expect_response(f"{CONSOLE_URL}/api/v2/pipelines/runs/mock-run"):
        page.get_by_role("button", name="Run Indexing", exact=True).click()
    page.wait_for_load_state("networkidle")
    assert submissions == [{"repos": REPOS[:repo_count]}]


@pytest.mark.parametrize("combined", [False, True], ids=["single-repo", "multi-repo"])
def test_analysis_submits_selected_index(page: Page, mock_console, combined):
    submissions = mock_console()
    # Make the catalog selection differ from the analysis selection so accidental
    # use of the indexing checkboxes is caught for both analysis modes.
    page.get_by_role("button", name="Select all", exact=True).click()
    page.locator('.cu-tabs button[data-tab="analysis"]').click()
    key = "__multi_repo__" if combined else QUERYABLE[1]["key"]
    page.locator("#analysis-repo").select_option(key)

    with page.expect_response(f"{CONSOLE_URL}/api/v2/pipelines/runs/mock-run"):
        page.get_by_role("button", name="Run Analysis", exact=True).click()
    page.wait_for_load_state("networkidle")
    assert submissions == [
        {
            "repos": [] if combined else [REPOS[1]],
            "analysis_only": True,
            "multi_repo": combined,
        }
    ]


def test_indexing_without_selected_repositories_does_not_submit(page: Page, mock_console):
    submissions = mock_console()
    page.get_by_role("button", name="Clear", exact=True).click()
    page.locator('.cu-tabs button[data-tab="pipelines"]').click()

    page.get_by_role("button", name="Run Indexing", exact=True).click()

    expect(page.get_by_role("alert")).to_have_text(
        "Select at least one repository before running."
    )
    assert submissions == []


def test_analysis_without_available_indexes_does_not_submit(page: Page, mock_console):
    submissions = mock_console(indexed=False)
    page.locator('.cu-tabs button[data-tab="analysis"]').click()

    expect(page.locator("#analysis-empty")).to_be_visible()
    expect(page.locator("#analysis-repo option")).to_have_count(0)
    expect(page.get_by_role("button", name="Run Analysis", exact=True)).to_be_disabled()
    assert submissions == []
