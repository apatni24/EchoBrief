import pytest
import asyncio
import json
from unittest.mock import patch, AsyncMock

from summarization_service import transcription_complete_consumer


@pytest.mark.asyncio
async def test_consumer_message_processing(monkeypatch):
    # Sample parsed Redis message
    parsed = {
        "job_id": "job123",
        "summary_type": "bp",
        "transcript": "Climate change is real.",
        "metadata": {
            "summary": "Climate story",
            "show_title": "Planet Voices",
            "show_summary": "Voices from the climate frontlines"
        }
    }

    fake_summary = "• Climate change is a threat\n• Action is required"

    # Mock summarization and broadcasting
    with patch("summarization_service.transcription_complete_consumer.summarize.get_summary", return_value=fake_summary) as mock_summarize, \
         patch("summarization_service.transcription_complete_consumer.manager.broadcast", new_callable=AsyncMock) as mock_broadcast:

        # Simulate what your loop does with the parsed Redis data
        summary = transcription_complete_consumer.summarize.get_summary(
            parsed["summary_type"],
            parsed["transcript"],
            parsed["metadata"]["summary"],
            parsed["metadata"]["show_title"],
            parsed["metadata"]["show_summary"],
        )

        payload = {
            "job_id": parsed["job_id"],
            "status": "done",
            "summary": summary,
        }

        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(
            asyncio.create_task,
            transcription_complete_consumer.manager.broadcast(parsed["job_id"], payload)
        )

        await asyncio.sleep(0.1)  # let the event loop run

        mock_summarize.assert_called_once()
        mock_broadcast.assert_awaited_once_with("job123", payload)
