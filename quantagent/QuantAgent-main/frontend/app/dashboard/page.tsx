"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import {
  RefreshCw, Brain, ArrowRight, Newspaper
} from "lucide-react";

// ─── TypeScript Interfaces ─────────────────────────────────────────────────
interface Ticker {
  symbol: string;
  price: number;
  change_24h: number;
  change_percent: number;
  volume: number;
  high_24h?: number;
  low_24h?: number;
}

interface Position {
  symbol: string;
  side?: "long" | "short" | "LONG" | "SHORT" | string;
  quantity: number;
  avg_price: number;
  avgEntryPrice?: number;
  mark_price: number;
  markPrice?: number;
  pnl: number;
  unrealizedPnl?: number;
  pnl_pct: number;
  unrealizedPnlPct?: number;
  source?: "manual" | "agent" | "backtest" | string;
  relatedDecisionId?: number | null;
  relatedOrderIntentId?: string | null;
  riskStatus?: string;
  updatedAt?: string | null;
  updated_at?: string | null;
}

interface PaperOrder {
  order_id: string;
  orderId?: string;
  source?: "manual" | "agent" | "backtest" | string;
  symbol: string;
  side: "BUY" | "SELL" | string;
  order_type: string;
  quantity: number;
  price: number;
  fillPrice?: number;
  fee: number;
  pnl: number | null;
  realizedPnl?: number | null;
  slippage?: number | null;
  status: string;
  created_at: string;
  createdAt?: string | null;
  filledAt?: string | null;
  relatedDecisionId?: number | null;
  relatedOrderIntentId?: string | null;
}

interface RiskRuleRow {
  ruleName?: string;
  rule_name?: string;
  currentValue?: string | number | null;
  current_value?: string | number | null;
  limitValue?: string | number | null;
  limit_value?: string | number | null;
  passed?: boolean;
  message?: string;
}

interface RiskStatus {
  kill_switch_active: boolean;
  drawdown_breached: boolean;
  total_drawdown_pct: number;
  drawdown_limit_pct: number;
  daily_loss_breached: boolean;
  daily_pnl: number;
  daily_loss_limit_pct: number;
  max_leverage: number;
  checked_rules?: RiskRuleRow[];
  metadata?: DataPanelMeta;
}

interface DataPanelMeta {
  data_source?: string;
  price_source?: string;
  last_updated?: string | null;
  is_cached?: boolean;
  fallback_source?: string | null;
  degraded?: boolean;
  message?: string;
}

interface ComparisonData {
  gateway_price: number | null;
  exchange_price: number | null;
  exchange_label: string;
  exchange_source: string;
  price_diff: number | null;
  price_diff_percent: number | null;
  status: "ok" | "unavailable";
  error?: string;
}

function buildComparisonData(
  gatewayPrice: number | null,
  exchangePrice: number | null,
  exchangeLabel: string,
  exchangeError?: string
): ComparisonData {
  const hasBothPrices = hasFiniteNumber(gatewayPrice) && hasFiniteNumber(exchangePrice);
  const diff = hasBothPrices ? Math.abs(toFiniteNumber(gatewayPrice) - toFiniteNumber(exchangePrice)) : null;
  const avg = hasBothPrices ? (toFiniteNumber(gatewayPrice) + toFiniteNumber(exchangePrice)) / 2 : 0;
  const diffPct = diff !== null && avg > 0 ? (diff / avg) * 100 : null;

  return {
    gateway_price: gatewayPrice,
    exchange_price: exchangePrice,
    exchange_label: exchangeLabel,
    exchange_source: `CCXT/${exchangeLabel}`,
    price_diff: diff,
    price_diff_percent: diffPct,
    status: exchangePrice !== null ? "ok" : "unavailable",
    error: exchangePrice === null ? exchangeError : undefined,
  };
}

interface TrendingCoinItem {
  id: string;
  symbol: string;
  name: string;
  thumb: string;
  market_cap_rank: number;
  price_btc?: number;
}

interface TrendingCoin {
  item: TrendingCoinItem;
}

interface ResearchSnapshotCounts {
  // Tier 1: 当前前端展示量
  bars_displayed?: number;
  factors_displayed?: number;
  signals_displayed?: number;
  news_displayed?: number;
  macro_displayed?: number;
  decisions_displayed?: number;
  tradingagents_roles_displayed?: number;
  // Tier 2: 回看窗口可用量
  bars_available?: number;
  factors_available?: number;
  signals_available?: number;
  news_available?: number;
  macro_available?: number;
  decisions_available?: number;
  tradingagents_roles_available?: number;
  // Tier 3: 数据库累计总量
  bars_total?: number;
  factors_total?: number;
  signals_total?: number;
  news_total?: number;
  macro_total?: number;
  decisions_total?: number;
  tradingagents_roles_total?: number;
  // 分类明细
  technical_factors?: number;
  sentiment_factors?: number;
  macro_factors?: number;
  // Deprecated（向后兼容）
  bars?: number;
  factors?: number;
  signals?: number;
  news?: number;
  macro?: number;
  decisions?: number;
  tradingagents_roles?: number;
}

interface ResearchSnapshotBar {
  event_time?: string;
  available_time?: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  vwap?: number | null;
  vwap_method?: string;
  provider?: string;
  data_source?: string;
}

interface ResearchSnapshotFactor {
  name: string;
  value: number | string | null;
  as_of_time?: string;
  alignment_rule?: string;
}

interface FactorDefinition {
  factor_name?: string;
  display_name?: string;
}

