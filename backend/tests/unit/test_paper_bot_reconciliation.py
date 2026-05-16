"""
Unit tests for Paper Bot 远端状态对账逻辑 (v1.2.3)。

测试场景：
1. active_bots 命中时 → running / can_fetch=true / matched_by=active_bots
2. docker 命中时    → running / can_fetch=true / matched_by=docker
3. bot_runs 命中时 → deployed / can_fetch=false / matched_by=bot_runs
4. 未命中时        → not_detected / can_fetch=false / matched_by=none
5. 列表和详情返回一致
"""

import asyncio
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


ACTIVE_BOT = {
    "instance_name": "paper_test_ma_001_fbef1fdb",
    "bot_name": "test_ma_001",
    "status": "running",
    "container_id": "abc123",
}

DOCKER_BOT = {
    "instance_name": "paper_signal_btc",
    "container_name": "hummingbot-signal-btc",
    "status": "running",
    "image": "hummingbot/hummingbot:latest",
}

BOT_RUN = {
    "instance_name": "paper_test_ma_001_fbef1fdb",
    "bot_name": "test_ma_001",
    "deployment_status": "DEPLOYED",
    "run_status": "running",
}

PAPER_BOT_RECORD = {
    "paper_bot_id": "paper_test_ma_001_fbef1fdb",
    "bot_name": "test_ma_001",
    "strategy_type": "ma",
    "trading_pair": "BTC-USDT",
    "mode": "paper",
    "local_status": "submitted",
    "remote_status": "not_detected",
    "matched_remote_bot": False,
    "matched_by": "none",
    "hummingbot_bot_id": None,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "started_at": datetime.now(timezone.utc).isoformat(),
    "config": {},
}

PAPER_BOT_RECORD_START_FAILED = {
    **PAPER_BOT_RECORD,
    "local_status": "start_failed",
    "last_error": "deploy-v2-controllers failed",
}


# ── 辅助：同步包装异步测试函数 ────────────────────────────────────────────────

def _sync_async(test_fn):
    """将 async 测试函数包装为同步函数，用于 pytest"""
    def wrapper():
        return asyncio.run(test_fn())
    wrapper.__name__ = test_fn.__name__
    return wrapper


# ── Test: reconcile_paper_bot — 4 个场景 ──────────────────────────────────

def test_reconcile_active_bots_match():
    """场景 1: active_bots 命中 → running + can_fetch=true"""

    async def run():
        from app.services.hummingbot_paper_bot_service import reconcile_paper_bot

        result = await reconcile_paper_bot(
            paper_bot_id="paper_test_ma_001_fbef1fdb",
            record=PAPER_BOT_RECORD,
            active_bots=[ACTIVE_BOT],
            docker_bots=[],
            bot_runs_deployed=[],
        )

        assert result.local_status == "running"
        assert result.remote_status == "running"
        assert result.matched_remote_bot is True
        assert result.matched_by == "active_bots"
        assert result.can_fetch_runtime_data is True
        assert result.hummingbot_bot_id == "paper_test_ma_001_fbef1fdb"
        assert result.message is None

    asyncio.run(run())


def test_reconcile_docker_match():
    """场景 2: docker 命中 → running + can_fetch=true"""

    async def run():
        from app.services.hummingbot_paper_bot_service import reconcile_paper_bot

        result = await reconcile_paper_bot(
            paper_bot_id="paper_signal_btc",
            record={"bot_name": "signal_btc", "local_status": "submitted"},
            active_bots=[],
            docker_bots=[DOCKER_BOT],
            bot_runs_deployed=[],
        )

        assert result.local_status == "running"
        assert result.remote_status == "running"
        assert result.matched_remote_bot is True
        assert result.matched_by == "docker"
        assert result.can_fetch_runtime_data is True

    asyncio.run(run())


