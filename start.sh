#!/bin/bash

# Start internal transcription service
uvicorn transcription_service.main:app --host 0.0.0.0 --port 8081 &

# Start summarization service using UNIX socket
uvicorn summarization_service.main:app --uds /tmp/summary.sock --proxy-headers &

# Start public podcast resolver service
uvicorn podcast_audio_resolver_service.main:app --host 0.0.0.0 --port 8080 &

# Start NGINX reverse proxy
nginx -g 'daemon off;'
