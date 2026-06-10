import pytest

from app.api.v1.endpoints import data_governance


@pytest.mark.asyncio
async def test_data_governance_overview_exposes_storage_and_ingest_contracts():
    payload = await data_governance.get_data_governance_overview()

    assert payload["meta"]["schema_version"] == "data_governance_response.v1"
    assert payload["data"]["contracts"]["storage_contract"] == "/api/v1/meta/storage-contract"
    assert payload["data"]["contracts"]["manual_ingest"] == "/api/v1/meta/ingest"
    assert "fundamental_report" in payload["data"]["storage_contract"]["tables"]
    assert payload["data"]["quality"]["manual_ingest_ready"] is True


@pytest.mark.asyncio
async def test_data_governance_preview_routes_fundamentals_through_pit_storage():
    payload = await data_governance.preview_governed_data(
        data_type="fundamentals",
        symbol="AAPL",
        interval="1h",
        limit=1,
        as_of_time=None,
    )

    assert payload["meta"]["source_endpoint"] == "/api/v1/fundamentals/{symbol}"
    assert payload["meta"]["pit_rule"] == "available_time <= as_of_time"
    assert payload["meta"]["agent_input_policy"] == "local_storage_only"
    assert payload["meta"]["storage_contract"] == "fundamental_report"