def test_reconcile_bot_runs_deployed_match():
    """场景 3: bot_runs DEPLOYED 命中 → deployed + can_fetch=false（不覆盖 local_status）"""

    async def run():
        from app.services.hummingbot_paper_bot_service import reconcile_paper_bot

        result = await reconcile_paper_bot(
            paper_bot_id="paper_test_ma_001_fbef1fdb",
            record=PAPER_BOT_RECORD_START_FAILED,
            active_bots=[],
            docker_bots=[],
            bot_runs_deployed=[BOT_RUN],
        )

        assert result.local_status == "start_failed", "local_status 不应被 bot_runs 覆盖"
        assert result.remote_status == "deployed"
        assert result.matched_remote_bot is True
        assert result.matched_by == "bot_runs"
        assert result.can_fetch_runtime_data is False
        assert "active_bots" in result.message
        assert "容器未启动" in result.message

    asyncio.run(run())


def test_reconcile_bot_runs_deployed_match_submitted():
    """场景 3b: bot_runs 命中时，本地状态是 submitted，保持 submitted"""

    async def run():
        from app.services.hummingbot_paper_bot_service import reconcile_paper_bot

        result = await reconcile_paper_bot(
            paper_bot_id="paper_test_ma_001_fbef1fdb",
            record=PAPER_BOT_RECORD,
            active_bots=[],
            docker_bots=[],
            bot_runs_deployed=[BOT_RUN],
        )

        assert result.local_status == "submitted"
        assert result.remote_status == "deployed"
        assert result.can_fetch_runtime_data is False

    asyncio.run(run())


def test_reconcile_no_match():
    """场景 4: 未匹配 → not_detected + can_fetch=false"""

    async def run():
        from app.services.hummingbot_paper_bot_service import reconcile_paper_bot

        # 用一个 bot_name 完全不同的记录，确保不会误匹配
        no_match_record = {
            "paper_bot_id": "paper_unknown",
            "bot_name": "definitely_not_test_bot",
            "local_status": "submitted",
        }
        result = await reconcile_paper_bot(
            paper_bot_id="paper_unknown",
            record=no_match_record,
            active_bots=[ACTIVE_BOT],
            docker_bots=[DOCKER_BOT],
            bot_runs_deployed=[BOT_RUN],
        )

        assert result.local_status == "submitted"
        assert result.remote_status == "not_detected"
        assert result.matched_remote_bot is False
        assert result.matched_by == "none"
        assert result.can_fetch_runtime_data is False
        assert result.hummingbot_bot_id is None

    asyncio.run(run())


def test_reconcile_priority_active_over_docker():
    """优先级：active_bots 优先于 docker"""

    async def run():
        from app.services.hummingbot_paper_bot_service import reconcile_paper_bot

        result = await reconcile_paper_bot(
            paper_bot_id="paper_test_ma_001_fbef1fdb",
            record=PAPER_BOT_RECORD,
            active_bots=[ACTIVE_BOT],
            docker_bots=[DOCKER_BOT],
            bot_runs_deployed=[],
        )

        assert result.matched_by == "active_bots"
        assert result.can_fetch_runtime_data is True

    asyncio.run(run())


def test_reconcile_priority_docker_over_bot_runs():
    """优先级：docker 优先于 bot_runs"""

    async def run():
        from app.services.hummingbot_paper_bot_service import reconcile_paper_bot

        result = await reconcile_paper_bot(
            paper_bot_id="paper_signal_btc",
            record={"bot_name": "signal_btc", "local_status": "submitted"},
            active_bots=[],
            docker_bots=[DOCKER_BOT],
            bot_runs_deployed=[BOT_RUN],
        )

        assert result.matched_by == "docker"
        assert result.can_fetch_runtime_data is True

    asyncio.run(run())


# ── Test: 宽松匹配 key 逻辑 ────────────────────────────────────────────────

def test_build_match_keys_basic():
    """paper_bot_id 和 bot_name 都在 key 集合中"""
    from app.services.hummingbot_paper_bot_service import _build_match_keys

    keys = _build_match_keys("paper_test_ma_001_fbef1fdb", "test_ma_001", {})
    assert keys["paper_bot_id"] == "paper_test_ma_001_fbef1fdb"
    assert keys["bot_name"] == "test_ma_001"


