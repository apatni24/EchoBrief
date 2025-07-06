import pytest
import os
from summarization_service.summarize import get_summary
from unittest.mock import patch, MagicMock
from summarization_service import summarize
from langchain_core.runnables import Runnable


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


class MockLLM(Runnable):
    """Mock LLM that implements the Runnable interface"""
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
    
    def invoke(self, input_data, config=None, **kwargs):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return "Default response"
    
    def run(self, *args, **kwargs):
        return self.invoke(kwargs)


class TestSummarizeWithMetadata:
    
    @patch('summarization_service.summarize._rate_limit')
    def test_get_summary_with_episode_title(self, mock_rate_limit):
        """Test that get_summary properly uses episode_title when provided"""
        # Mock responses
        responses = [
            "Speaker 1: Host\nSpeaker 2: Guest",  # Speaker roles
            "CORRECTIONS: None needed\nVALIDATION: Transcript is accurate and aligns with metadata",  # Validation
            "## Test Summary\n\nThis is a test summary."  # Final summary
        ]
        
        mock_llm = MockLLM(responses)
        
        with patch('summarization_service.summarize.ChatOpenAI', return_value=mock_llm):
            # Test data
            transcript = "This is a test transcript with some content."
            episode_summary = "A test episode about technology."
            show_title = "Tech Talk Show"
            show_summary = "A show about technology and innovation."
            episode_title = "The Future of AI"
            
            # Call the function
            result = summarize.get_summary(
                "bps",  # bullet points summary
                transcript,
                episode_summary,
                show_title,
                show_summary,
                episode_title
            )
            
            # Verify the result
            assert result == "## Test Summary\n\nThis is a test summary."
            
            # Verify that the LLM was called the expected number of times
            assert mock_llm.call_count == 3
        
    @patch('summarization_service.summarize._rate_limit')
    def test_get_summary_without_episode_title(self, mock_rate_limit):
        """Test that get_summary works when episode_title is not provided"""
        # Mock responses
        responses = [
            "Speaker 1: Host\nSpeaker 2: Guest",  # Speaker roles
            "CORRECTIONS: None needed\nVALIDATION: Transcript is accurate",  # Validation
            "## Test Summary\n\nThis is a test summary."  # Final summary
        ]
        
        mock_llm = MockLLM(responses)
        
        with patch('summarization_service.summarize.ChatOpenAI', return_value=mock_llm):
            # Test data without episode_title
            transcript = "This is a test transcript."
            episode_summary = "A test episode."
            show_title = "Test Show"
            show_summary = "A test show description."
            
            # Call the function without episode_title
            result = summarize.get_summary(
                "bps",
                transcript,
                episode_summary,
                show_title,
                show_summary
            )
            
            # Verify the result
            assert result == "## Test Summary\n\nThis is a test summary."
            
            # Verify that the LLM was called the expected number of times
            assert mock_llm.call_count == 3
    
    @patch('summarization_service.summarize._rate_limit')
    def test_transcript_correction(self, mock_rate_limit):
        """Test that transcript corrections are applied when validation finds issues"""
        # Mock responses with corrections
        responses = [
            "Speaker 1: Host\nSpeaker 2: Guest",  # Speaker roles
            """CORRECTIONS:
- "artificial inteligence" → "artificial intelligence"
- "mashine learning" → "machine learning"
VALIDATION: Found and corrected spelling errors in technical terms""",  # Validation with corrections
            "## Corrected Summary\n\nThis summary uses corrected terms."  # Final summary
        ]
        
        mock_llm = MockLLM(responses)
        
        with patch('summarization_service.summarize.ChatOpenAI', return_value=mock_llm):
            # Test data with spelling errors
            transcript = "This episode discusses artificial inteligence and mashine learning."
            episode_summary = "A discussion about AI and ML."
            show_title = "Tech Show"
            show_summary = "Technology discussions."
            episode_title = "AI and ML Basics"
            
            # Call the function
            result = summarize.get_summary(
                "bps",
                transcript,
                episode_summary,
                show_title,
                show_summary,
                episode_title
            )
            
            # Verify the result
            assert result == "## Corrected Summary\n\nThis summary uses corrected terms."
            
            # Verify that the LLM was called the expected number of times
            assert mock_llm.call_count == 3
    
    @patch('summarization_service.summarize._rate_limit')
    def test_different_summary_types(self, mock_rate_limit):
        """Test that different summary types work with the new metadata"""
        # Mock responses for multiple calls
        responses = [
            "Speaker 1: Host\nSpeaker 2: Guest",  # Speaker roles
            "CORRECTIONS: None needed\nVALIDATION: Transcript is accurate",  # Validation
            "## Narrative Summary\n\nThis is a narrative summary.",  # Narrative summary
            "Speaker 1: Host\nSpeaker 2: Guest",  # Speaker roles for second call
            "CORRECTIONS: None needed\nVALIDATION: Transcript is accurate",  # Validation for second call
            "## Takeaways Summary\n\n1. First takeaway\n2. Second takeaway"  # Takeaways summary
        ]
        
        mock_llm = MockLLM(responses)
        
        with patch('summarization_service.summarize.ChatOpenAI', return_value=mock_llm):
            # Test data
            transcript = "This is a test transcript."
            episode_summary = "A test episode."
            show_title = "Test Show"
            show_summary = "A test show description."
            episode_title = "Test Episode"
            
            # Test narrative summary
            narrative_result = summarize.get_summary(
                "ns",  # narrative summary
                transcript,
                episode_summary,
                show_title,
                show_summary,
                episode_title
            )
            
            # Test takeaways summary
            takeaways_result = summarize.get_summary(
                "ts",  # takeaways summary
                transcript,
                episode_summary,
                show_title,
                show_summary,
                episode_title
            )
            
            # Verify results
            assert narrative_result == "## Narrative Summary\n\nThis is a narrative summary."
            assert takeaways_result == "## Takeaways Summary\n\n1. First takeaway\n2. Second takeaway"
            
            # Verify that the LLM was called the expected number of times (6 total calls)
            assert mock_llm.call_count == 6
