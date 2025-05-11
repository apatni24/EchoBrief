import os
import redis
from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENV", "dev")  # default to dev

# Provide dummy values during tests
if ENV == "test":
    upstash_redis_host = "localhost"
    upstash_redis_port = 6379
    upstash_redis_password = None
else:
    upstash_redis_host = os.getenv("UPSTASH_REDIS_HOST")
    upstash_redis_port = int(os.getenv("UPSTASH_REDIS_PORT", "0"))  # convert to int
    upstash_redis_password = os.getenv("UPSTASH_REDIS_PASSWORD")

    # Fail fast if any required config is missing
    if not all([upstash_redis_host, upstash_redis_port, upstash_redis_password]):
        raise RuntimeError("Missing required Upstash Redis environment variables")

# Create the Redis client
redis_client = redis.Redis(
    host=upstash_redis_host,
    port=upstash_redis_port,
    password=upstash_redis_password,
    ssl=(ENV != "test"),            # TLS only for non-test envs
    decode_responses=True
)

# Stream names
AUDIO_UPLOADED_STREAM = "audio_uploaded"
TRANSCRIPTION_COMPLETE_STREAM = "transcription_complete"
