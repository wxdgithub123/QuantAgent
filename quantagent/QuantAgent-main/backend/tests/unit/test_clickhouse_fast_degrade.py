from app.services import clickhouse_service


def test_clickhouse_database_ensure_failure_sets_short_circuit(monkeypatch):
    ensure_calls = {"count": 0}

    def fail_ensure():
        ensure_calls["count"] += 1
        return False

    monkeypatch.setattr(clickhouse_service, "_client", None)
    monkeypatch.setattr(clickhouse_service, "_unavailable_until", 0.0)
    monkeypatch.setattr(clickhouse_service, "_ensure_database", fail_ensure)

    assert clickhouse_service._get_client() is None
    assert clickhouse_service._get_client() is None
    assert ensure_calls["count"] == 1


def test_clickhouse_client_failure_sets_short_circuit(monkeypatch):
    calls = {"count": 0}

    def fail_connect(*args, **kwargs):
        calls["count"] += 1
        raise RuntimeError("clickhouse offline")

    monkeypatch.setattr(clickhouse_service, "_client", None)
    monkeypatch.setattr(clickhouse_service, "_unavailable_until", 0.0)
    monkeypatch.setattr(clickhouse_service, "_ensure_database", lambda: True)
    monkeypatch.setattr(clickhouse_service, "_ch_connect", fail_connect)

    assert clickhouse_service._get_client() is None
    assert clickhouse_service._get_client() is None
    assert calls["count"] == 1
