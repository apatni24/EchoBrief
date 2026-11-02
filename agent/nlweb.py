"""NLWeb v0.55 POST /ask — answers about EchoBrief capabilities from the catalog."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

from agent.catalog import HUMAN_OPERATIONS, KNOWN_LIMITS, OPERATIONS, build_capabilities

router = APIRouter(tags=["nlweb"])
NLWEB_VERSION = "0.55"
BASE_DOCS = "https://echobrief.onrender.com"
CAPABILITIES_PATH = "/.well-known/echobrief/capabilities.json"
OPENAPI_PATH = "/openapi.json"


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]+", (text or "").lower()) if len(t) > 1}


def _score_operation(query_tokens: set[str], operation: dict) -> int:
    haystack = " ".join(
        [
            operation.get("id", ""),
            operation.get("title", ""),
            operation.get("description", ""),
            " ".join(operation.get("effects") or []),
            str(operation.get("risk") or ""),
            str((operation.get("invocation") or {}).get("path") or ""),
        ]
    ).lower()
    score = 0
    for token in query_tokens:
        if token in haystack:
            score += 2 if token == operation.get("id") else 1
    return score


def _summary_text(query: str, matched: list[dict]) -> str:
    if not matched:
        return (
            "EchoBrief answers questions about its agent API and capabilities here. "
            "It is not a general podcast chatbot. Discover operations at "
            f"{CAPABILITIES_PATH} or OpenAPI at {OPENAPI_PATH}. "
            "Supported agent tools include summarize_episode, get_job, get_summary, and get_health."
        )
    lines = [
        f"EchoBrief capability answers for: {query.strip() or '(empty)'}",
        "Matched catalog operations (not a podcast Q&A):",
    ]
    for op in matched:
        inv = op.get("invocation") or {}
        lines.append(
            f"- {op['id']}: {op.get('title')} — {inv.get('method')} {inv.get('path')} "
            f"(risk={op.get('risk')}, mode={op.get('mode')})."
        )
    lines.append("Production is shared; prefer Idempotency-Key and get_summary / cache_only for dry reads.")
    return "\n".join(lines)


def _article_for_operation(operation: dict) -> dict:
    inv = operation.get("invocation") or {}
    return {
        "@type": "Article",
        "@context": "https://schema.org",
        "name": operation.get("title") or operation.get("id"),
        "identifier": operation.get("id"),
        "description": (operation.get("description") or "")[:500],
        "url": f"{BASE_DOCS}{CAPABILITIES_PATH}#{operation.get('id')}",
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "method", "value": inv.get("method")},
            {"@type": "PropertyValue", "name": "path", "value": inv.get("path")},
            {"@type": "PropertyValue", "name": "risk", "value": operation.get("risk")},
            {"@type": "PropertyValue", "name": "mode", "value": operation.get("mode")},
        ],
    }


def build_answer(body: dict | None) -> dict:
    body = body or {}
    query_obj = body.get("query") if isinstance(body.get("query"), dict) else {}
    text = ""
    if isinstance(body.get("query"), str):
        text = body["query"]
    else:
        text = (query_obj or {}).get("text") or ""
    tokens = _tokenize(text)

    # Always include a short overview hit for capability/health/openapi keywords.
    overview_boost = any(
        t in tokens
        for t in ("capability", "capabilities", "openapi", "mcp", "health", "agent", "api", "sandbox")
    )

    scored: list[tuple[int, dict]] = []
    for operation in OPERATIONS + HUMAN_OPERATIONS:
        score = _score_operation(tokens, operation)
        if overview_boost and operation["id"] in ("summarize_episode", "get_health", "get_summary", "get_job"):
            score += 1
        if score > 0:
            scored.append((score, operation))
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    matched = [op for _, op in scored[:5]]

    if not matched and tokens:
        # Fallback: surface the four core agent tools so the endpoint stays useful.
        by_id = {op["id"]: op for op in OPERATIONS}
        matched = [by_id[i] for i in ("summarize_episode", "get_job", "get_summary", "get_health") if i in by_id]

    results: list[dict[str, Any]] = [
        {
            "@type": "SearchSummary",
            "@context": "https://schema.org",
            "text": _summary_text(text, matched),
        }
    ]
    for operation in matched:
        results.append(_article_for_operation(operation))

    if any(t in tokens for t in ("limit", "limits", "duration", "budget", "approval")):
        results.append(
            {
                "@type": "Article",
                "@context": "https://schema.org",
                "name": "Known limits",
                "description": " ".join(KNOWN_LIMITS)[:800],
                "url": f"{BASE_DOCS}{CAPABILITIES_PATH}",
            }
        )

    query_id = str(uuid.uuid4())
    return {
        "_meta": {
            "response_type": "answer",
            "version": NLWEB_VERSION,
            "query_id": query_id,
        },
        "results": results,
        # Additive flat fields some clients still expect.
        "answer": results[0]["text"],
        "query": text,
    }


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_answer(answer: dict) -> AsyncIterator[bytes]:
    yield _sse_event(
        "start",
        {"_meta": {"response_type": "answer", "version": NLWEB_VERSION, "streaming": True}},
    ).encode()
    for index, item in enumerate(answer.get("results") or []):
        yield _sse_event("result", {"index": index, "item": item}).encode()
    yield _sse_event("complete", {"_meta": {"version": NLWEB_VERSION}}).encode()


def _wants_streaming(body: dict | None, accept: str | None) -> bool:
    prefer = (body or {}).get("prefer") if isinstance((body or {}).get("prefer"), dict) else {}
    if prefer.get("streaming") is True:
        return True
    if prefer.get("streaming") is False:
        return False
    accept = (accept or "").lower()
    return "text/event-stream" in accept


@router.post("/ask")
async def ask(request: Request, accept: str | None = Header(default=None, alias="Accept")):
    raw = await request.body()
    if len(raw) > 64 * 1024:
        return JSONResponse(
            status_code=413,
            content={
                "_meta": {"response_type": "failure", "version": NLWEB_VERSION},
                "error": {"code": "payload_too_large", "message": "Body must be ≤64 KiB."},
            },
        )
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "_meta": {"response_type": "failure", "version": NLWEB_VERSION},
                "error": {"code": "invalid_json", "message": "Body must be JSON."},
            },
        )
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={
                "_meta": {"response_type": "failure", "version": NLWEB_VERSION},
                "error": {"code": "invalid_request", "message": "Body must be a JSON object."},
            },
        )

    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    if meta.get("version") and str(meta.get("version")) != NLWEB_VERSION:
        return JSONResponse(
            status_code=400,
            content={
                "_meta": {"response_type": "failure", "version": NLWEB_VERSION},
                "error": {
                    "code": "unsupported_version",
                    "message": f"Only NLWeb {NLWEB_VERSION} is supported.",
                },
            },
        )

    answer = build_answer(body)
    if _wants_streaming(body, accept):
        return StreamingResponse(
            _stream_answer(answer),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    return JSONResponse(content=answer)


@router.get("/ask")
async def ask_help():
    """Human-readable hint; NLWeb queries use POST."""
    caps = build_capabilities()
    return {
        "protocol": "nlweb",
        "version": NLWEB_VERSION,
        "usage": "POST /ask with {\"query\":{\"text\":\"...\"},\"prefer\":{\"streaming\":false}}",
        "scope": "Answers questions about EchoBrief agent capabilities from the in-repo catalog/OpenAPI. Not a podcast chatbot.",
        "operations": [op["id"] for op in caps["operations"] if op["id"] in {
            "summarize_episode", "get_job", "get_summary", "get_health"
        }],
        "docs_mcp": "deferred",
    }
