"""Unit tests for generate_improvement_plan in eval_utils."""

from unittest.mock import MagicMock, patch

import pandas as pd
from utils.eval_utils import generate_improvement_plan


def _sample_df():
    return pd.DataFrame(
        {
            "question": ["What does module X do?", "How is Y structured?"],
            "answer": ["Module X handles auth.", "Y is a monolith."],
            "reference": ["Module X manages authentication and tokens.", "Y uses microservices."],
            "faithfulness": [4, 2],
            "answer_relevance": [5, 3],
            "answer_similarity": [4, 2],
            "answer_correctness": [4, 1],
        }
    )


@patch("utils.eval_utils.completion")
@patch("loaders.default_asset_loader.DefaultAssetLoader")
def test_generate_improvement_plan_calls_llm(MockLoader, mock_completion, monkeypatch):
    monkeypatch.setenv("JUDGE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("JUDGE_LLM_ID", "gpt-4")
    monkeypatch.setenv("JUDGE_LLM_API_BASE", "http://localhost:8000")
    monkeypatch.setenv("JUDGE_LLM_TOKEN", "test-token")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "# Improvement Plan\n\nAdd metadata."
    mock_completion.return_value = mock_response

    fake_loader = MagicMock()
    fake_loader.download_prompt.return_value = ("Rendered prompt with payload", {})
    MockLoader.return_value = fake_loader

    result = generate_improvement_plan(_sample_df())

    assert result == "# Improvement Plan\n\nAdd metadata."
    mock_completion.assert_called_once()
    call_kwargs = mock_completion.call_args
    assert call_kwargs.kwargs["model"] == "openai/gpt-4"
    assert call_kwargs.kwargs["messages"][0]["content"] == "Rendered prompt with payload"

    fake_loader.download_prompt.assert_called_once()
    prompt_call = fake_loader.download_prompt.call_args
    assert prompt_call.args[0] == "eval/improvement_plan"
    assert "payload" in prompt_call.kwargs


@patch("utils.eval_utils.completion")
@patch("loaders.default_asset_loader.DefaultAssetLoader")
def test_generate_improvement_plan_returns_fallback_on_error(
    MockLoader, mock_completion, monkeypatch
):
    monkeypatch.setenv("JUDGE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("JUDGE_LLM_ID", "gpt-4")
    monkeypatch.setenv("JUDGE_LLM_API_BASE", "http://localhost:8000")
    monkeypatch.setenv("JUDGE_LLM_TOKEN", "test-token")

    fake_loader = MagicMock()
    fake_loader.download_prompt.return_value = ("Rendered prompt", {})
    MockLoader.return_value = fake_loader

    mock_completion.side_effect = RuntimeError("LLM unavailable")

    result = generate_improvement_plan(_sample_df())

    assert "_Improvement plan generation failed:" in result
