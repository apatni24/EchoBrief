#!/bin/bash

# Start internal transcription service
uvicorn transcription_service.main:app --host 0.0.0.0 --port 8081 &

# Start summarization service
uvicorn summarization_service.main:app --host 0.0.0.0 --port 8082 --proxy-headers &

# Start resolver service
uvicorn podcast_audio_resolver_service.main:app --host 0.0.0.0 --port 8080 &

# Wait to ensure all services are running before NGINX starts
echo "⏳ Waiting 5 seconds for services to be ready..."
sleep 5

# Start NGINX last so it doesn’t race
nginx -g 'daemon off;'
