import pytest
import os
from summarization_service.summarize import get_summary


@pytest.fixture
def dummy_input():
    return {
        "summary_type": "bp",
        "transcript": "[Speaker 1] Welcome to the show. [Speaker 2] Thank you for having me.",
        "episode_summary": "A discussion about podcast technology.",
        "show_title": "Tech Talks",
        "show_summary": "A podcast about technology trends."
    }


# Skip tests if CHATGROQ_API_KEY is not set
pytestmark = pytest.mark.skipif(
    not os.getenv("CHATGROQ_API_KEY"),
    reason="CHATGROQ_API_KEY not set; skipping integration test."
)

def test_get_summary_basic(dummy_input):
    summary = get_summary(**dummy_input)
    assert isinstance(summary, str)
    assert len(summary) > 0
    assert "Tech Talks" in summary or "technology" in summary or "Speaker" in summary
