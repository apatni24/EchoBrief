"""Point ENV=test at an in-memory Redis before service modules import it."""

import os

os.environ.setdefault("ENV", "test")

import pytest

import redis_stream_client
from tests.fake_redis import FakeRedis

FAKE_REDIS = FakeRedis()
redis_stream_client.redis_client = FAKE_REDIS


@pytest.fixture(autouse=True)
def _reset_fake_redis():
    FAKE_REDIS.flush()
    yield
    FAKE_REDIS.flush()
