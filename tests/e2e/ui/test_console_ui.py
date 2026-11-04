"""Browser smoke checks for the deployed Code Understanding console."""

import pytest
from playwright.sync_api import Page, expect

QUERY_TIMEOUT_MS = 30 * 60 * 1000


def test_console_loads_repositories_and_recent_runs(page: Page) -> None:
    checkboxes = page.locator("#repo-list input[type=checkbox]")
    expect(checkboxes.first).to_be_visible()

    # Recent Runs renders either run cards or its normal empty state.
    runs = page.locator("#runs")
    expect(runs).to_be_visible()
    expect(runs).not_to_be_empty()


def test_tabs_and_repository_selection_work(page: Page) -> None:
    repositories_tab = page.locator('.cu-tabs button[data-tab="repos"]')
    indexing_tab = page.locator('.cu-tabs button[data-tab="pipelines"]')
    analysis_tab = page.locator('.cu-tabs button[data-tab="analysis"]')
    chat_tab = page.locator('.cu-tabs button[data-tab="chat"]')

    expect(page.locator("#tab-repos")).to_be_visible()
    indexing_tab.click()
    expect(page.locator("#tab-pipelines")).to_be_visible()
    expect(page.get_by_role("button", name="Run Indexing")).to_be_visible()

    analysis_tab.click()
    expect(page.locator("#tab-analysis")).to_be_visible()
    expect(page.get_by_role("button", name="Run Analysis")).to_be_visible()

    chat_tab.click()
    expect(page.locator("#tab-chat")).to_be_visible()
    expect(page.get_by_placeholder("Ask about the selected code…")).to_be_visible()
    expect(page.get_by_role("button", name="Send")).to_be_visible()

    repositories_tab.click()
    checkboxes = page.locator("#repo-list input[type=checkbox]")
    count = checkboxes.count()
    assert count > 0, "The deployed repository catalog is empty"

    page.get_by_role("button", name="Select all").click()
    for index in range(count):
        expect(checkboxes.nth(index)).to_be_checked()
    expect(page.locator("#selection-note")).to_contain_text(f"{count} selected")

    page.get_by_role("button", name="Clear").click()
    for index in range(count):
        expect(checkboxes.nth(index)).not_to_be_checked()
    expect(page.locator("#selection-note")).to_contain_text("0 selected")


def test_analysis_offers_the_same_indexed_repositories_as_chat(page: Page) -> None:
    page.locator('.cu-tabs button[data-tab="analysis"]').click()
    expect(page.locator("#analysis-loading")).to_be_hidden()
    assert page.locator("#analysis-repo").inner_html() == page.locator("#chat-repo").inner_html()
    if page.locator("#analysis-repo option").count():
        expect(page.locator("#run-analysis")).to_be_enabled()
    else:
        expect(page.locator("#analysis-empty")).to_be_visible()
        expect(page.locator("#run-analysis")).to_be_disabled()


def test_analysis_and_chat_keep_independent_selections_after_refresh(page: Page) -> None:
    page.locator('.cu-tabs button[data-tab="analysis"]').click()
    expect(page.locator("#analysis-loading")).to_be_hidden()
    options = page.locator("#analysis-repo option")
    if options.count() < 2:
        pytest.skip("Two indexed repositories are needed to check independent selections.")

    analysis_key = options.last.get_attribute("value")
    chat_key = options.first.get_attribute("value")
    page.locator("#analysis-repo").select_option(analysis_key)
    page.locator('.cu-tabs button[data-tab="chat"]').click()
    page.locator("#chat-repo").select_option(chat_key)

    page.locator('.cu-tabs button[data-tab="repos"]').click()
    page.get_by_role("button", name="Clear", exact=True).click()
    page.locator('.cu-tabs button[data-tab="analysis"]').click()
    expect(page.locator("#analysis-repo")).to_have_value(analysis_key)

    # Refresh through the real console APIs, preserving both dropdown selections.
    page.evaluate("load()")
    expect(page.locator("#analysis-repo")).to_have_value(analysis_key)
    page.locator('.cu-tabs button[data-tab="chat"]').click()
    expect(page.locator("#chat-repo")).to_have_value(chat_key)


