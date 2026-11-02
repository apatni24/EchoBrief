"""Minimal Streamable HTTP MCP transport wrapping product tools."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response
from starlette.responses import StreamingResponse

from agent import mcp_tools

router = APIRouter(tags=["mcp"])

JSONRPC_PARSE = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL = -32603


def _rpc_error(req_id: Any, code: int, message: str, data: Any = None) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": error}


def _rpc_result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _handle_message(message: dict) -> dict | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _rpc_error(None, JSONRPC_INVALID_REQUEST, "Invalid Request")

    method = message.get("method")
    req_id = message.get("id", None)
    params = message.get("params") or {}
    is_notification = "id" not in message

    try:
        if method == "initialize":
            return _rpc_result(req_id, mcp_tools.initialize_result())
        if method == "notifications/initialized":
            return None if is_notification else _rpc_result(req_id, {})
        if method == "ping":
            return None if is_notification else _rpc_result(req_id, {})
        if method == "tools/list":
            return _rpc_result(req_id, {"tools": mcp_tools.tool_definitions()})
        if method == "tools/call":
            if not isinstance(params, dict) or not params.get("name"):
                return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, "name is required")
            result = mcp_tools.call_tool(params.get("name"), params.get("arguments") or {})
            return _rpc_result(req_id, result)
        if is_notification:
            return None
        return _rpc_error(req_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")
    except Exception as exc:
        if is_notification:
            return None
        return _rpc_error(req_id, JSONRPC_INTERNAL, "Internal error", str(exc))


def _wants_sse(accept: str | None) -> bool:
    accept = (accept or "").lower()
    if "text/event-stream" in accept and "application/json" not in accept:
        return True
    return False


def _sse_encode(payload: dict) -> str:
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


@router.post("/mcp")
async def mcp_post(
    request: Request,
    accept: str | None = Header(default=None, alias="Accept"),
    protocol_version: str | None = Header(default=None, alias="Mcp-Protocol-Version"),
):
    try:
        body = await request.json()
    except Exception:
        payload = _rpc_error(None, JSONRPC_PARSE, "Parse error")
        return JSONResponse(status_code=400, content=payload)

    headers = {}
    if protocol_version:
        headers["Mcp-Protocol-Version"] = protocol_version
    else:
        headers["Mcp-Protocol-Version"] = mcp_tools.PROTOCOL_VERSION

    if isinstance(body, list):
        responses = []
        for item in body:
            if not isinstance(item, dict):
                responses.append(_rpc_error(None, JSONRPC_INVALID_REQUEST, "Invalid Request"))
                continue
            handled = _handle_message(item)
            if handled is not None:
                responses.append(handled)
        if not responses:
            return Response(status_code=202, headers=headers)
        if _wants_sse(accept):

            async def batch_stream():
                for item in responses:
                    yield _sse_encode(item)

            return StreamingResponse(
                batch_stream(),
                media_type="text/event-stream",
                headers={**headers, "Cache-Control": "no-cache"},
            )
        return JSONResponse(content=responses, headers=headers)

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content=_rpc_error(None, JSONRPC_INVALID_REQUEST, "Invalid Request"),
            headers=headers,
        )

    handled = _handle_message(body)
    if handled is None:
        return Response(status_code=202, headers=headers)

    if _wants_sse(accept):

        async def single_stream():
            yield _sse_encode(handled)

        return StreamingResponse(
            single_stream(),
            media_type="text/event-stream",
            headers={**headers, "Cache-Control": "no-cache"},
        )
    return JSONResponse(content=handled, headers=headers)


@router.get("/mcp")
async def mcp_get(
    protocol_version: str | None = Header(default=None, alias="Mcp-Protocol-Version"),
):
    """Streamable HTTP GET opens a server stream; this server is request/response only."""
    headers = {
        "Mcp-Protocol-Version": protocol_version or mcp_tools.PROTOCOL_VERSION,
        "Cache-Control": "no-cache",
    }

    async def empty_stream():
        # Keep the stream briefly open so clients that probe GET do not see an immediate close.
        yield ": connected\n\n"

    return StreamingResponse(empty_stream(), media_type="text/event-stream", headers=headers)


@router.delete("/mcp")
async def mcp_delete():
    return Response(status_code=204)
