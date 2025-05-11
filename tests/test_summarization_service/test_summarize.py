import pytest
from unittest.mock import patch, MagicMock
from summarization_service.summarize import get_summary


@pytest.fixture
def dummy_input():
    return {
        "summary_type": "bp",
        "transcript": "The world is facing a major climate challenge.",
        "episode_summary": "Discussion about global warming.",
        "show_title": "Climate Talks",
        "show_summary": "Podcast about climate change."
    }


@patch("summarization_service.summarize.requests.post")
@patch("summarization_service.summarize.time.sleep", return_value=None)
def test_get_summary_basic(mock_sleep, mock_post, dummy_input):
    fake_response = {
        "choices": [
            {"message": {"content": "• Climate change is real.\n• We must act."}}
        ]
    }

    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = fake_response

    summary = get_summary(**dummy_input)
    assert "Climate change" in summary
    mock_post.assert_called_once()
    mock_sleep.assert_not_called()  # assume >60s since last call


@patch("summarization_service.summarize.requests.post")
@patch("summarization_service.summarize.time.sleep")
def test_get_summary_respects_rate_limit(mock_sleep, mock_post, dummy_input):
    from summarization_service import summarize
    summarize.t_last_request_time = summarize.time.time() - 10  # simulate last call was 10s ago

    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "• Test summary"}}]
    }

    summary = get_summary(**dummy_input)
    mock_sleep.assert_called_once()
    assert "summary" in summary.lower()


@patch("summarization_service.summarize.requests.post")
def test_get_summary_handles_no_choices(mock_post, dummy_input):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {}

    summary = get_summary(**dummy_input)
    assert summary == "No response generated."


@patch("summarization_service.summarize.requests.post")
def test_get_summary_handles_api_exception(mock_post, dummy_input):
    mock_post.side_effect = Exception("API crashed")

    summary = get_summary(**dummy_input)
    assert summary.startswith("Error")
