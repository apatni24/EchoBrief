"""In-memory Redis stand-in for ENV=test.

Enough of the redis-py surface for job records, streams, and cache counters.
Not a server. Keys expire on read.
"""

import fnmatch
import time

import redis


class FakeRedis:
    def __init__(self):
        self.flush()

    def flush(self):
        self.store = {}
        self.lists = {}
        self.sets = {}
        self.streams = {}
        self.groups = {}
        self.acked = []
        self._seq = 0

    def _alive(self, key):
        item = self.store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and time.time() >= expires_at:
            self.store.pop(key, None)
            return None
        return value

    def ping(self):
        return True

    def get(self, key):
        return self._alive(key)

    def set(self, key, value, ex=None, nx=False, px=None):
        if nx and self._alive(key) is not None:
            return None
        expires_at = None
        if ex is not None:
            expires_at = time.time() + int(ex)
        elif px is not None:
            expires_at = time.time() + (int(px) / 1000.0)
        elif key in self.store and self._alive(key) is not None:
            expires_at = self.store[key][1]
        self.store[key] = (value if isinstance(value, str) else str(value), expires_at)
        return True

    def setex(self, key, time_seconds, value):
        self.store[key] = (value if isinstance(value, str) else str(value), time.time() + int(time_seconds))
        return True

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                removed += 1
            self.lists.pop(key, None)
            self.sets.pop(key, None)
        return removed

    def exists(self, key):
        return 1 if self._alive(key) is not None else 0

    def expire(self, key, seconds):
        value = self._alive(key)
        if value is None:
            return False
        self.store[key] = (value, time.time() + int(seconds))
        return True

    def incr(self, key):
        current = int(self._alive(key) or 0) + 1
        expires_at = None
        if key in self.store and self._alive(key) is not None:
            expires_at = self.store[key][1]
        self.store[key] = (str(current), expires_at)
        return current

    def decr(self, key):
        current = int(self._alive(key) or 0) - 1
        expires_at = None
        if key in self.store and self._alive(key) is not None:
            expires_at = self.store[key][1]
        self.store[key] = (str(current), expires_at)
        return current

    def keys(self, pattern):
        found = []
        for key in list(self.store):
            if self._alive(key) is not None and fnmatch.fnmatch(key, pattern):
                found.append(key)
        return found

    def rpush(self, key, *values):
        bucket = self.lists.setdefault(key, [])
        bucket.extend(values)
        return len(bucket)

    def lrange(self, key, start, end):
        bucket = self.lists.get(key, [])
        if end == -1:
            return bucket[start:]
        return bucket[start:end + 1]

    def sadd(self, key, *members):
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(members)
        return len(bucket) - before

    def srem(self, key, *members):
        bucket = self.sets.setdefault(key, set())
        removed = 0
        for member in members:
            if member in bucket:
                bucket.remove(member)
                removed += 1
        return removed

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def xadd(self, name, fields, id="*"):
        self._seq += 1
        message_id = f"{int(time.time() * 1000)}-{self._seq}"
        self.streams.setdefault(name, []).append((message_id, dict(fields)))
        return message_id

    def xtrim(self, name, maxlen=None, approximate=True, minid=None, limit=None):
        return 0

    def xgroup_create(self, name, groupname, id="$", mkstream=False):
        if mkstream:
            self.streams.setdefault(name, [])
        key = (name, groupname)
        if key in self.groups:
            raise redis.exceptions.ResponseError("BUSYGROUP Consumer Group name already exists")
        self.groups[key] = {"id": id, "pending": {}}
        return True

    def xinfo_groups(self, name):
        if name not in self.streams and not any(stream == name for stream, _group in self.groups):
            raise redis.exceptions.ResponseError("ERR no such key")
        return [
            {"name": group, "consumers": 1, "pending": len(meta.get("pending", {}))}
            for (stream, group), meta in self.groups.items()
            if stream == name
        ]

    def xreadgroup(self, groupname, consumername, streams, count=None, block=None):
        return []

    def xautoclaim(self, name, groupname, consumername, min_idle_time, start_id="0-0", count=None):
        return ["0-0", [], []]

    def xack(self, name, groupname, *ids):
        self.acked.extend(ids)
        pending = self.groups.get((name, groupname), {}).get("pending", {})
        acked = 0
        for message_id in ids:
            if message_id in pending:
                del pending[message_id]
            acked += 1
        return acked

    def xpending(self, name, groupname):
        key = (name, groupname)
        if key not in self.groups:
            raise redis.exceptions.ResponseError("NOGROUP No such consumer group")
        pending = self.groups[key].get("pending", {})
        if not pending:
            return {"pending": 0, "min": None, "max": None, "consumers": []}
        ids = sorted(pending)
        return {"pending": len(pending), "min": ids[0], "max": ids[-1], "consumers": []}

    def xpending_range(self, name, groupname, min, max, count, consumername=None):
        key = (name, groupname)
        if key not in self.groups:
            return []
        rows = []
        for message_id, meta in self.groups[key].get("pending", {}).items():
            if message_id < min or message_id > max:
                continue
            rows.append({
                "message_id": message_id,
                "consumer": meta.get("consumer"),
                "time_since_delivered": meta.get("idle", 0),
                "times_delivered": meta.get("times_delivered", 1),
            })
            if len(rows) >= count:
                break
        return rows
