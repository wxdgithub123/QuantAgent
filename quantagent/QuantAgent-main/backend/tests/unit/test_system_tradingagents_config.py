from app.api.v1.endpoints.system_health import (
    _build_tradingagents_config_status,
    _redact_url,
)
from app.core.config import settings


def test_redact_url_hides_credentials_query_and_fragment():
    redacted = _redact_url("https://user:secret@example.com:8443/v1?api_key=abc#frag")

    assert redacted == "https://***:***@example.com:8443/v1"
    assert "secret" not in redacted
    assert "api_key" not in redacted
    assert "#" not in redacted


def test_tradingagents_config_reports_full_graph_readiness(monkeypatch):
    monkeypatch.setattr(settings, "USE_TRADINGAGENTS", True)
    monkeypatch.setattr(settings, "TRADINGAGENTS_SERVICE_URL", "http://ta-service:8010")
    monkeypatch.setattr(settings, "TRADINGAGENTS_TIMEOUT_SECONDS", 120.0)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-test")
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "https://user:secret@example.com/v1?token=abc")

    payload = _build_tradingagents_config_status(
        {
            "status": "ok",
            "http_status": 200,
            "service_url": "http://user:password@ta-service:8010?token=abc",
            "detail": {
                "status": "healthy",
                "mode": "quantagent_patched_graph",
                "llm_provider": "openai",
                "openai_configured": True,
                "openai_base_url": "https://user:secret@example.com/v1?token=abc",
                "openai_model": "gpt-test",
                "tradingagents_available": True,
                "native_graph": {
                    "available": True,
                    "manual_only": True,
                    "quick_model": "quick-model",
                    "deep_model": "deep-model",
                    "selected_analysts": ["market", "news"],
                },
            },
        }
    )

    assert payload["overall_status"] == "ready"
    assert payload["service"]["url"] == "http://***:***@ta-service:8010"
    assert payload["llm"]["baseUrl"] == "https://***:***@example.com/v1"
    assert payload["mode"]["configured"] == "quantagent_patched_graph"
    assert payload["mode"]["fullGraphReady"] is True
    assert payload["graph"]["strongAcceptanceEligible"] is True
    assert payload["data_boundary"]["agent_input_policy"] == "local_storage_only"
    assert payload["data_boundary"]["externalFallbackAllowed"] is False
    assert payload["data_boundary"]["pit_rule"] == "available_time <= as_of_time"


def test_tradingagents_config_keeps_fast_mode_ready_without_full_graph(monkeypatch):
    monkeypatch.setattr(settings, "USE_TRADINGAGENTS", True)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-test")
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1")

    payload = _build_tradingagents_config_status(
        {
            "status": "ok",
            "http_status": 200,
            "service_url": "http://ta-service:8010",
            "detail": {
                "mode": "context_adapter",
                "llm_provider": "openai",
                "openai_configured": False,
                "tradingagents_available": False,
            },
        }
    )

    assert payload["overall_status"] == "ready"
    assert payload["mode"]["fastResearchReady"] is True
    assert payload["mode"]["fullGraphReady"] is False
    assert payload["graph"]["strongAcceptanceEligible"] is False
    assert next(item for item in payload["readiness"] if item["id"] == "data_boundary")["status"] == "ready"
