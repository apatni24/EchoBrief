#!/bin/bash

# Start internal transcription service (not publicly exposed)
uvicorn transcription_service.main:app --host 0.0.0.0 --port 8081 &

# Start public WebSocket summarization service
uvicorn summarization_service.main:app --host 0.0.0.0 --port 8082 --proxy-headers &

# Start public podcast resolver service
uvicorn podcast_audio_resolver_service.main:app --host 0.0.0.0 --port 8080 &

# Start NGINX reverse proxy (bring to foreground so container stays alive)
nginx -g 'daemon off;'
