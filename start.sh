#!/bin/bash
set -e

# Render-compatible service initialization

# 1) Start internal services with explicit port binding
uvicorn transcription_service.main:app --host 0.0.0.0 --port 8081 &
uvicorn podcast_audio_resolver_service.main:app --host 0.0.0.0 --port 8080 &

# 2) Start WebSocket service on port 8082 (Render requires TCP ports)
uvicorn summarization_service.main:app \
  --host 0.0.0.0 \
  --port 8082 \
  --proxy-headers &

# 3) Start NGINX with Render-optimized config
nginx -g 'daemon off;'
