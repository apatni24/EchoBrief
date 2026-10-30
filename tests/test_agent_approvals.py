"""Spend ceiling and approval gate. Decision route stays unauthenticated."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent import approvals
from podcast_audio_resolver_service.main import app

client = TestClient(app)

APPLE = "https://podcasts.apple.com/us/podcast/episode?i=123456"


@patch("agent.policies.budget_max", return_value=0)
@patch("cache_service.CacheService.get_cached_episode", return_value=None)
@patch("podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple")
@patch("transcription_service.assemblyai_transcriber.transcribe_audio")
def test_budget_zero_waits_for_approval_and_does_not_call_upstream(
    mock_transcribe, mock_get_audio, _mock_cached, _mock_budget
):
    response = client.post("/agent/v1/episodes/summaries", json={"url": APPLE, "summary_type": "ts"})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "awaiting_approval"
    assert body["approval_id"]
    mock_get_audio.assert_not_called()
    mock_transcribe.assert_not_called()

    denied = client.post(
        f"/agent/v1/approvals/{body['approval_id']}/decision",
        json={"decision": "deny"},
    )
    assert denied.status_code == 200
    assert denied.json()["status"] == "cancelled"
    mock_get_audio.assert_not_called()


@patch("cache_service.CacheService.invalidate_specific_episode", return_value=True)
def test_invalidate_does_nothing_until_approved_and_second_approve_is_noop(mock_invalidate):
    pending = client.delete("/cache/invalidate/apple/123456/ts")
    assert pending.status_code == 202
    body = pending.json()
    assert body["status"] == "awaiting_approval"
    assert body["approval_id"]
    mock_invalidate.assert_not_called()

    approved = client.post(
        f"/agent/v1/approvals/{body['approval_id']}/decision",
        json={"decision": "approve"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "done"
    mock_invalidate.assert_called_once_with("apple", "123456", "ts")

    again = client.post(
        f"/agent/v1/approvals/{body['approval_id']}/decision",
        json={"decision": "approve"},
    )
    assert again.status_code == 200
    assert again.json()["job_id"] == approved.json()["job_id"]
    mock_invalidate.assert_called_once()


@patch("cache_service.CacheService.clear_cache", return_value=True)
def test_agent_clear_requires_approval_and_ignores_admin_key(mock_clear):
    pending = client.post("/agent/v1/cache/clear")
    assert pending.status_code == 202
    body = pending.json()
    assert "admin_key" not in pending.text
    mock_clear.assert_not_called()

    denied = client.post(
        f"/agent/v1/approvals/{body['approval_id']}/decision",
        json={"decision": "deny"},
    )
    assert denied.json()["status"] == "cancelled"
    mock_clear.assert_not_called()

    pending_again = client.post("/agent/v1/cache/clear")
    approved = client.post(
        f"/agent/v1/approvals/{pending_again.json()['approval_id']}/decision",
        json={"decision": "approve"},
    )
    assert approved.json()["status"] == "done"
    mock_clear.assert_called_once()


@patch("cache_service.CacheService.invalidate_specific_episode")
def test_expired_approval_is_409_and_missing_is_404(mock_invalidate):
    pending = client.delete("/cache/invalidate/spotify/abc/bs")
    approval_id = pending.json()["approval_id"]
    approval = approvals.get_approval(approval_id)
    approval["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    approvals._save(approval, 3600)

    late = client.post(
        f"/agent/v1/approvals/{approval_id}/decision",
        json={"decision": "approve"},
    )
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "approval_expired"
    mock_invalidate.assert_not_called()

    missing = client.post("/agent/v1/approvals/00000000-0000-4000-8000-000000000000/decision", json={"decision": "deny"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    bad = client.post(f"/agent/v1/approvals/{approval_id}/decision", json={"decision": "maybe"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_input"