def test_indexing_selection_summary_tracks_repository_changes(page: Page) -> None:
    repository_cards = page.locator("#repo-list .cu-repo")
    count = repository_cards.count()
    assert count >= 2, "At least two repositories are needed to check the indexing summary"

    first_repo = repository_cards.nth(0)
    second_repo = repository_cards.nth(1)
    first_name = first_repo.locator(".cu-repo-title").inner_text()
    first_branch = first_repo.locator(".cu-chips .cu-chip").first.inner_text()
    second_name = second_repo.locator(".cu-repo-title").inner_text()
    second_branch = second_repo.locator(".cu-chips .cu-chip").first.inner_text()

    page.get_by_role("button", name="Clear").click()
    page.locator('.cu-tabs button[data-tab="pipelines"]').click()
    summary = page.locator("#pipeline-selection")
    expect(summary).to_contain_text("None selected")

    page.locator('.cu-tabs button[data-tab="repos"]').click()
    first_repo.locator("input").check()
    second_repo.locator("input").check()
    page.locator('.cu-tabs button[data-tab="pipelines"]').click()
    expected_summary = f"{first_name} @ {first_branch}, " f"{second_name} @ {second_branch}"
    expect(summary).to_contain_text(expected_summary)

    page.locator('.cu-tabs button[data-tab="repos"]').click()
    page.get_by_role("button", name="Clear").click()
    page.locator('.cu-tabs button[data-tab="pipelines"]').click()
    expect(summary).to_contain_text("None selected")


def test_recent_run_can_open_its_analysis_report(page: Page) -> None:
    expand_buttons = page.locator("#runs .cu-run-expand")
    if expand_buttons.count() == 0:
        pytest.skip("No successful pipeline runs are available to open.")

    page.locator('.cu-tabs button[data-tab="chat"]').click()
    expand_buttons.first.click()

    report_viewer = page.locator("#report-viewer")
    expect(report_viewer).to_be_visible(timeout=30_000)
    expect(page.locator("#tab-analysis")).to_be_visible()
    expect(page.locator("#report-viewer-title")).not_to_be_empty()
    expect(page.locator("#report-viewer-content")).not_to_be_empty()
    expect(page.locator("#report-viewer-content")).not_to_contain_text(
        "No analysis report available."
    )


def test_chat_query_returns_answer_and_succeeds(page: Page) -> None:
    page.locator('.cu-tabs button[data-tab="chat"]').click()

    repository = page.locator("#chat-repo")
    option = repository.get_by_role("option", name="tic-tac-toe-sample @ main", exact=True)
    expect(option).to_have_count(1, timeout=30_000)
    repository.select_option(label="tic-tac-toe-sample @ main")

    question = "How does the game determine when a player wins?"
    page.get_by_placeholder("Ask about the selected code…").fill(question)
    with page.expect_response(
        lambda response: response.url.endswith("/api/v2/queries")
        and response.request.method == "POST",
        timeout=30_000,
    ) as query_response_info:
        page.get_by_role("button", name="Send").click()

    query_response = query_response_info.value
    response_text = query_response.text()
    assert query_response.ok, f"Query submission failed: {query_response.status} {response_text}"
    query_id = query_response.json().get("query_id")
    assert query_id, f"Query submission did not return a query ID: {response_text}"

    answer = page.locator("#chat-log .cu-bubble.assistant:not(.thinking-msg)").last
    expect(answer).to_be_visible(timeout=QUERY_TIMEOUT_MS)
    expect(answer).not_to_be_empty(timeout=QUERY_TIMEOUT_MS)
    answer_text = answer.inner_text().strip()
    assert answer_text, "The query response box is empty"
    for error_text in (
        "Could not perform query:",
        "Query failed:",
        "The query job finished but no answer was found",
    ):
        assert error_text not in answer_text, f"Query returned an error: {answer_text}"
