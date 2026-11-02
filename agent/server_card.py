"""MCP Server Card (SEP-2127 experimental extension)."""

from __future__ import annotations

import os

SCHEMA = "https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json"
CARD_NAME = "com.echobrief/mcp"
CARD_VERSION = "1.0.0"
# Schema maxLength is 100.
CARD_DESCRIPTION = "Summarize Apple/Spotify podcast episodes via EchoBrief agent tools."


def public_base_url() -> str:
    return (
        os.getenv("PUBLIC_BASE_URL")
        or os.getenv("BACKEND_PUBLIC_URL")
        or "https://echobrief-backend.onrender.com"
    ).rstrip("/")


def build_server_card() -> dict:
    base = public_base_url()
    return {
        "$schema": SCHEMA,
        "name": CARD_NAME,
        "version": CARD_VERSION,
        "description": CARD_DESCRIPTION,
        "title": "EchoBrief",
        "websiteUrl": "https://echobrief.onrender.com",
        "repository": {
            "url": "https://github.com/apatni24/EchoBrief",
            "source": "github",
        },
        "remotes": [
            {
                "type": "streamable-http",
                "url": f"{base}/mcp",
            }
        ],
    }