def test_build_match_keys_strips_paper_prefix():
    """去掉 paper_ 前缀后仍能匹配"""
    from app.services.hummingbot_paper_bot_service import _build_match_keys

    keys = _build_match_keys("paper_test_ma_001_fbef1fdb", "test_ma_001", {})
    assert "paper_bot_id_stripped" in keys
    assert keys["paper_bot_id_stripped"] == "test_ma_001_fbef1fdb"


def test_build_match_keys_strips_random_suffix():
    """去掉 8 位 hex 后缀后仍能匹配"""
    from app.services.hummingbot_paper_bot_service import _build_match_keys

    keys = _build_match_keys("paper_test_ma_001_fbef1fdb", "test_ma_001", {})
    assert "paper_bot_id_no_suffix" in keys
    assert keys["paper_bot_id_no_suffix"] == "paper_test_ma_001"


def test_build_match_keys_from_record_config():
    """config_id / controller_config_id / hummingbot_bot_id 从 record.config 中提取"""
    from app.services.hummingbot_paper_bot_service import _build_match_keys

    record = {
        "config": {
            "config_id": "ctrl_abc123",
            "controller_config_id": "ctrl_xyz789",
            "hummingbot_bot_id": "hb_bot_001",
        }
    }
    keys = _build_match_keys("paper_test_001", "test", record)
    assert keys.get("config_id") == "ctrl_abc123"
    assert keys.get("controller_config_id") == "ctrl_xyz789"
    assert keys.get("hummingbot_bot_id") == "hb_bot_001"


def test_bot_matches_remote_exact():
    """完全相等匹配"""
    from app.services.hummingbot_paper_bot_service import _bot_matches_remote

    keys = {"paper_bot_id": "paper_test_ma_001_fbef1fdb", "bot_name": "test_ma_001"}
    remote_bot = {"instance_name": "paper_test_ma_001_fbef1fdb"}
    assert _bot_matches_remote(keys, remote_bot) is True


def test_bot_matches_remote_substring():
    """互为子串匹配"""
    from app.services.hummingbot_paper_bot_service import _bot_matches_remote

    keys = {"paper_bot_id": "paper_test_ma_001", "bot_name": "test_ma_001"}
    remote_bot = {"instance_name": "paper_test_ma_001_fbef1fdb"}
    assert _bot_matches_remote(keys, remote_bot) is True


def test_bot_matches_remote_stripped():
    """去掉前缀后匹配"""
    from app.services.hummingbot_paper_bot_service import _bot_matches_remote

    keys = {"paper_bot_id_stripped": "test_ma_001_fbef1fdb"}
    remote_bot = {"bot_name": "test_ma_001_fbef1fdb"}
    assert _bot_matches_remote(keys, remote_bot) is True


def test_bot_matches_remote_no_suffix():
    """去掉随机后缀后匹配"""
    from app.services.hummingbot_paper_bot_service import _bot_matches_remote

    keys = {"paper_bot_id_no_suffix": "paper_test_ma_001"}
    remote_bot = {"instance_name": "paper_test_ma_001"}
    assert _bot_matches_remote(keys, remote_bot) is True


def test_bot_matches_remote_config_id():
    """通过 config_id 匹配"""
    from app.services.hummingbot_paper_bot_service import _bot_matches_remote

    keys = {"config_id": "ctrl_abc123"}
    remote_bot = {"config_id": "ctrl_abc123", "instance_name": "other-bot"}
    assert _bot_matches_remote(keys, remote_bot) is True


def test_bot_matches_remote_no_match():
    """完全不匹配"""
    from app.services.hummingbot_paper_bot_service import _bot_matches_remote

    keys = {"paper_bot_id": "paper_unknown_bot", "bot_name": "unknown"}
    remote_bot = {"instance_name": "paper_test_ma_001_fbef1fdb"}
    assert _bot_matches_remote(keys, remote_bot) is False


# ── Test: 列表和详情一致性 ────────────────────────────────────────────────

