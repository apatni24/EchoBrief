import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock

from transcription_service.audio_upload_consumer import _handle_message


@pytest.mark.asyncio
async def test_handle_message_success():
    parsed_data = {
        "file_path": "audio_files/fake.mp3",
        "metadata": {
            "summary": "Climate talk",
            "show_title": "TED Climate",
            "show_summary": "Storytelling and climate activism"
        },
        "summary_type": "ts",
        "job_id": "xyz123"
    }

    dummy_transcript = "This is a dummy transcript for testing."

    with patch("transcription_service.audio_upload_consumer.assemblyai_transcriber.transcribe_audio", return_value=dummy_transcript) as mock_transcribe, \
         patch("transcription_service.audio_upload_consumer.transcription_complete_producer.emit_transcription_completed") as mock_emit:

        await _handle_message(parsed_data)

        mock_transcribe.assert_called_once_with("audio_files/fake.mp3")
        mock_emit.assert_called_once()

        # Check the passed transcript in emit payload
        emitted_data = mock_emit.call_args[0][0]
        assert emitted_data["transcript"] == dummy_transcript
        assert emitted_data["job_id"] == "xyz123"
