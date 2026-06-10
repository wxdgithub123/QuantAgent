import pytest

from app.services import database


class _FailingRedis:
    def __init__(self):
        self.get_calls = 0
        self.closed = False

    async def get(self, key):
        self.get_calls += 1
        raise RuntimeError("redis offline")

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_redis_get_failure_short_circuits_followup_call(monkeypatch):
    client = _FailingRedis()
    monkeypatch.setattr(database, "_redis_client", client)
    monkeypatch.setattr(database, "_redis_unavailable_until", 0.0)
    monkeypatch.setattr(database, "_REDIS_OPERATION_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(database, "_REDIS_UNAVAILABLE_RETRY_SECONDS", 30.0)

    assert await database.redis_get("risk:config") is None
    assert client.get_calls == 1
    assert client.closed is True
    assert database._redis_unavailable_until > 0

    assert await database.redis_get("risk:kill_switch") is None
    assert client.get_calls == 1


def test_get_redis_returns_none_while_short_circuited(monkeypatch):
    monkeypatch.setattr(database, "_redis_client", None)
    monkeypatch.setattr(database, "_redis_unavailable_until", database.time.monotonic() + 30.0)

    assert database.get_redis() is None
