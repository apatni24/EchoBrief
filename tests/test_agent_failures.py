"""Deadlines, retries, resume, dead letter, producer failures, and audit hooks."""

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent import jobs
from agent.delivery import fail_stage
from agent.errors import error_dict, is_transient_exception
from podcast_audio_resolver_service.main import app
from redis_stream_client import (
    AUDIO_UPLOADED_STREAM,
    JOBS_DLQ_STREAM,
    TRANSCRIPTION_COMPLETE_STREAM,
    TRANSCRIPTION_GROUP,
    SUMMARIZATION_GROUP,
    ensure_consumer_group,
    group_exists,
    redis_client,
    trim_acked_history,
)
from summarization_service.transcription_complete_consumer import (
    handle_transcription_complete,
    prepare_summary_consumer,
)
from transcription_service.audio_upload_consumer import _handle_message, prepare_audio_consumer

client = TestClient(app)

APPLE = "https://podcasts.apple.com/us/podcast/episode?i=123456"


def test_poll_reports_timeout_after_deadline():
    job = jobs.create_job(
        operation="summarize_episode",
        status="resolving",
        input_data={"url": APPLE, "summary_type": "ts"},
        platform="apple",
        episode_id="123456",
    )
    job["deadline_at"] = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
    jobs.save_job(job)

    response = client.get(f"/agent/v1/jobs/{job['job_id']}")
    assert response.status_code == 504
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "timeout"
    assert body["error"]["retryable"] is True


def test_dead_letter_after_three_failures():
    job = jobs.create_job(
        operation="summarize_episode",
        status="transcribing",
        input_data={"url": APPLE, "summary_type": "ts"},
        platform="apple",
        episode_id="123456",
    )
    ensure_consumer_group(AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP)
    entry = {"job_id": job["job_id"], "file_path": "audio_files/missing.mp3"}
    assert fail_stage(
        job_id=job["job_id"],
        stage="transcribing",
        code="upstream_unavailable",
        message="Transcription failed.",
        retryable=True,
        stream=AUDIO_UPLOADED_STREAM,
        group=TRANSCRIPTION_GROUP,
        message_id="1-1",
        entry=entry,
    ) == "pending"
    assert fail_stage(
        job_id=job["job_id"],
        stage="transcribing",
        code="upstream_unavailable",
        message="Transcription failed.",
        retryable=True,
        stream=AUDIO_UPLOADED_STREAM,
        group=TRANSCRIPTION_GROUP,
        message_id="1-1",
        entry=entry,
    ) == "pending"
    assert jobs.get_job(job["job_id"])["status"] == "transcribing"
    assert fail_stage(
        job_id=job["job_id"],
        stage="transcribing",
        code="upstream_unavailable",
        message="Transcription failed.",
        retryable=True,
        stream=AUDIO_UPLOADED_STREAM,
        group=TRANSCRIPTION_GROUP,
        message_id="1-1",
        entry=entry,
    ) == "acked"
    stored = jobs.get_job(job["job_id"])
    assert stored["status"] == "failed"
    assert stored["error"]["code"] == "upstream_unavailable"
    assert redis_client.streams[JOBS_DLQ_STREAM]
    assert "1-1" in redis_client.acked
    assert "transcript" not in redis_client.streams[JOBS_DLQ_STREAM][0][1]["data"]


def test_permanent_errors_are_not_transient():
    class Response:
        status_code = 429

    class HTTPError(Exception):
        def __init__(self):
            self.response = Response()

    assert is_transient_exception(HTTPError()) is True
    assert is_transient_exception(TimeoutError("request timeout")) is True
    assert is_transient_exception(RuntimeError("Failed to process after 3 attempts")) is False
    assert is_transient_exception(RuntimeError("request too large: 413")) is False
    assert is_transient_exception(RuntimeError("episode_too_long")) is False


@patch("cache_service.CacheService.get_cached_episode", return_value=None)
@patch("podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple")
@patch("transcription_service.transcription_complete_producer.emit_transcription_completed")
@patch("cache_service.CacheService.get_cached_transcript_by_hash")
def test_retry_resumes_without_download_or_transcription(mock_transcript, mock_emit, mock_get_audio, _cached):
    mock_transcript.return_value = {"transcript": "already transcribed"}
    job = jobs.create_job(
        operation="summarize_episode",
        status="failed",
        input_data={"url": APPLE, "summary_type": "ts"},
        platform="apple",
        episode_id="123456",
        with_deadline=False,
        error=error_dict("upstream_unavailable", retryable=True),
    )
    job["file_hash"] = "file-hash"
    job["artifacts"] = {"file_path": "audio_files/test.mp3", "metadata": {"title": "Test"}}
    jobs.save_job(job)

    response = client.post(f"/agent/v1/jobs/{job['job_id']}/retry")
    assert response.status_code == 202
    assert response.json()["status"] == "summarizing"
    mock_get_audio.assert_not_called()
    mock_emit.assert_called_once()
    emitted = mock_emit.call_args[0][0]
    assert emitted["transcript"] == "already transcribed"
    assert emitted["job_id"] == job["job_id"]


