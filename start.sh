#!/bin/bash
set -e

# 1) Start transcription & resolver on TCP ports
uvicorn transcription_service.main:app --host 0.0.0.0 --port 8081 &
uvicorn podcast_audio_resolver_service.main:app --host 0.0.0.0 --port 8080 &

# 2) Start summarization on a Unix domain socket
#    --proxy-headers needed so Uvicorn trusts the upgrade headers from NGINX
uvicorn summarization_service.main:app \
  --uds /tmp/summary.sock \
  --proxy-headers &

# 3) Wait for the socket file to appear
echo "⏳ Waiting for /tmp/summary.sock to be created…"
while [ ! -S /tmp/summary.sock ]; do
  sleep 0.5
done
echo "✅ Socket is live, now starting NGINX"

# 4) Start NGINX (foreground)
nginx -g 'daemon off;'
