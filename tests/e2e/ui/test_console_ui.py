"""Browser smoke checks for the deployed Code Understanding console."""

import re

import pytest
from playwright.sync_api import Page, expect

QUERY_TIMEOUT_MS = 30 * 60 * 1000


def test_console_loads_repositories_and_recent_runs(page: Page) -> None:
    checkboxes = page.locator("#repo-list input[type=checkbox]")
    expect(checkboxes.first).to_be_visible()

    # Switch to Runs tab and verify it renders.
    page.locator('.cu-nav-item[data-tab="runs"]').click()
    expect(page.locator("#tab-runs")).to_be_visible()
    run_table = page.locator("#run-list")
    expect(run_table).to_be_visible()


def test_tabs_and_repository_selection_work(page: Page) -> None:
    repos_tab = page.locator('.cu-nav-item[data-tab="repos"]')
    runs_tab = page.locator('.cu-nav-item[data-tab="runs"]')

    # Repos tab is visible by default.
    expect(page.locator("#tab-repos")).to_be_visible()

    # Switch to Runs tab.
    runs_tab.click()
    expect(page.locator("#tab-runs")).to_be_visible()

    # Switch back to repos.
    repos_tab.click()
    expect(page.locator("#tab-repos")).to_be_visible()
    checkboxes = page.locator("#repo-list input[type=checkbox]")
    count = checkboxes.count()
    assert count > 0, "The deployed repository catalog is empty"

    page.get_by_role("button", name="Select all").click()
    for index in range(count):
        expect(checkboxes.nth(index)).to_be_checked()

    page.get_by_role("button", name="Clear").click()
    for index in range(count):
        expect(checkboxes.nth(index)).not_to_be_checked()


def test_selection_note_tracks_repository_changes(page: Page) -> None:
    repository_cards = page.locator("#repo-list .cu-repo")
    count = repository_cards.count()
    assert count >= 2, "At least two repositories are needed to check the selection note"

    first_repo = repository_cards.nth(0)
    second_repo = repository_cards.nth(1)
    first_name = first_repo.locator(".cu-repo-title").inner_text()
    first_branch = first_repo.locator(".cu-chips .cu-chip").first.inner_text()
    second_name = second_repo.locator(".cu-repo-title").inner_text()
    second_branch = second_repo.locator(".cu-chips .cu-chip").first.inner_text()

    page.get_by_role("button", name="Clear").click()
    note = page.locator("#selection-note")
    expect(note).to_contain_text("None selected")

    first_repo.locator("input").check()
    second_repo.locator("input").check()
    expected = f"{first_name} @ {first_branch}, {second_name} @ {second_branch}"
    expect(note).to_contain_text(expected)

    page.get_by_role("button", name="Clear").click()
    expect(note).to_contain_text("None selected")


def test_analyze_button_requires_selection(page: Page) -> None:
    page.get_by_role("button", name="Clear").click()
    analyze_btn = page.locator("#open-analyze")
    expect(analyze_btn).to_be_disabled()

    page.get_by_role("button", name="Select all").click()
    expect(analyze_btn).to_be_enabled()


def test_analyze_opens_confirmation_modal(page: Page) -> None:
    page.get_by_role("button", name="Select all").click()
    page.locator("#open-analyze").click()

    modal = page.locator("#analyze-modal")
    expect(modal).to_be_visible()
    expect(page.locator("#analyze-modal-title")).to_have_text("Confirm Run Analysis")
    expect(page.locator("#start-analysis")).to_be_visible()

    # Close via cancel.
    page.locator("#analyze-modal-cancel").click()
    expect(modal).to_be_hidden()


def test_recent_run_can_open_its_analysis_report(page: Page) -> None:
    page.locator('.cu-nav-item[data-tab="runs"]').click()
    expand_buttons = page.locator("#run-list .cu-run-expand")
    if expand_buttons.count() == 0:
        pytest.skip("No successful pipeline runs are available to open.")

    expand_buttons.first.click()

    expect(page.locator("#tab-analysis")).to_be_visible(timeout=30_000)
    expect(page.locator("#report-viewer-title")).not_to_be_empty()
    expect(page.locator("#report-viewer-content")).not_to_be_empty()
    expect(page.locator("#report-viewer-content")).not_to_contain_text(
        "No analysis report available."
    )


def test_theme_toggle_switches_to_dark_mode(page: Page) -> None:
    body = page.locator("body")
    expect(body).not_to_have_class("dark")

    page.locator('input[name="theme-mode"][value="dark"]').check(force=True)
    expect(body).to_have_class("dark")

    page.locator('input[name="theme-mode"][value="light"]').check(force=True)
    expect(body).not_to_have_class("dark")


def test_chat_slider_opens_from_run(page: Page) -> None:
    page.locator('.cu-nav-item[data-tab="runs"]').click()
    chat_buttons = page.locator("#run-list .cu-run-chat")
    if chat_buttons.count() == 0:
        pytest.skip("No successful runs with chat available.")

    chat_buttons.first.click()
    slider = page.locator("#chat-slider")
    expect(slider).to_have_class(re.compile(r"open"))

    page.locator("#chat-slider-close").click()
    expect(slider).not_to_have_class(re.compile(r"open"))