@patch("cache_service.CacheService.get_cached_episode", return_value=None)
@patch("podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple")
@patch("podcast_audio_resolver_service.audio_upload_producer.emit_audio_uploaded")
def test_publish_failure_is_visible(mock_emit, mock_get_audio, _cached):
    mock_get_audio.return_value = {
        "file_path": "audio_files/test.mp3",
        "metadata": {"title": "Test", "duration": 120},
    }
    mock_emit.side_effect = RuntimeError("xadd failed")

    agent = client.post("/agent/v1/episodes/summaries", json={"url": APPLE, "summary_type": "bs"})
    assert agent.status_code == 502
    assert agent.json()["error"]["code"] == "upstream_unavailable"
    job_id = agent.json()["job_id"]
    assert jobs.get_job(job_id)["status"] == "failed"

    human = client.post(
        "/submit",
        json={"url": "https://podcasts.apple.com/us/podcast/episode?i=654321", "summary_type": "bs"},
    )
    assert human.status_code == 200
    assert human.json()["error"] is True
    assert human.json()["message"] == "Failed to start processing. Please try again."


def test_consumer_startup_creates_group_at_dollar_without_trim():
    audio_source = inspect.getsource(prepare_audio_consumer)
    summary_source = inspect.getsource(prepare_summary_consumer)
    audio_file = Path("transcription_service/audio_upload_consumer.py").read_text()
    summary_file = Path("summarization_service/transcription_complete_consumer.py").read_text()
    assert "maxlen=0" not in audio_source
    assert "maxlen=0" not in summary_source
    assert "maxlen=0" not in audio_file
    assert "maxlen=0" not in summary_file
    assert 'id="$"' in inspect.getsource(ensure_consumer_group)

    prepare_audio_consumer()
    prepare_audio_consumer()
    prepare_summary_consumer()
    assert group_exists(AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP)
    assert group_exists(TRANSCRIPTION_COMPLETE_STREAM, SUMMARIZATION_GROUP)
    assert redis_client.groups[(AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP)]["id"] == "$"


def test_trim_skips_when_pending_lookup_fails(monkeypatch):
    called = {"trim": 0}

    def boom(*_args, **_kwargs):
        raise RuntimeError("nogroup")

    def record(*_args, **_kwargs):
        called["trim"] += 1
        return 0

    monkeypatch.setattr(redis_client, "xpending", boom)
    monkeypatch.setattr(redis_client, "xtrim", record)
    trim_acked_history(AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP)
    assert called["trim"] == 0


def test_rate_limited_when_cooldown_exceeds_deadline():
    job = jobs.create_job(
        operation="summarize_episode",
        status="summarizing",
        input_data={"url": APPLE, "summary_type": "ts"},
        platform="apple",
        episode_id="123456",
    )
    parsed = {
        "job_id": job["job_id"],
        "summary_type": "ts",
        "transcript": "hello",
        "metadata": {"summary": "s", "show_title": "t", "show_summary": "ss"},
        "platform": "apple",
        "episode_id": "123456",
    }
    with patch(
        "summarization_service.transcription_complete_consumer.summarize.cooldown_remaining",
        return_value=1000,
    ), patch(
        "summarization_service.transcription_complete_consumer.summarize.get_summary",
    ) as mock_summary:
        handle_transcription_complete(parsed, message_id="9-1", loop=None)
        mock_summary.assert_not_called()
    stored = jobs.get_job(job["job_id"])
    assert stored["status"] == "summarizing"
    assert stored["error"]["code"] == "rate_limited"
    assert stored["error"]["retry_after_seconds"] >= 1000
    assert "9-1" not in redis_client.acked

    polled = client.get(f"/agent/v1/jobs/{job['job_id']}")
    assert polled.status_code == 429
    assert polled.json()["error"]["code"] == "rate_limited"