def test_list_and_detail_return_consistent_status():
    """列表和详情对同一 paper_bot_id 返回完全一致的 remote_status / local_status / matched_by"""

    async def run():
        from app.services.hummingbot_paper_bot_service import (
            get_paper_bots_list,
            get_paper_bot_detail,
            _paper_bot_records,
        )

        _paper_bot_records.clear()
        _paper_bot_records["paper_test_ma_001_fbef1fdb"] = PAPER_BOT_RECORD.copy()

        async def mock_fetch_all():
            return [ACTIVE_BOT], [], []  # active_bots, docker_bots, bot_runs_deployed

        with patch("app.services.hummingbot_paper_bot_service._fetch_all_remote_sources", new=mock_fetch_all):
            list_resp = await get_paper_bots_list()
            detail_resp = await get_paper_bot_detail("paper_test_ma_001_fbef1fdb")

        bot_data = next(b for b in list_resp["data"]["bots"]
                        if b["paper_bot_id"] == "paper_test_ma_001_fbef1fdb")
        detail_data = detail_resp["data"]

        assert bot_data["remote_status"] == detail_data["remote_status"]
        assert bot_data["local_status"] == detail_data["local_status"]
        assert bot_data["matched_by"] == detail_data["matched_by"]
        assert bot_data["matched_remote_bot"] == detail_data["matched_remote_bot"]
        assert bot_data["can_fetch_runtime_data"] == detail_data["can_fetch_runtime_data"]

    asyncio.run(run())


def test_list_and_detail_consistent_not_detected():
    """未匹配时，列表和详情都返回 not_detected"""

    async def run():
        from app.services.hummingbot_paper_bot_service import (
            get_paper_bots_list,
            get_paper_bot_detail,
            _paper_bot_records,
        )

        _paper_bot_records.clear()
        _paper_bot_records["paper_unknown_bot"] = {
            **PAPER_BOT_RECORD,
            "paper_bot_id": "paper_unknown_bot",
            "bot_name": "unknown",
        }

        async def mock_fetch_all():
            return [], [], []  # 没有任何远端记录

        with patch("app.services.hummingbot_paper_bot_service._fetch_all_remote_sources", new=mock_fetch_all):
            list_resp = await get_paper_bots_list()
            detail_resp = await get_paper_bot_detail("paper_unknown_bot")

        bot_data = next(b for b in list_resp["data"]["bots"]
                        if b["paper_bot_id"] == "paper_unknown_bot")
        detail_data = detail_resp["data"]

        assert bot_data["remote_status"] == "not_detected"
        assert detail_data["remote_status"] == "not_detected"
        assert bot_data["matched_by"] == "none"
        assert detail_data["matched_by"] == "none"
        assert bot_data["can_fetch_runtime_data"] is False
        assert detail_data["can_fetch_runtime_data"] is False

    asyncio.run(run())


def test_list_and_detail_consistent_deployed():
    """bot_runs 命中时，列表和详情都返回 deployed"""

    async def run():
        from app.services.hummingbot_paper_bot_service import (
            get_paper_bots_list,
            get_paper_bot_detail,
            _paper_bot_records,
        )

        _paper_bot_records.clear()
        _paper_bot_records["paper_test_ma_001_fbef1fdb"] = PAPER_BOT_RECORD_START_FAILED.copy()

        async def mock_fetch_all():
            return [], [], [BOT_RUN]  # 只有 bot_runs

        with patch("app.services.hummingbot_paper_bot_service._fetch_all_remote_sources", new=mock_fetch_all):
            list_resp = await get_paper_bots_list()
            detail_resp = await get_paper_bot_detail("paper_test_ma_001_fbef1fdb")

        bot_data = next(b for b in list_resp["data"]["bots"]
                        if b["paper_bot_id"] == "paper_test_ma_001_fbef1fdb")
        detail_data = detail_resp["data"]

        assert bot_data["remote_status"] == "deployed"
        assert detail_data["remote_status"] == "deployed"
        assert bot_data["matched_by"] == "bot_runs"
        assert detail_data["matched_by"] == "bot_runs"
        assert bot_data["can_fetch_runtime_data"] is False
        assert detail_data["can_fetch_runtime_data"] is False
        # local_status 不应被覆盖为 running
        assert bot_data["local_status"] == "start_failed"
        assert detail_data["local_status"] == "start_failed"

    asyncio.run(run())


