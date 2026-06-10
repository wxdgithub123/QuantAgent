from app.api.v1.endpoints import config_center


def test_agent_id_normalization():
    assert config_center._agent_id(" Macro Agent v2 ") == "macro_agent_v2"


def test_normalize_agent_uses_default_llm_when_unset():
    payload = config_center.AgentConfigPayload(
        agent_id="news-plus",
        display_name="News Plus",
        prompt="Summarize local news only.",
        skill="news",
    )

    agent = config_center._normalize_agent(
        payload,
        {"provider": "openai", "model": "gpt-4o", "baseUrl": "https://example.test/v1"},
    )

    assert agent["agent_id"] == "news-plus"
    assert agent["effective_llm"]["provider"] == "openai"
    assert agent["effective_llm"]["model"] == "gpt-4o"
    assert agent["effective_llm"]["uses_default"] is True
    assert agent["schema_version"] == "custom_agent_config.v1"


def test_normalize_agent_keeps_independent_llm():
    payload = config_center.AgentConfigPayload(
        agent_id="risk-local",
        display_name="Risk Local",
        llm_provider="ollama",
        model="qwen2.5",
        base_url="http://localhost:11434",
    )

    agent = config_center._normalize_agent(payload, {"provider": "openai", "model": "gpt-4o"})

    assert agent["effective_llm"]["provider"] == "ollama"
    assert agent["effective_llm"]["model"] == "qwen2.5"
    assert agent["effective_llm"]["uses_default"] is False


def test_role_config_normalization_preserves_defaults_and_effective_llm():
    roles = config_center._normalize_role_configs(
        {
            "market_analyst": {
                "enabled": False,
                "prompt": "Use only local PIT bars.",
                "skill": "custom_market_scan",
            },
            "trader": {
                "llm_provider": "ollama",
                "model": "qwen2.5",
                "base_url": "http://localhost:11434",
            },
        },
        {"provider": "openai", "model": "gpt-4o", "baseUrl": "https://llm.example/v1"},
    )

    assert roles["market_analyst"]["enabled"] is False
    assert roles["market_analyst"]["prompt_version"] == "market_analyst.v1"
    assert roles["market_analyst"]["prompt"] == "Use only local PIT bars."
    assert roles["market_analyst"]["skill"] == "custom_market_scan"
    assert roles["market_analyst"]["effective_llm"]["provider"] == "openai"
    assert roles["market_analyst"]["effective_llm"]["uses_default"] is True

    assert roles["trader"]["effective_llm"]["provider"] == "ollama"
    assert roles["trader"]["effective_llm"]["model"] == "qwen2.5"
    assert roles["trader"]["effective_llm"]["base_url"] == "http://localhost:11434"
    assert roles["trader"]["effective_llm"]["uses_default"] is False


def test_tradingagents_config_normalization_keeps_role_contract():
    config = config_center._normalize_tradingagents_config(
        {
            "default_mode": "quantagent_patched_graph",
            "llm_provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.test/v1",
            "max_runtime_seconds": 9999,
            "background_run": False,
            "save_full_output": False,
            "write_audit": True,
            "unknown_top_level": "ignored",
            "role_configs": {
                "news_analyst": {
                    "enabled": False,
                    "prompt_version": "news_analyst.local.v2",
                    "prompt": "Extract symbols from locally stored financial news.",
                    "skill": "local_news_symbol_extraction",
                    "unknown_field": "ignored",
                }
            },
        },
        {"provider": "openai", "model": "gpt-4o"},
    )

    assert config["default_mode"] == "quantagent_patched_graph"
    assert config["llm_provider"] == "deepseek"
    assert config["model"] == "deepseek-chat"
    assert config["base_url"] == "https://api.deepseek.test/v1"
    assert config["max_runtime_seconds"] == 3600
    assert config["background_run"] is False
    assert config["save_full_output"] is False
    assert config["write_audit"] is True
    assert config["output_language"] == "zh-CN"
    assert config["effective_llm"]["provider"] == "deepseek"
    assert config["effective_llm"]["uses_default"] is False
    assert "unknown_top_level" not in config
    assert "market_analyst" in config["role_configs"]
    assert config["role_configs"]["news_analyst"]["enabled"] is False
    assert config["role_configs"]["news_analyst"]["prompt_version"] == "news_analyst.local.v2"
    assert config["role_configs"]["news_analyst"]["prompt"] == "Extract symbols from locally stored financial news."
    assert "unknown_field" not in config["role_configs"]["news_analyst"]
    assert config["role_configs"]["news_analyst"]["effective_llm"]["uses_default"] is True
