#!/bin/bash

# Start internal transcription service
uvicorn transcription_service.main:app --host 0.0.0.0 --port 8081 &

# Start summarization service
uvicorn summarization_service.main:app --host 0.0.0.0 --port 8082 --proxy-headers &

# Start resolver service
uvicorn podcast_audio_resolver_service.main:app --host 0.0.0.0 --port 8080 &

# Start NGINX last so it doesn’t race
nginx -g 'daemon off;'