# ── Test: can_fetch_runtime_data 字段存在于响应中 ─────────────────────────

def test_list_response_includes_can_fetch_runtime_data():
    """列表接口响应中包含 can_fetch_runtime_data 字段"""

    async def run():
        from app.services.hummingbot_paper_bot_service import (
            get_paper_bots_list,
            _paper_bot_records,
        )

        _paper_bot_records.clear()
        _paper_bot_records["paper_test_ma_001_fbef1fdb"] = PAPER_BOT_RECORD.copy()

        async def mock_fetch_all():
            return [ACTIVE_BOT], [], []

        with patch("app.services.hummingbot_paper_bot_service._fetch_all_remote_sources", new=mock_fetch_all):
            resp = await get_paper_bots_list()

        bot = resp["data"]["bots"][0]
        assert "can_fetch_runtime_data" in bot
        assert "reconciliation_message" in bot

    asyncio.run(run())


def test_detail_response_includes_can_fetch_runtime_data():
    """详情接口响应中包含 can_fetch_runtime_data 字段"""

    async def run():
        from app.services.hummingbot_paper_bot_service import (
            get_paper_bot_detail,
            _paper_bot_records,
        )

        _paper_bot_records.clear()
        _paper_bot_records["paper_test_ma_001_fbef1fdb"] = PAPER_BOT_RECORD.copy()

        async def mock_fetch_all():
            return [], [DOCKER_BOT], []

        with patch("app.services.hummingbot_paper_bot_service._fetch_all_remote_sources", new=mock_fetch_all):
            resp = await get_paper_bot_detail("paper_test_ma_001_fbef1fdb")

        data = resp["data"]
        assert "can_fetch_runtime_data" in data
        assert "reconciliation_message" in data

    asyncio.run(run())


# ── Test: 停止接口 guard 检查 ───────────────────────────────────────────────

def test_stop_blocked_when_can_fetch_false():
    """can_fetch_runtime_data=false 时，停止接口应拒绝"""

    async def run():
        from app.services.hummingbot_paper_bot_service import stop_paper_bot

        result = await stop_paper_bot(
            paper_bot_id="paper_test_ma_001_fbef1fdb",
            raw_request_data={"confirm": True},
        )

        assert result["stopped"] is False
        assert result["error"] is not None

    asyncio.run(run())


# ── Test: _fetch_all_remote_sources 并行请求 ──────────────────────────────

def test_fetch_all_remote_sources_returns_three_lists():
    """_fetch_all_remote_sources 返回 (active_bots, docker_bots, bot_runs_deployed)"""

    async def run():
        from app.services.hummingbot_paper_bot_service import _fetch_all_remote_sources

        with patch("app.services.hummingbot_paper_bot_service._call_hummingbot_api") as mock_api:
            mock_api.return_value = {"data": []}

            active, docker, runs = await _fetch_all_remote_sources()

            assert isinstance(active, list)
            assert isinstance(docker, list)
            assert isinstance(runs, list)
            # 三个 API 都应该被调用
            assert mock_api.call_count >= 3

    asyncio.run(run())


# ── Test: active_bots 命中时 reconcile 覆盖本地 start_failed ─────────────

def test_active_bots_override_local_status_to_running():
    """active_bots 命中时，local_status 应被覆盖为 running"""

    async def run():
        from app.services.hummingbot_paper_bot_service import reconcile_paper_bot

        result = await reconcile_paper_bot(
            paper_bot_id="paper_test_ma_001_fbef1fdb",
            record=PAPER_BOT_RECORD_START_FAILED,  # local_status=start_failed
            active_bots=[ACTIVE_BOT],
            docker_bots=[],
            bot_runs_deployed=[],
        )

        assert result.local_status == "running", "active_bots 命中时应将 local_status 覆盖为 running"

    asyncio.run(run())
