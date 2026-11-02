"""MCP Streamable HTTP, server card, NLWeb /ask, sandbox, and cache_only."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.server_card import CARD_DESCRIPTION, SCHEMA, build_server_card
from podcast_audio_resolver_service.main import app

client = TestClient(app)
APPLE = "https://podcasts.apple.com/us/podcast/episode?i=999001"


def test_server_card_schema_and_paths():
    card = build_server_card()
    assert card["$schema"] == SCHEMA
    assert card["name"] == "com.echobrief/mcp"
    assert len(card["description"]) <= 100
    assert card["description"] == CARD_DESCRIPTION
    assert "tools" not in card
    assert card["remotes"][0]["type"] == "streamable-http"
    assert card["remotes"][0]["url"].endswith("/mcp")

    for path in ("/server-card", "/.well-known/mcp/server-card.json"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert body["$schema"] == SCHEMA
        assert "tools" not in body
        assert "application/mcp-server-card+json" in response.headers.get("content-type", "")


def test_mcp_initialize_and_tools_list():
    init = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
    )
    assert init.status_code == 200
    result = init.json()["result"]
    assert result["serverInfo"]["name"] == "echobrief"
    assert result["instructions"]
    assert "tools" in result["capabilities"]

    listed = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert listed.status_code == 200
    tools = {t["name"]: t for t in listed.json()["result"]["tools"]}
    for name in ("summarize_episode", "get_job", "get_summary", "get_health"):
        assert name in tools
        assert len(tools[name]["description"]) >= 20
        assert "inputSchema" in tools[name]
        assert "properties" in tools[name]["inputSchema"]


@patch("cache_service.CacheService.get_cached_episode")
def test_mcp_get_health_and_get_summary(mock_get_cached):
    health = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_health", "arguments": {}},
        },
    )
    assert health.status_code == 200
    body = health.json()["result"]["structuredContent"]
    assert body["status"] in {"ok", "degraded"}

    mock_get_cached.return_value = None
    missing = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_summary",
                "arguments": {
                    "platform": "apple",
                    "episode_id": "1",
                    "summary_type": "ts",
                },
            },
        },
    )
    assert missing.status_code == 200
    assert missing.json()["result"]["isError"] is True


@patch("cache_service.CacheService.get_cached_episode")
def test_cache_only_summarize_miss_is_404(mock_get_cached):
    mock_get_cached.return_value = None
    response = client.post(
        "/agent/v1/episodes/summaries?cache_only=true",
        json={"url": APPLE, "summary_type": "ts"},
        headers={"X-EchoBrief-Cache-Only": "true"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@patch("cache_service.CacheService.get_cached_episode")
def test_cache_only_summarize_hit(mock_get_cached):
    mock_get_cached.return_value = {
        "summary": "Cached",
        "metadata": {"title": "Hit"},
        "cached_at": 1,
    }
    response = client.post(
        "/agent/v1/episodes/summaries",
        json={"url": APPLE, "summary_type": "bs", "cache_only": True},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert response.json()["cached"] is True


def test_sandbox_docs():
    response = client.get("/agent/v1/sandbox")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "shared_production"
    assert "Idempotency-Key" in " ".join(body["recommendations"])
    assert body["docs_mcp"].startswith("deferred")


def test_nlweb_ask_json():
    response = client.post(
        "/ask",
        json={
            "query": {"text": "How do I summarize an episode and poll the job?"},
            "prefer": {"streaming": False},
            "meta": {"version": "0.55"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["_meta"]["version"] == "0.55"
    assert body["_meta"]["response_type"] == "answer"
    assert isinstance(body["results"], list) and body["results"]
    assert body["results"][0]["@type"] == "SearchSummary"
    ids = " ".join(str(item.get("identifier") or item.get("name") or "") for item in body["results"])
    assert "summarize_episode" in ids or "summarize" in body["results"][0]["text"].lower()


def test_nlweb_ask_streaming_sse():
    response = client.post(
        "/ask",
        json={
            "query": {"text": "What does get_health return?"},
            "prefer": {"streaming": True},
        },
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    text = response.text
    assert "event: start" in text
    assert "event: result" in text
    assert "event: complete" in text
    assert '"version": "0.55"' in text or '"version":"0.55"' in text