def test_webhook_is_optional(monkeypatch):
    job = jobs.create_job(
        operation="summarize_episode",
        status="summarizing",
        input_data={"url": APPLE, "summary_type": "ts"},
        platform="apple",
        episode_id="123456",
    )
    monkeypatch.delenv("ECHOBRIEF_WEBHOOK_URL", raising=False)
    with patch("agent.webhook.requests.post") as mock_post:
        done = jobs.complete_job(job["job_id"], {"summary": "ok", "cached": False})
        assert done["status"] == "done"
        mock_post.assert_not_called()

    job = jobs.create_job(
        operation="summarize_episode",
        status="summarizing",
        input_data={"url": APPLE, "summary_type": "ns"},
        platform="apple",
        episode_id="999",
    )
    monkeypatch.setenv("ECHOBRIEF_WEBHOOK_URL", "http://example.test/hook")
    with patch("agent.webhook.requests.post") as mock_post:
        jobs.complete_job(job["job_id"], {"summary": "ok", "cached": False})
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["event"] == "job.completed"
        assert payload["job_id"] == job["job_id"]
        assert mock_post.call_args.kwargs["timeout"] == 3

    job = jobs.create_job(
        operation="summarize_episode",
        status="summarizing",
        input_data={"url": APPLE, "summary_type": "bs"},
        platform="apple",
        episode_id="888",
    )
    with patch("agent.webhook.requests.post", side_effect=RuntimeError("down")):
        done = jobs.complete_job(job["job_id"], {"summary": "ok", "cached": False})
    assert done["status"] == "done"


def test_nginx_proxies_agent_routes_and_keeps_human_routes():
    conf = Path("nginx.conf").read_text()
    for snippet in (
        "location /agent/",
        "location /.well-known/echobrief/",
        "location = /health",
        "location = /openapi.json",
        "location /submit",
        "location /cache/",
        "location /ws/",
        "location /internal",
    ):
        assert snippet in conf
    assert "proxy_pass http://resolver_backend" in conf


def test_missing_audio_fails_before_ack():
    job = jobs.create_job(
        operation="summarize_episode",
        status="accepted",
        input_data={"url": APPLE, "summary_type": "ts"},
        platform="apple",
        episode_id="123456",
    )
    import asyncio

    asyncio.run(_handle_message({
        "job_id": job["job_id"],
        "file_path": "audio_files/does-not-exist.mp3",
        "metadata": {},
        "summary_type": "ts",
    }, message_id="4-1"))
    stored = jobs.get_job(job["job_id"])
    assert stored["status"] == "failed"
    assert stored["error"]["code"] == "audio_missing"
    assert stored["error"]["retryable"] is False
    assert "4-1" in redis_client.acked


def test_summarization_websocket_payloads_stay_compatible():
    job = jobs.create_job(
        operation="summarize_episode",
        status="summarizing",
        input_data={"url": APPLE, "summary_type": "ts"},
        platform="apple",
        episode_id="123456",
    )
    payloads = []

    def capture(_loop, _job_id, payload):
        payloads.append(payload)

    parsed = {
        "job_id": job["job_id"],
        "summary_type": "ts",
        "transcript": "Climate change is real.",
        "metadata": {
            "summary": "Climate story",
            "show_title": "Planet Voices",
            "show_summary": "Voices from the climate frontlines",
            "episode_title": "Episode",
            "duration": 600,
        },
        "platform": "apple",
        "episode_id": "123456",
        "file_path": "audio_files/test.mp3",
        "processing_time": 1,
    }
    with patch(
        "summarization_service.transcription_complete_consumer._broadcast",
        side_effect=capture,
    ), patch(
        "summarization_service.transcription_complete_consumer.summarize.get_summary",
        return_value="A short summary",
    ):
        handle_transcription_complete(parsed, message_id="8-1", loop=object())

    assert payloads[0] == {
        "job_id": job["job_id"],
        "status": "summarization_received",
        "message": "Received for summarization. Generating summary...",
    }
    assert payloads[1]["status"] == "done"
    assert payloads[1]["summary"] == "A short summary"
    assert payloads[1]["job_id"] == job["job_id"]
    stored = jobs.get_job(job["job_id"])
    assert stored["status"] == "done"
    assert "transcript" not in (stored.get("result") or {})
    assert "8-1" in redis_client.acked


def test_audit_route_has_events_without_transcript_text():
    job = jobs.create_job(
        operation="summarize_episode",
        status="accepted",
        input_data={"url": APPLE, "summary_type": "ts"},
        platform="apple",
        episode_id="123456",
    )
    response = client.get(f"/agent/v1/jobs/{job['job_id']}/audit")
    assert response.status_code == 200
    audit = response.json()["audit"]
    assert audit
    assert "transcript" not in response.text
    assert audit[0]["event"] == "created"