interface ResearchSnapshotSignal {
  id?: number;
  signalId?: number;
  symbol?: string;
  event_time?: string;
  available_time?: string;
  asOfTime?: string;
  timestamp?: string;
  signal_type?: string;
  action?: string;
  signal_value?: number;
  strength?: number;
  triggerStrength?: number;
  direction_strength?: number;
  direction_strength_label?: string;
  is_triggered?: boolean;
  confidence?: number;
  trigger_condition?: string;
  triggerReason?: string;
  source_strategy?: string;
  strategyType?: string;
  strategyName?: string;
  strategy_id?: string;
  provider?: string;
  data_source?: string;
  relatedBacktestId?: number | null;
  relatedDecisionId?: number | null;
  relatedOrderIntentId?: string | null;
  relatedAuditIds?: Array<number | string>;
  replaySessionId?: string | null;
  mergedCount?: number;
  mergedSignalIds?: Array<number | string>;
  mergeNote?: string;
  sourceEvents?: Array<Record<string, unknown>>;
  similarSignalCount?: number;
  similarBacktestIds?: Array<number | string>;
}

interface ResearchSnapshotFactorPanel {
  groups?: {
    technical?: ResearchSnapshotFactor[];
    sentiment?: ResearchSnapshotFactor[];
    macro?: ResearchSnapshotFactor[];
  };
  macro_event_tags?: Array<{
    label?: string;
    value?: number | string | null;
    event_time?: string;
    provider?: string;
  }>;
  alignment_rule?: string;
}

interface ResearchSnapshotBarPanel {
  rows?: ResearchSnapshotBar[];
  displayed?: number;
  latest?: ResearchSnapshotBar | null;
  summary?: {
    open?: number;
    high?: number;
    low?: number;
    close?: number;
    volume?: number;
    vwap?: number | null;
    window_vwap?: number | null;
    vwap_method?: string;
    source?: string;
  };
  note?: string;
}

interface ResearchSnapshotRole {
  role?: string;
  index?: number;
  label?: string;
  phase?: string;
  opinion?: string;
  confidence?: number | null;
  available?: boolean;
  summary?: string;
  reasoning?: string;
  key_points?: string[];
  data_source_chain?: string;
}

interface ResearchSnapshotTradingAgentsPanel {
  engine?: string;
  source?: string;
  decision_id?: number;
  decision_time?: string;
  final_signal?: string;
  confidence?: number;
  risk_veto?: boolean;
  summary?: string;
  role_count?: number;
  sections?: Array<{
    key: string;
    title: string;
    items: ResearchSnapshotRole[];
  }>;
  audit_url?: string | null;
}

interface ResearchSnapshotNewsItem {
  title?: string;
  source?: string;
  url?: string;
  summary?: string;
  published_at?: string;
  available_time?: string;
  sentiment_score?: number | null;
  asset_mappings?: string[];
  topics?: string[];
  event_tags?: string[];
  provider?: string;
}

interface ResearchSnapshotDecision {
  id: number;
  timestamp?: string;
  final_signal?: string;
  confidence?: number;
  risk_veto?: boolean;
  summary?: string;
  role_count?: number;
}

interface ResearchSnapshot {
  symbol: string;
  interval: string;
  as_of_time?: string;
  mode: "latest" | "point_in_time" | string;
  counts: ResearchSnapshotCounts;
  latest_bar?: ResearchSnapshotBar | null;
  bar_panel?: ResearchSnapshotBarPanel;
  factors: ResearchSnapshotFactor[];
  factor_panel?: ResearchSnapshotFactorPanel;
  signals: ResearchSnapshotSignal[];
  signal_panel?: ResearchSnapshotSignal[];
  news_events: Array<{ title?: string; source?: string; published_at?: string; provider?: string }>;
  news_panel?: ResearchSnapshotNewsItem[];
  macro_events: Array<{ indicator?: string; value?: number | string | null; date?: string; provider?: string }>;
  latest_decision?: ResearchSnapshotDecision | null;
  tradingagents_panel?: ResearchSnapshotTradingAgentsPanel | null;
  global_time_axis?: {
    as_of_time?: string;
    mode?: string;
    alignment_rule?: string;
    replay_note?: string;
  };
  lineage?: {
    rule?: string;
    context_source?: string;
    market_data?: string;
    storage_note?: string;
  };
}

const COOLDOWN_SECONDS = 30;

