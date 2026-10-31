"""Agent HTTP: catalog, cache hit, miss, poll, validation, and summary lookup."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from agent import jobs
from agent.catalog import OPERATIONS, all_operations
from podcast_audio_resolver_service.main import app

client = TestClient(app)

APPLE = "https://podcasts.apple.com/us/podcast/episode?i=123456"
AUDIO = {
    "file_path": "audio_files/test.mp3",
    "file_hash": "abc",
    "metadata": {"title": "Test Episode", "duration": 600},
}


def test_capabilities_document():
    response = client.get("/.well-known/echobrief/capabilities.json")
    assert response.status_code == 200
    body = response.json()
    by_id = {item["id"]: item for item in body["operations"]}
    for operation_id in ("summarize_episode", "get_job", "get_summary", "get_health"):
        operation = by_id[operation_id]
        assert operation["input_schema"]
        assert operation["effects"]
        assert operation["timeout_seconds"]
    assert by_id["invalidate_episode_cache"]["approval_policy"]
    assert by_id["clear_cache"]["approval_policy"]
    assert "admin_key" not in response.text
    human_ids = {item["id"] for item in body["human_operations"]}
    assert human_ids == {"decide_approval"}
    assert "itunes_duration" in " ".join(body["known_limits"])


@patch("cache_service.CacheService.get_cached_episode")
def test_summarize_cache_hit_is_done(mock_get_cached):
    mock_get_cached.return_value = {
        "summary": "Cached summary",
        "metadata": {"title": "Cached Episode"},
        "cached_at": 1234567890,
    }
    response = client.post("/agent/v1/episodes/summaries", json={"url": APPLE, "summary_type": "ts"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["cached"] is True
    assert body["job_id"]
    assert body["result"]["summary"] == "Cached summary"
    assert "artifacts" not in body
    assert "file_hash" not in body


@patch("cache_service.CacheService.get_cached_episode")
@patch("podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple")
@patch("podcast_audio_resolver_service.audio_upload_producer.emit_audio_uploaded")
def test_summarize_miss_poll_and_idempotency(mock_emit, mock_get_audio, mock_get_cached):
    mock_get_cached.return_value = None
    mock_get_audio.return_value = AUDIO

    first = client.post(
        "/agent/v1/episodes/summaries",
        json={"url": APPLE, "summary_type": "ns"},
        headers={"Idempotency-Key": "same-key"},
    )
    assert first.status_code == 202
    body = first.json()
    assert body["status"] in {"accepted", "resolving"}
    assert body["job_id"]
    assert body["poll_url"] == f"/agent/v1/jobs/{body['job_id']}"

    second = client.post(
        "/agent/v1/episodes/summaries",
        json={"url": APPLE, "summary_type": "ns"},
        headers={"Idempotency-Key": "same-key"},
    )
    assert second.status_code == 202
    assert second.json()["job_id"] == body["job_id"]
    mock_get_audio.assert_called_once()

    overlap = client.post("/agent/v1/episodes/summaries", json={"url": APPLE, "summary_type": "ns"})
    assert overlap.json()["job_id"] == body["job_id"]

    conflict = client.post(
        "/agent/v1/episodes/summaries",
        json={"url": APPLE, "summary_type": "bs"},
        headers={"Idempotency-Key": "same-key"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"

    jobs.transition(body["job_id"], "transcribing")
    jobs.transition(body["job_id"], "summarizing")
    jobs.complete_job(body["job_id"], {"summary": "Finished", "cached": False, "metadata": {"title": "Test Episode"}})
    polled = client.get(body["poll_url"])
    assert polled.status_code == 200
    assert polled.json()["status"] == "done"
    assert polled.json()["result"]["summary"] == "Finished"


def test_validation_errors_are_error_objects():
    empty = client.post("/agent/v1/episodes/summaries", json={"url": "", "summary_type": "ts"})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "invalid_input"

    bad_type = client.post("/agent/v1/episodes/summaries", json={"url": APPLE, "summary_type": "nope"})
    assert bad_type.status_code == 400
    assert bad_type.json()["error"]["code"] == "invalid_input"

    bad_platform = client.post(
        "/agent/v1/episodes/summaries",
        json={"url": "https://example.com/ep", "summary_type": "ts"},
    )
    assert bad_platform.status_code == 400
    assert bad_platform.json()["error"]["code"] == "unsupported_platform"


@patch("cache_service.CacheService.get_cached_episode", return_value=None)
def test_get_summary_miss_does_not_start_a_job(mock_get_cached):
    response = client.get(
        "/agent/v1/summaries",
        params={"platform": "apple", "episode_id": "123456", "summary_type": "ts"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert jobs.redis_client.smembers(jobs.ACTIVE_KEY) == set()
    mock_get_cached.assert_called_once()


def test_unknown_job_and_health():
    missing = client.get("/agent/v1/jobs/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["redis"] == "ok"
    assert "consumer_groups" in body


def test_openapi_matches_catalog():
    schema = client.get("/openapi.json").json()
    found = {}
    for methods in schema["paths"].values():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "delete", "patch"}:
                continue
            operation_id = operation.get("operationId")
            if operation_id:
                found[operation_id] = operation
    for operation in all_operations():
        assert operation["id"] in found, operation["id"]
        assert found[operation["id"]]["x-echobrief-effects"] == operation["effects"]
        assert found[operation["id"]]["x-echobrief-operation"] == operation["id"]
    listed = {item["id"] for item in OPERATIONS}
    assert listed <= set(found)
