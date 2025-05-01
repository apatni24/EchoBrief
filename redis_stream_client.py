import os
import redis
from dotenv import load_dotenv

load_dotenv()

# Load URL from env or paste your Upstash URL here
upstash_redis_host = os.getenv("UPSTASH_REDIS_HOST")
upstash_redis_port = os.getenv("UPSTASH_REDIS_PORT")
upstash_redis_password = os.getenv("UPSTASH_REDIS_PASSWORD")



# Create the Redis client
redis_client = redis.Redis(
    host=upstash_redis_host,
    port=upstash_redis_port,
    password=upstash_redis_password,
    ssl=True,                  # TLS is required for Upstash
    decode_responses=True
)

# Stream names
AUDIO_UPLOADED_STREAM = "audio_uploaded"
TRANSCRIPTION_COMPLETE_STREAM = "transcription_complete"
