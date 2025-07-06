import pytest
import os
from summarization_service.summarize import get_summary


@pytest.fixture
def dummy_input():
    return {
        "summary_type": "bp",
        "transcript": "[Speaker 1] Welcome to Tech Talks, I'm your host Sarah Chen. Today we're discussing the future of artificial intelligence in healthcare. [Speaker 2] Thanks for having me, Sarah. I'm Dr. Michael Rodriguez, and I've been working on AI applications in medical diagnosis for over a decade. [Speaker 1] That's fascinating, Dr. Rodriguez. Can you tell us about some of the breakthroughs you've seen? [Speaker 2] Absolutely. We're seeing AI systems that can detect early signs of diseases like cancer with 95% accuracy, often before human doctors can spot them. The technology is revolutionizing how we approach preventive medicine.",
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
