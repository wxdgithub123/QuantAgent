"""Add factor definition catalog.

Revision ID: 011
Revises: 010
Create Date: 2026-05-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FACTOR_DEFINITIONS = [
    # OHLCV base fields
    ("open", "开盘价", "行情基础", "ohlcv", "该根K线开始时的成交价格。", "直接取K线 open 字段。", "K线 OHLCV", "从平台行情库读取；具体原始来源见快照 provider/data_source。", "price", "1h", 10),
    ("high", "最高价", "行情基础", "ohlcv", "该根K线周期内出现的最高成交价格。", "直接取K线 high 字段。", "K线 OHLCV", "从平台行情库读取；具体原始来源见快照 provider/data_source。", "price", "1h", 20),
    ("low", "最低价", "行情基础", "ohlcv", "该根K线周期内出现的最低成交价格。", "直接取K线 low 字段。", "K线 OHLCV", "从平台行情库读取；具体原始来源见快照 provider/data_source。", "price", "1h", 30),
    ("close", "收盘价", "行情基础", "ohlcv", "该根K线结束时的成交价格。", "直接取K线 close 字段。", "K线 OHLCV", "从平台行情库读取；具体原始来源见快照 provider/data_source。", "price", "1h", 40),
    ("volume", "成交量", "行情基础", "ohlcv", "该根K线周期内的成交数量。", "直接取K线 volume 字段。", "K线 OHLCV", "从平台行情库读取；具体原始来源见快照 provider/data_source。", "base_volume", "1h", 50),
    # Technical indicators
    ("sma_5", "5周期简单均线", "技术指标", "sma", "短周期价格平均线，用于观察很近的价格方向。", "最近5根K线收盘价的简单平均。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price", "1h", 105),
    ("sma_10", "10周期简单均线", "技术指标", "sma", "短中周期价格平均线。", "最近10根K线收盘价的简单平均。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price", "1h", 110),
    ("sma_20", "20周期简单均线", "技术指标", "sma", "常用中周期趋势参考线。", "最近20根K线收盘价的简单平均。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price", "1h", 120),
    ("sma_60", "60周期简单均线", "技术指标", "sma", "较长周期趋势参考线。", "最近60根K线收盘价的简单平均。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price", "1h", 160),
    ("ema_12", "12周期指数均线", "技术指标", "ema", "对近期价格更敏感的均线。", "最近12根K线收盘价的指数加权平均。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price", "1h", 212),
    ("ema_26", "26周期指数均线", "技术指标", "ema", "MACD常用慢速指数均线。", "最近26根K线收盘价的指数加权平均。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price", "1h", 226),
    ("boll_mid", "布林带中轨", "技术指标", "bollinger", "布林带的中心线。", "20周期收盘价简单均线。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price", "1h", 320),
    ("boll_upper", "布林带上轨", "技术指标", "bollinger", "价格波动区间的上边界参考。", "20周期均线 + 2倍标准差。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price", "1h", 321),
    ("boll_lower", "布林带下轨", "技术指标", "bollinger", "价格波动区间的下边界参考。", "20周期均线 - 2倍标准差。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price", "1h", 322),
    ("boll_pct_b", "布林带位置百分比", "技术指标", "bollinger", "衡量当前价格处在布林带上下轨之间的相对位置。", "(close - 下轨) / (上轨 - 下轨)。", "K线 close", "由系统内部指标模块根据入库K线计算。", "ratio", "1h", 323),
    ("boll_width", "布林带宽度", "技术指标", "bollinger", "衡量当前波动率区间是否扩张。", "(上轨 - 下轨) / 中轨。", "K线 close", "由系统内部指标模块根据入库K线计算。", "ratio", "1h", 324),
    ("rsi_14", "14周期RSI", "技术指标", "rsi", "观察价格上涨/下跌动能强弱的震荡指标。", "14周期平均上涨幅度与平均下跌幅度计算得到。", "K线 close", "由系统内部指标模块根据入库K线计算。", "score", "1h", 414),
    ("macd_dif", "MACD DIF", "技术指标", "macd", "MACD快慢线差值，反映趋势动量。", "EMA12 - EMA26。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price_diff", "1h", 510),
    ("macd_dea", "MACD DEA", "技术指标", "macd", "DIF的平滑信号线。", "DIF的9周期指数平均。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price_diff", "1h", 520),
    ("macd_hist", "MACD柱状图", "技术指标", "macd", "DIF与DEA之间的距离，用于观察动量变化。", "DIF - DEA。", "K线 close", "由系统内部指标模块根据入库K线计算。", "price_diff", "1h", 530),
    ("atr_14", "14周期ATR", "技术指标", "atr", "衡量近期真实波动幅度。", "14周期真实波幅的平均值。", "K线 high/low/close", "由系统内部指标模块根据入库K线计算。", "price", "1h", 614),
    # News context
    ("news_sentiment_mean", "新闻情绪均值", "新闻因子", "sentiment", "最近新闻的平均情绪倾向。", "对近期新闻 sentiment_score 求平均。", "新闻/RSS/OpenBB新闻", "从新闻库读取；通常由 OpenBB 新闻或 RSS 写入。", "score", "1h", 701),
    ("news_event_earnings", "新闻事件：财报", "新闻因子", "event_tag", "近期新闻中被标记为财报相关的数量。", "统计近期新闻 event_tags 包含 earnings 的文章数。", "新闻/RSS/OpenBB新闻", "从新闻库读取；当前主要作为上下文辅助。", "count", "1h", 711),
    ("news_event_etf", "新闻事件：ETF", "新闻因子", "event_tag", "近期新闻中被标记为 ETF 相关的数量。", "统计近期新闻 event_tags 包含 etf 的文章数。", "新闻/RSS/OpenBB新闻", "从新闻库读取；当前主要作为上下文辅助。", "count", "1h", 712),
    ("news_event_macro_policy", "新闻事件：宏观政策", "新闻因子", "event_tag", "近期新闻中被标记为宏观政策相关的数量。", "统计近期新闻 event_tags 包含 macro_policy 的文章数。", "新闻/RSS/OpenBB新闻", "从新闻库读取；当前主要作为上下文辅助。", "count", "1h", 713),
    ("news_event_regulation", "新闻事件：监管", "新闻因子", "event_tag", "近期新闻中被标记为监管相关的数量。", "统计近期新闻 event_tags 包含 regulation 的文章数。", "新闻/RSS/OpenBB新闻", "从新闻库读取；当前主要作为上下文辅助。", "count", "1h", 714),
    ("news_event_volatility", "新闻事件：波动", "新闻因子", "event_tag", "近期新闻中被标记为波动相关的数量。", "统计近期新闻 event_tags 包含 volatility 的文章数。", "新闻/RSS/OpenBB新闻", "从新闻库读取；当前主要作为上下文辅助。", "count", "1h", 715),
    # Macro context
    ("macro_cpi", "CPI通胀指标", "宏观因子", "macro", "通胀环境参考，用于辅助判断风险偏好。", "读取最近可用宏观快照并映射为因子。", "宏观数据", "通过 OpenBB 接入 OECD/FRED 等宏观 provider。", "rate", "1h", 801),
    ("macro_fed_funds_rate", "联邦基金利率", "宏观因子", "macro", "美国基准利率环境参考。", "读取最近可用宏观快照并映射为因子。", "宏观数据", "通过 OpenBB/FRED 获取。", "percent", "1h", 802),
    ("macro_inflation_expect", "通胀预期", "宏观因子", "macro", "市场通胀预期参考。", "读取最近可用宏观快照并映射为因子。", "宏观数据", "通过 OpenBB/FRED 获取。", "percent", "1h", 803),
    ("macro_m2_money_supply", "M2货币供应", "宏观因子", "macro", "流动性背景参考。", "读取最近可用宏观快照并映射为因子。", "宏观数据", "通过 OpenBB/FRED 获取。", "level", "1h", 804),
    ("macro_treasury_10y", "10年期美债收益率", "宏观因子", "macro", "长端利率环境参考。", "读取最近可用宏观快照并映射为因子。", "宏观数据", "通过 OpenBB/FRED 获取。", "percent", "1h", 805),
    ("macro_unemployment", "失业率", "宏观因子", "macro", "就业环境参考，用于辅助判断宏观压力。", "读取最近可用宏观快照并映射为因子。", "宏观数据", "通过 OpenBB/OECD 获取。", "rate", "1h", 806),
]


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("factor_definitions"):
        op.create_table(
            "factor_definitions",
            sa.Column("factor_name", sa.String(100), nullable=False),
            sa.Column("display_name", sa.String(120), nullable=False),
            sa.Column("category", sa.String(40), nullable=False),
            sa.Column("family", sa.String(60), nullable=True),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("calculation", sa.Text(), nullable=False, server_default=""),
            sa.Column("upstream_data", sa.String(160), nullable=False, server_default=""),
            sa.Column("provider_hint", sa.String(160), nullable=False, server_default=""),
            sa.Column("unit", sa.String(40), nullable=False, server_default=""),
            sa.Column("default_interval", sa.String(20), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="1000"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("factor_name"),
        )
        op.create_index("idx_factor_def_category", "factor_definitions", ["category"])
        op.create_index("idx_factor_def_active", "factor_definitions", ["is_active"])

    bind = op.get_bind()
    sql = text(
        """
        INSERT INTO factor_definitions (
            factor_name, display_name, category, family, description, calculation,
            upstream_data, provider_hint, unit, default_interval, sort_order, is_active
        )
        VALUES (
            :factor_name, :display_name, :category, :family, :description, :calculation,
            :upstream_data, :provider_hint, :unit, :default_interval, :sort_order, true
        )
        ON CONFLICT (factor_name) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            category = EXCLUDED.category,
            family = EXCLUDED.family,
            description = EXCLUDED.description,
            calculation = EXCLUDED.calculation,
            upstream_data = EXCLUDED.upstream_data,
            provider_hint = EXCLUDED.provider_hint,
            unit = EXCLUDED.unit,
            default_interval = EXCLUDED.default_interval,
            sort_order = EXCLUDED.sort_order,
            is_active = true,
            updated_at = now()
        """
    )
    for row in FACTOR_DEFINITIONS:
        bind.execute(
            sql,
            {
                "factor_name": row[0],
                "display_name": row[1],
                "category": row[2],
                "family": row[3],
                "description": row[4],
                "calculation": row[5],
                "upstream_data": row[6],
                "provider_hint": row[7],
                "unit": row[8],
                "default_interval": row[9],
                "sort_order": row[10],
            },
        )


def downgrade() -> None:
    if _table_exists("factor_definitions"):
        op.drop_index("idx_factor_def_active", table_name="factor_definitions")
        op.drop_index("idx_factor_def_category", table_name="factor_definitions")
        op.drop_table("factor_definitions")