// 动态获取 WebSocket URL，优先适配当前环境
const getWsUrl = () => {
  if (typeof window === "undefined") return "";
  
  // 统一使用相对路径并通过 Next.js 的 rewrites 转发，避免硬编码的绝对域名路径
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/market`;
};

const toFiniteNumber = (value: unknown, fallback = 0) => {
  const numberValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
};

const hasFiniteNumber = (value: unknown): value is number =>
  value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));

const formatCompactNumber = (v: unknown) => {
  const n = toFiniteNumber(v);
  if (!n) return "—";
  if (n >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(2) + "K";
  return n.toFixed(0);
};

const formatCurrency = (v: unknown) => {
  const n = toFiniteNumber(v);
  if (!n) return "—";
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const normalizeResearchAsOfInput = (value: string) => {
  const raw = value.trim();
  if (!raw) return "";
  const candidate = raw.includes("T") ? raw : raw.replace(" ", "T");
  const date = new Date(candidate);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
};

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const FRIENDLY_DATA_UNAVAILABLE = "数据暂不可用，已展示缓存数据 / 暂无数据。";
const FRIENDLY_EXCHANGE_QUOTE_UNAVAILABLE = "交易所直接报价暂不可用，已保留平台统一报价。";

const sanitizeFetchError = (error: unknown, fallback = FRIENDLY_DATA_UNAVAILABLE) => {
  const raw = error instanceof Error ? error.message : String(error || "");
  if (!raw) return fallback;
  const lower = raw.toLowerCase();
  if (
    lower.includes("failed to fetch") ||
    lower.includes("network") ||
    lower.includes("timeout") ||
    lower.includes("abort") ||
    lower.includes("econnrefused") ||
    lower.includes("http 5")
  ) {
    return fallback;
  }
  return raw.length > 120 ? fallback : raw;
};

const sanitizeExchangeQuoteError = (error?: string | null) => {
  if (!error) return "等待交易所直接报价";
  const lower = error.toLowerCase();
  if (
    lower.includes("timeout") ||
    lower.includes("超时") ||
    lower.includes("clash") ||
    lower.includes("failed") ||
    lower.includes("fetch") ||
    lower.includes("http") ||
    lower.includes("451") ||
    lower.includes("restricted") ||
    lower.includes("econnrefused")
  ) {
    return FRIENDLY_EXCHANGE_QUOTE_UNAVAILABLE;
  }
  return error.length > 80 ? FRIENDLY_EXCHANGE_QUOTE_UNAVAILABLE : error;
};

async function fetchJsonWithTimeout<T>(url: string, options: RequestInit = {}, timeoutMs = 12000): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: options.signal ?? controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof data?.detail === "string" ? data.detail : `HTTP ${response.status}`;
      throw new Error(detail);
    }
    return data as T;
  } finally {
    clearTimeout(timeout);
  }
}

const formatResearchAsOfInput = (value?: string | null) => {
  if (!value) return "";
  const normalized = normalizeResearchAsOfInput(value);
  if (!normalized) return value.trim();
  const date = new Date(normalized);
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const normalizeSymbolParam = (value?: string | null) => (value || "BTCUSDT").replace("/", "").trim().toUpperCase() || "BTCUSDT";

type AnalysisCache = Record<string, { result: string; timestamp: number; outputContent?: string; thinkingContent?: string }>;
type CooldownTracker = Record<string, number>;

// 每个 Agent 对应的回测策略配置
const AGENT_STRATEGY_MAP: Record<string, { strategy_type: string; params: Record<string, number>; interval: string; limit: number }> = {
  trend:          { strategy_type: "ma",   params: { short_period: 10, long_period: 30 }, interval: "1d", limit: 200 },
  mean_reversion: { strategy_type: "boll", params: { period: 20, std_dev: 2.0 },          interval: "1d", limit: 200 },
  risk:           { strategy_type: "rsi",  params: { period: 14, oversold: 30, overbought: 70 }, interval: "1d", limit: 200 },
};

const FALLBACK_FACTOR_LABELS: Record<string, string> = {
  open: "开盘价",
  high: "最高价",
  low: "最低价",
  close: "收盘价",
  volume: "成交量",
  boll_mid: "布林带中轨",
  boll_upper: "布林带上轨",
  boll_lower: "布林带下轨",
  boll_pct_b: "布林带位置百分比",
  boll_width: "布林带宽度",
  macd_dif: "MACD 快线 DIF",
  macd_dea: "MACD 信号线 DEA",
  macd_hist: "MACD 柱状图",
  news_sentiment: "新闻情绪",
  news_sentiment_mean: "新闻情绪均值",
  macro_cpi: "CPI 消费者物价指数",
  macro_core_cpi: "核心 CPI",
  macro_fed_funds_rate: "联邦基金利率",
  macro_inflation_expect: "通胀预期",
  macro_m2_money_supply: "M2 货币供应",
  macro_treasury_10y: "10年期美债收益率",
  macro_unemployment: "失业率",
  macro_gdp: "GDP 国内生产总值",
  macro_retail_sales: "零售销售",
  macro_industrial_production: "工业生产",
  macro_consumer_sentiment: "消费者信心",
};

const FALLBACK_STRATEGY_LABELS: Record<string, string> = {
  ma: "均线金叉策略",
  ma_cross: "均线金叉策略",
  rsi: "RSI 超买超卖策略",
  boll: "布林带均值回归策略",
  macd: "MACD 金叉死叉策略",
  ema_triple: "三线 EMA 趋势系统",
  atr_trend: "ATR 趋势追踪策略",
  turtle: "海龟交易法则",
  ichimoku: "一目均衡表趋势策略",
  news_sentiment: "新闻情绪策略",
  trend: "趋势跟踪策略",
  mean_reversion: "均值回归策略",
  risk: "风险管理策略",
};

const STRATEGY_SOURCE_LABELS: Record<string, string> = {
  backtest: "回测",
  replay: "历史回放",
  agent: "Agent",
  manual: "手动",
  paper: "模拟盘",
  strategy: "策略",
};

const ROLE_HELP_TEXT: Record<string, string> = {
  technical: "看 K 线、成交量、VWAP 和技术因子，判断价格结构。",
  news: "看新闻、情绪和资产映射，判断外部事件影响。",
  macro: "看 CPI、利率、通胀预期等宏观标签，判断市场背景。",
  risk: "看波动、回撤、仓位和风控约束，判断是否应该谨慎。",
  portfolio: "把前面角色意见汇总成仓位和组合建议。",
  final: "汇总多角色意见，形成最终买入、卖出或观望建议。",
};

function formatFactorDisplayName(name?: string, definitionMap?: Record<string, string>) {
  const raw = (name || "").trim();
  if (!raw) return "未知因子";
  const normalized = raw.toLowerCase();
  if (definitionMap?.[raw]) return definitionMap[raw];
  if (definitionMap?.[normalized]) return definitionMap[normalized];
  if (FALLBACK_FACTOR_LABELS[normalized]) return FALLBACK_FACTOR_LABELS[normalized];

  const periodMatch = normalized.match(/^(sma|ema|rsi|atr)_(\d+)$/);
  if (periodMatch) {
    const [, family, period] = periodMatch;
    const familyLabel: Record<string, string> = {
      sma: "简单均线",
      ema: "指数均线",
      rsi: "RSI 相对强弱",
      atr: "ATR 真实波幅",
    };
    return `${period}周期${familyLabel[family]}`;
  }

  return raw;
}

function formatStrategyDisplayName(strategy?: string) {
  const raw = (strategy || "").trim();
  if (!raw) return "未知策略";
  const sourceMatch = raw.match(/^(backtest|replay|agent|manual|paper|strategy)[:/_-](.+)$/i);
  if (sourceMatch) {
    const sourceLabel = STRATEGY_SOURCE_LABELS[sourceMatch[1].toLowerCase()] || sourceMatch[1];
    const strategyKey = sourceMatch[2].toLowerCase().replace(/^strategy[:/_-]?/, "");
    return `${sourceLabel} · ${FALLBACK_STRATEGY_LABELS[strategyKey] || sourceMatch[2]}`;
  }
  const normalized = raw.toLowerCase().replace(/^strategy[:/_-]?/, "");
  return FALLBACK_STRATEGY_LABELS[normalized] || raw;
}

function formatDataSourceChain(chain?: string | null) {
  const raw = chain || "AnalysisContext / OpenBB / CCXT / ClickHouse / 策略信号管道";
  return raw
    .replace(/AnalysisContext/g, "决策上下文（给 Agent 的标准材料）")
    .replace(/OpenBB\/yfinance/g, "OpenBB/yfinance（行情/新闻接口）")
    .replace(/CCXT\/OKX/g, "CCXT/OKX（交易所行情备源）")
    .replace(/ClickHouse/g, "ClickHouse 缓存（本地历史数据）")
    .replace(/DuckDB/g, "DuckDB 研究库")
    .replace(/FRED\/OECD/g, "FRED/OECD（宏观数据）")
    .replace(/L5 因子信号/g, "因子与信号数据")
    .replace(/L5/g, "因子与信号")
    .replace(/factor_snapshots/g, "因子快照表")
    .replace(/signal_events/g, "信号事件表")
    .replace(/策略信号管道/g, "策略信号管道");
}

function formatAlignmentRule(rule?: string | null) {
  const raw = rule || "available_time <= as_of_time";
  return raw
    .replace(/available_time\s*<=\s*as_of_time/g, "只使用该时间点之前已经可用的数据")
    .replace(/available_time/g, "数据可用时间")
    .replace(/as_of_time/g, "回看时间");
}

function normalizeSignalStrategyKey(signal: ResearchSnapshotSignal) {
  const raw = String(signal.strategyType || signal.source_strategy || signal.strategy_id || "").trim();
  if (!raw) return "unknown";
  const sourceMatch = raw.match(/^(backtest|replay|agent|manual|paper|strategy)[:/_-](.+)$/i);
  if (sourceMatch) return sourceMatch[2].toLowerCase().replace(/^strategy[:/_-]?/, "");
  return raw.toLowerCase().replace(/^strategy[:/_-]?/, "").replace(/^backtest[-_]/, "");
}

function signalBacktestId(signal: ResearchSnapshotSignal) {
  if (signal.relatedBacktestId !== null && signal.relatedBacktestId !== undefined) return signal.relatedBacktestId;
  const raw = `${signal.strategy_id || ""} ${signal.source_strategy || ""}`;
  const match = raw.match(/backtest[-_:](\d+)/i);
  return match ? Number(match[1]) : null;
}

function signalAction(signal: ResearchSnapshotSignal) {
  return String(signal.action || signal.signal_type || "WAIT").toUpperCase();
}

function signalAsOfTime(signal: ResearchSnapshotSignal) {
  return signal.asOfTime || signal.timestamp || signal.event_time || "";
}

function signalDedupeKey(signal: ResearchSnapshotSignal, fallbackSymbol: string) {
  return [
    String(signal.symbol || fallbackSymbol || "").toUpperCase(),
    normalizeSignalStrategyKey(signal),
    signalAction(signal),
    signalAsOfTime(signal),
    String(signal.data_source || signal.provider || "").toUpperCase(),
    signalBacktestId(signal) ?? "",
  ].join("::");
}

function signalCompletenessScore(signal: ResearchSnapshotSignal) {
  return [
    signal.relatedBacktestId,
    signal.relatedDecisionId,
    signal.relatedOrderIntentId,
    signal.relatedAuditIds?.length,
    signal.triggerReason || signal.trigger_condition,
    signal.sourceEvents?.length,
  ].filter(Boolean).length;
}

function dedupeResearchSignals(signals: ResearchSnapshotSignal[], fallbackSymbol: string) {
  const merged = new Map<string, ResearchSnapshotSignal>();
  for (const signal of signals) {
    const key = signalDedupeKey(signal, fallbackSymbol);
    const existing = merged.get(key);
    const normalizedSignal: ResearchSnapshotSignal = {
      ...signal,
      signalId: signal.signalId ?? signal.id,
      symbol: signal.symbol || fallbackSymbol,
      action: signalAction(signal),
      asOfTime: signalAsOfTime(signal),
      strategyType: normalizeSignalStrategyKey(signal),
      relatedBacktestId: signalBacktestId(signal),
      mergedCount: signal.mergedCount || 1,
      mergedSignalIds: signal.mergedSignalIds || (signal.id ? [signal.id] : []),
      sourceEvents: signal.sourceEvents || [],
    };
    if (!existing) {
      merged.set(key, normalizedSignal);
      continue;
    }
    const keep = signalCompletenessScore(normalizedSignal) > signalCompletenessScore(existing)
      ? normalizedSignal
      : existing;
    const other = keep === normalizedSignal ? existing : normalizedSignal;
    const mergedCount = (existing.mergedCount || 1) + (normalizedSignal.mergedCount || 1);
    const mergedSignalIds = Array.from(new Set([...(keep.mergedSignalIds || []), ...(other.mergedSignalIds || [])]));
    merged.set(key, {
      ...keep,
      mergedCount,
      mergedSignalIds,
      sourceEvents: [...(keep.sourceEvents || []), ...(other.sourceEvents || [])],
      mergeNote: `已合并 ${mergedCount} 条相同信号`,
    });
  }
  return Array.from(merged.values());
}

function signalTimeValue(signal: ResearchSnapshotSignal) {
  const time = new Date(signalAsOfTime(signal)).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function isStrongResearchSignal(signal: ResearchSnapshotSignal) {
  const action = signalAction(signal);
  return action === "BUY" || action === "SELL";
}

function representativeStrongSignals(signals: ResearchSnapshotSignal[]) {
  const grouped = new Map<string, ResearchSnapshotSignal>();
  for (const signal of signals.filter(isStrongResearchSignal)) {
    const key = [
      String(signal.symbol || "").toUpperCase(),
      normalizeSignalStrategyKey(signal),
      signalAction(signal),
      String(signal.data_source || signal.provider || "").toUpperCase(),
    ].join("::");
    const existing = grouped.get(key);
    const currentBacktestId = signalBacktestId(signal);
    const currentCount = signal.mergedCount || signal.similarSignalCount || 1;
    if (!existing) {
      grouped.set(key, {
        ...signal,
        similarSignalCount: currentCount,
        similarBacktestIds: currentBacktestId ? [currentBacktestId] : [],
      });
      continue;
    }
    const backtestIds = Array.from(new Set([...(existing.similarBacktestIds || []), ...(currentBacktestId ? [currentBacktestId] : [])]));
    const keep = signalTimeValue(signal) > signalTimeValue(existing) ? signal : existing;
    const other = keep === signal ? existing : signal;
    grouped.set(key, {
      ...keep,
      similarSignalCount: (existing.similarSignalCount || 1) + currentCount,
      similarBacktestIds: backtestIds,
      mergedSignalIds: Array.from(new Set([...(keep.mergedSignalIds || []), ...(other.mergedSignalIds || [])])),
    });
  }
  return Array.from(grouped.values()).sort((a, b) => signalTimeValue(b) - signalTimeValue(a));
}

function strategyCoverageSignals(signals: ResearchSnapshotSignal[]) {
  const grouped = new Map<string, ResearchSnapshotSignal>();
  for (const signal of signals) {
    const key = normalizeSignalStrategyKey(signal);
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, signal);
      continue;
    }
    const existingStrong = isStrongResearchSignal(existing);
    const nextStrong = isStrongResearchSignal(signal);
    if ((nextStrong && !existingStrong) || (nextStrong === existingStrong && signalTimeValue(signal) > signalTimeValue(existing))) {
      grouped.set(key, signal);
    }
  }
  return Array.from(grouped.values()).sort((a, b) => {
    if (isStrongResearchSignal(a) !== isStrongResearchSignal(b)) return isStrongResearchSignal(a) ? -1 : 1;
    return normalizeSignalStrategyKey(a).localeCompare(normalizeSignalStrategyKey(b));
  });
}

function roleHelpText(sectionKey?: string, title?: string) {
  const key = String(sectionKey || "").toLowerCase();
  if (ROLE_HELP_TEXT[key]) return ROLE_HELP_TEXT[key];
  const titleText = title || "";
  if (titleText.includes("技术")) return ROLE_HELP_TEXT.technical;
  if (titleText.includes("新闻")) return ROLE_HELP_TEXT.news;
  if (titleText.includes("宏观")) return ROLE_HELP_TEXT.macro;
  if (titleText.includes("风险")) return ROLE_HELP_TEXT.risk;
  if (titleText.includes("组合")) return ROLE_HELP_TEXT.portfolio;
  return "该角色负责从自己的角度解释当前市场材料。";
}

const DASHBOARD_TAB_VALUES = ["overview", "diagnostics", "positions", "agents"] as const;
type DashboardTabValue = typeof DASHBOARD_TAB_VALUES[number];

// ─── Order Panel ───────────────────────────────────────────────────────────
interface OrderPanelProps {
  symbol: string;
  exchangeId: string;
  currentPrice: number | null;
  onClose: () => void;
  onOrderPlaced: () => void;
}



// ─── Main Dashboard ─────────────────────────────────────────────────────────

// ─── FactorGroup: interpret factor values into directional judgments ────────────

// ─── Status Card ─────────────────────────────────────────────────────────────
function StatusCard({ title, color, children }: { title: string; color: string; children: React.ReactNode }) {
  var borders: Record<string, string> = { blue: "border-l-blue-400/40", purple: "border-l-purple-400/40", green: "border-l-green-400/40", amber: "border-l-amber-400/40", cyan: "border-l-cyan-400/40", slate: "border-l-slate-400/40" };
  return (
    <div className={"rounded-lg border border-border/50 bg-secondary/20 border-l-2 p-2.5 space-y-1 " + (borders[color] || "")}>
      <p className="text-[10px] text-muted-foreground font-medium">{title}</p>
      {children}
    </div>
  );
}

function errorMessage(error: unknown) {
  const raw = error instanceof Error ? error.message : String(error || "");
  const lower = raw.toLowerCase();
  if (!raw || lower.includes("failed to fetch") || lower.includes("timeout") || lower.includes("abort") || lower.includes("http 5")) {
    return "数据暂不可用，已展示缓存数据 / 暂无数据。";
  }
  return raw.length > 120 ? "数据暂不可用，已展示缓存数据 / 暂无数据。" : raw;
}

function formatPct(v: number | null | undefined) { return v != null ? (v * 100).toFixed(0) + "%" : "—"; }
function signalBadge(s: string) {
  var t = (s || "").toUpperCase();
  if (t === "BUY") return <Badge className="bg-green-500/15 text-green-400 text-[10px]">买入</Badge>;
  if (t === "SELL") return <Badge className="bg-red-500/15 text-red-400 text-[10px]">卖出</Badge>;
  return <Badge className="bg-slate-500/15 text-slate-400 text-[10px]">观察</Badge>;
}

function DashboardPageContent() {
  const searchParams = useSearchParams();
  const requestedSymbol = normalizeSymbolParam(searchParams.get("symbol"));
  const requestedInterval = searchParams.get("interval") || "1h";
  const requestedAsOf = searchParams.get("as_of_time") || "";
  const requestedAsOfIso = normalizeResearchAsOfInput(requestedAsOf) || "";

  const [currentSymbol, setCurrentSymbol] = useState(requestedSymbol);
  const [currentInterval, setCurrentInterval] = useState(requestedInterval);

  // Research snapshot
  const [researchSnapshot, setResearchSnapshot] = useState<ResearchSnapshot | null>(null);
  const [factorDefinitionMap, setFactorDefinitionMap] = useState<Record<string, string>>({});
  const [researchAsOf, setResearchAsOf] = useState(formatResearchAsOfInput(requestedAsOf));
  const [appliedResearchAsOf, setAppliedResearchAsOf] = useState(requestedAsOfIso);
  const [researchLoading, setResearchLoading] = useState(false);
  const [researchError, setResearchError] = useState<string | null>(null);
  const researchAsOfInputRef = useRef<HTMLInputElement | null>(null);

  // L1: macro + news
  const [macro, setMacro] = useState<Record<string, { value: number | null; date: string | null; source?: string; provider?: string }>>({});
  const [headlines, setHeadlines] = useState<Array<{ title: string; source: string; url: string; date: string; symbol: string; summary?: string; sentiment_score?: number | null; topics?: string[] }>>([]);
  const [pipelineStats, setPipelineStats] = useState<{ macro_stored: number; news_stored: number; running: boolean } | null>(null);

  // AI decision trigger
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<{ final_signal?: string; confidence?: number; summary?: string; decision_id?: number } | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  const symbols = [
    { value: "BTCUSDT", label: "BTC/USDT" }, { value: "ETHUSDT", label: "ETH/USDT" },
    { value: "SOLUSDT", label: "SOL/USDT" }, { value: "BNBUSDT", label: "BNB/USDT" },
    { value: "DOGEUSDT", label: "DOGE/USDT" },
  ];
  const intervals = [
    { value: "1m", label: "1分钟" }, { value: "5m", label: "5分钟" },
    { value: "15m", label: "15分钟" }, { value: "1h", label: "1小时" },
    { value: "4h", label: "4小时" }, { value: "1d", label: "1天" },
  ];

  // ── Fetch research snapshot ──────────────────────────────────────────────────
  const fetchResearchSnapshot = useCallback(async () => {
    setResearchLoading(true); setResearchError(null);
    try {
      const params = new URLSearchParams({ interval: currentInterval });
      if (appliedResearchAsOf) params.set("as_of_time", appliedResearchAsOf);
      const res = await fetch("/api/v1/market/research-snapshot/" + currentSymbol + "?" + params.toString());
      if (!res.ok) { setResearchError("HTTP " + res.status); setResearchSnapshot(null); return; }
      setResearchSnapshot(await res.json());
    } catch (e: unknown) { setResearchError(errorMessage(e)); setResearchSnapshot(null); }
    finally { setResearchLoading(false); }
  }, [currentSymbol, currentInterval, appliedResearchAsOf]);

  const fetchMacroNews = useCallback(async () => {
    try {
      const [macroRes, newsRes, pipelineRes] = await Promise.all([
        fetch("/api/v1/market/macro"),
        fetch("/api/v1/market/news?symbol=BTC&limit=20"),
        fetch("/api/v1/system/pipeline"),
      ]);
      setMacro((await macroRes.json()).indicators || {});
      setHeadlines((await newsRes.json()).articles || []);
      setPipelineStats(await pipelineRes.json());
    } catch { /* silent */ }
  }, []);

  const fetchFactorDefinitions = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/signals/factor-definitions");
      if (!res.ok) return;
      const data = await res.json();
      const rows: FactorDefinition[] = Array.isArray(data?.data) ? data.data : [];
      setFactorDefinitionMap(rows.reduce<Record<string, string>>((acc, item) => {
        if (item.factor_name && item.display_name) acc[item.factor_name] = item.display_name;
        return acc;
      }, {}));
    } catch { /* silent */ }
  }, []);

  useEffect(() => { fetchResearchSnapshot(); }, [fetchResearchSnapshot]);
  useEffect(() => { fetchMacroNews(); }, [fetchMacroNews]);
  useEffect(() => { fetchFactorDefinitions(); }, [fetchFactorDefinitions]);

  // ── Trigger AI analysis ─────────────────────────────────────────────────────
  const triggerAiAnalysis = async () => {
    setAiLoading(true); setAiError(null); setAiResult(null);
    try {
      const url = "/api/v1/market/coordinate/" + currentSymbol + "?interval=" + currentInterval + "&fast=true";
      const res = await fetch(url, { signal: AbortSignal.timeout(180000) });
      if (!res.ok) { setAiError("HTTP " + res.status); return; }
      setAiResult(await res.json());
    } catch (e: unknown) { setAiError(errorMessage(e)); }
    finally { setAiLoading(false); }
  };

  // ── Derived values ──────────────────────────────────────────────────────────
  const counts = researchSnapshot?.counts;
  const barPanel = researchSnapshot?.bar_panel;
  const barSummary = barPanel?.summary;
  const factorPanel = researchSnapshot?.factor_panel;
  const signalPanel = researchSnapshot?.signal_panel || [];
  const newsPanel = researchSnapshot?.news_panel || [];
  const taPanel = researchSnapshot?.tradingagents_panel;
  const macroTags = factorPanel?.macro_event_tags || [];

  // Signal counts
  const signalCounts = { BUY: 0, SELL: 0, WAIT: 0 };
  signalPanel.forEach((s: any) => {
    const t = (s?.signal_type || s?.action || "WAIT").toUpperCase();
    if (t === "BUY") signalCounts.BUY++;
    else if (t === "SELL") signalCounts.SELL++;
    else signalCounts.WAIT++;
  });

  const isPointInTime = !!appliedResearchAsOf;
  const isProxyVwap = barSummary?.vwap_method === "typical_price_proxy";

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <>
      <AppTopNav activeSection="overview" title="研究台" subtitle="TradingAgents 驾驶舱" />

      <div className="container mx-auto px-4 py-4 space-y-3 max-w-7xl">

        {/* Row 1: Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <Select value={currentSymbol} onValueChange={(v) => { setCurrentSymbol(v); setAiResult(null); }}>
            <SelectTrigger className="w-32 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>{symbols.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={currentInterval} onValueChange={(v) => { setCurrentInterval(v); setAiResult(null); }}>
            <SelectTrigger className="w-20 h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>{intervals.map(i => <SelectItem key={i.value} value={i.value}>{i.label}</SelectItem>)}</SelectContent>
          </Select>
          <input ref={researchAsOfInputRef} type="text" value={researchAsOf} onChange={(e) => setResearchAsOf(e.target.value)}
            placeholder="回看时间(留空=当前)" className="h-8 w-40 rounded border border-border bg-secondary/40 px-2 text-xs" />
          <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => {
            const v = researchAsOfInputRef.current?.value || researchAsOf;
            const iso = normalizeResearchAsOfInput(v);
            if (iso === null) { setResearchError("时间格式无法识别"); return; }
            setAppliedResearchAsOf(iso);
          }} disabled={researchLoading}>回看</Button>
          <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => { setResearchAsOf(""); setAppliedResearchAsOf(""); }}
            disabled={researchLoading}>查看当前</Button>
          {researchLoading && <RefreshCw className="h-4 w-4 animate-spin text-cyan-400" />}
          {isPointInTime && <Badge variant="outline" className="text-[10px] border-amber-400/30 text-amber-300">回看模式</Badge>}
          {counts && <span className="text-[10px] text-muted-foreground ml-auto">截止 {researchSnapshot?.as_of_time ? new Date(researchSnapshot.as_of_time).toLocaleString("zh-CN") : "当前"}</span>}
        </div>

        {/* Error / Loading */}
        {researchError && <div className="text-xs text-red-400 p-2 border border-red-500/20 rounded bg-red-500/5">研究快照暂不可用：{researchError}</div>}
        {researchLoading && !researchSnapshot && <div className="text-xs text-cyan-300 p-2 border border-cyan-400/20 rounded bg-cyan-400/5"><RefreshCw className="mr-1 inline h-3 w-3 animate-spin" />整理材料中…</div>}

        {/* Row 2: One-line Conclusion */}
        {counts && (
          <Card className="border-2 border-cyan-400/20 bg-cyan-400/5">
            <CardContent className="py-3">
              <div className="flex items-center gap-2 text-sm flex-wrap">
                <Brain className="w-4 h-4 text-cyan-400 shrink-0" />
                <span className="text-foreground font-medium">{currentSymbol} · {currentInterval}</span>
                <span className="text-muted-foreground">
                  {counts.factors === 0 && signalCounts.BUY === 0 && signalCounts.SELL === 0
                    ? "当前未出现明确买卖信号，AI 倾向观察；但因子数据缺失，且风控未通过，暂不建议交易。"
                    : signalCounts.BUY > signalCounts.SELL ? "信号偏多" : signalCounts.SELL > signalCounts.BUY ? "信号偏空" : "信号中性"}
                  {(counts.factors ?? 0) > 0 && <>，{counts.bars ?? 0}根K线，{counts.factors ?? 0}个因子，{counts.news ?? 0}条新闻</>}
                </span>
                {taPanel ? (
                  <Badge className={taPanel.final_signal === "BUY" ? "bg-green-500/20 text-green-300" : taPanel.final_signal === "SELL" ? "bg-red-500/20 text-red-300" : "bg-slate-500/20 text-slate-300"}>
                    AI: {taPanel.final_signal === "BUY" ? "买入" : taPanel.final_signal === "SELL" ? "卖出" : "观察"} {formatPct(taPanel.confidence)}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px] text-amber-400">AI 未触发</Badge>
                )}
                {taPanel?.risk_veto && <Badge className="bg-red-500/15 text-red-400 text-[10px]">风控否决</Badge>}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Row 3: Six Status Cards */}
        {counts && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
            <StatusCard title="行情" color="blue">
              <div className="text-[11px] font-mono">
                <span className={isProxyVwap ? "text-amber-300" : "text-foreground"}>{barSummary?.close != null ? "$" + toFiniteNumber(barSummary.close).toFixed(0) : "—"}</span>
              </div>
              <div className="text-[9px] text-muted-foreground/50">vol {barSummary?.volume ? formatCompactNumber(barSummary.volume) : "—"} · {isProxyVwap ? "代理VWAP" : "真实VWAP"}</div>
            </StatusCard>

            <StatusCard title="因子" color="purple">
              {(counts.factors ?? 0) > 0 ? (
                <>
                  <div className="text-[10px]">
                    技术{factorPanel?.groups?.technical?.length || 0} 情绪{factorPanel?.groups?.sentiment?.length || 0} 宏观{factorPanel?.groups?.macro?.length || 0}
                  </div>
                  <Link href={"/signals?symbol=" + currentSymbol} className="text-[9px] text-cyan-400 hover:text-cyan-300">详情 →</Link>
                </>
              ) : (
                <>
                  <div className="text-[10px] text-amber-400">因子未生成</div>
                  <Link href={"/signals?symbol=" + currentSymbol} className="text-[9px] text-cyan-400 hover:text-cyan-300">查看原因 →</Link>
                </>
              )}
            </StatusCard>

            <StatusCard title="信号" color="green">
              <div className="flex gap-1">
                <Badge className="bg-green-500/15 text-green-400 text-[9px]">买{signalCounts.BUY}</Badge>
                <Badge className="bg-red-500/15 text-red-400 text-[9px]">卖{signalCounts.SELL}</Badge>
                <Badge className="bg-slate-500/15 text-slate-400 text-[9px]">观{signalCounts.WAIT}</Badge>
              </div>
              <Link href={"/signals?symbol=" + currentSymbol} className="text-[9px] text-cyan-400 hover:text-cyan-300">详情 →</Link>
            </StatusCard>

            <StatusCard title="新闻" color="amber">
              <div className="text-[10px] text-muted-foreground line-clamp-2">
                {headlines[0]?.title?.slice(0, 60) || "暂无"}
              </div>
              <div className="text-[9px] text-muted-foreground/50">当前快照 {newsPanel.length || 0} 条</div>
            </StatusCard>

            <StatusCard title="AI决策" color="cyan">
              {taPanel ? (
                <>
                  <div className="flex items-center gap-1">{signalBadge(taPanel.final_signal || "")}<span className="text-[10px]">{formatPct(taPanel.confidence)}</span></div>
                  <div className="text-[9px]">
                    <span className={taPanel.risk_veto ? "text-red-400" : "text-green-400"}>风控: {taPanel.risk_veto ? "否决" : "通过"}</span>
                    <span className="text-muted-foreground/50 ml-1">· {taPanel.final_signal === "WAIT" ? "不交易" : "交易"}</span>
                  </div>
                  <Link href={"/decisions?symbol=" + currentSymbol} className="text-[9px] text-cyan-400 hover:text-cyan-300">完整分析 →</Link>
                </>
              ) : (
                <>
                  <span className="text-[10px] text-muted-foreground">未触发</span>
                  <Button size="sm" className="h-6 text-[9px] gap-1 mt-1" onClick={triggerAiAnalysis} disabled={aiLoading}>
                    {aiLoading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Brain className="h-3 w-3" />}
                    {aiLoading ? "…" : "生成"}
                  </Button>
                </>
              )}
            </StatusCard>

            <StatusCard title="数据质量" color="slate">
              <div className="text-[10px]">
                <span className={isProxyVwap ? "text-amber-400" : "text-green-400"}>{isProxyVwap ? "典型价格代理" : "真实VWAP"}</span>
              </div>
              <div className="text-[9px] text-muted-foreground/50">{barSummary?.source || "market_data_gateway"} · {counts.bars ?? 0}根K线</div>
              {isProxyVwap && <div className="text-[8px] text-amber-400/60">非真实VWAP，无quote_volume</div>}
            </StatusCard>
          </div>
        )}

        {/* Row 4: No AI Decision Prompt */}
        {!taPanel && !aiLoading && counts && (
          <Card className="border border-dashed border-cyan-400/30 bg-cyan-400/3">
            <CardContent className="py-3 flex items-center justify-between">
              <p className="text-xs text-muted-foreground">当前快照暂无 AI 决策，基于上方研究材料生成 TradingAgents 综合分析</p>
              <Button size="sm" className="gap-2 shrink-0" onClick={triggerAiAnalysis} disabled={aiLoading}>
                <Brain className="h-4 w-4" />基于当前快照生成 AI 决策
              </Button>
            </CardContent>
          </Card>
        )}
        {aiError && <div className="text-xs text-red-400">{aiError}</div>}
        {aiResult && !taPanel && (
          <div className="text-xs text-green-300 p-2 border border-green-400/20 rounded bg-green-400/5">
            分析完成！信号：{aiResult.final_signal}，置信度：{formatPct(aiResult.confidence)}。
            <Link href={"/decisions?symbol=" + currentSymbol} className="text-cyan-400 ml-2">查看 →</Link>
          </div>
        )}

        {/* Row 5: Quick Links */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {[
            { href: "/signals?symbol=" + currentSymbol, label: "因子与信号", icon: "🔬" },
            { href: "/decisions?symbol=" + currentSymbol, label: "完整AI分析", icon: "🧠" },
            { href: "/data-sources", label: "新闻与数据源", icon: "📡" },
            { href: "/trades", label: "模拟交易", icon: "💼" },
            { href: "/audit", label: "审计链路", icon: "🛡️" },
          ].map(item => (
            <Link key={item.href} href={item.href}
              className="flex items-center gap-2 p-2.5 rounded-lg border border-border/50 bg-secondary/30 hover:bg-secondary/50 hover:border-cyan-400/30 transition-all text-xs">
              <span className="text-base">{item.icon}</span>
              <span className="text-foreground/80">{item.label}</span>
              <ArrowRight className="w-3 h-3 text-muted-foreground ml-auto" />
            </Link>
          ))}
        </div>

      </div>
    </>
  );
}

export default function DashboardPage() {
  return <DashboardPageContent />;
}
