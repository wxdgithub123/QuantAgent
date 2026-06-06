"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Prd104StatusPanel } from "@/components/prd/Prd104StatusPanel";
import { PrdV1FlowPanel } from "@/components/prd/PrdV1FlowPanel";

const TradingViewChart = dynamic(
  () => import("@/components/charts/TradingViewChart").then((mod) => mod.TradingViewChart),
  { ssr: false }
);
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import {
  TrendingUp, TrendingDown, Activity, BarChart3, Settings,
  DollarSign, BarChart2, RefreshCw, WifiOff,
  ChevronDown, ChevronUp, Brain, Shield, Zap, X, Plus, Minus,
  History, BarChart, Server, CheckCircle,
  Globe, Newspaper, ExternalLink
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
  quantity: number;
  avg_price: number;
  mark_price: number;
  pnl: number;
  pnl_pct: number;
}

interface PaperOrder {
  order_id: string;
  symbol: string;
  side: "BUY" | "SELL" | string;
  order_type: string;
  quantity: number;
  price: number;
  fee: number;
  pnl: number | null;
  status: string;
  created_at: string;
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
  bars?: number;
  bars_displayed?: number;
  factors?: number;
  factors_displayed?: number;
  technical_factors?: number;
  sentiment_factors?: number;
  macro_factors?: number;
  signals?: number;
  signals_displayed?: number;
  news?: number;
  news_displayed?: number;
  macro?: number;
  macro_displayed?: number;
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
  event_time?: string;
  available_time?: string;
  timestamp?: string;
  signal_type?: string;
  signal_value?: number;
  strength?: number;
  direction_strength?: number;
  direction_strength_label?: string;
  is_triggered?: boolean;
  confidence?: number;
  trigger_condition?: string;
  source_strategy?: string;
  provider?: string;
  data_source?: string;
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

const normalizeResearchAsOfInput = (value: string) => {
  const raw = value.trim();
  if (!raw) return "";
  const candidate = raw.includes("T") ? raw : raw.replace(" ", "T");
  const date = new Date(candidate);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
};

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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
  macro_cpi: "CPI 通胀指标",
  macro_fed_funds_rate: "联邦基金利率",
  macro_inflation_expect: "通胀预期",
  macro_m2_money_supply: "M2 货币供应",
  macro_treasury_10y: "10年期美债收益率",
  macro_unemployment: "失业率",
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
  const normalized = raw.toLowerCase().replace(/^strategy[:/_-]?/, "");
  return FALLBACK_STRATEGY_LABELS[normalized] || raw;
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

function OrderPanel({ symbol, exchangeId, currentPrice, onClose, onOrderPlaced }: OrderPanelProps) {
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [quantity, setQuantity] = useState("0.01");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const estimatedCost = currentPrice ? parseFloat(quantity || "0") * currentPrice : 0;

  const handleSubmit = async () => {
    setError(null); setSuccess(null);
    const qty = parseFloat(quantity);
    if (isNaN(qty) || qty <= 0) { setError("请输入有效数量"); return; }
    setLoading(true);
    try {
      const res = await fetch("/api/v1/trading/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, side, order_type: "MARKET", quantity: qty, exchange_id: exchangeId }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "下单失败"); return; }
      setSuccess(`${side} ${qty} ${symbol} @ $${toFiniteNumber(data.price, currentPrice ?? 0).toFixed(2)} ✓`);
      onOrderPlaced();
    } catch {
      setError("网络错误，请检查后端连接");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="bg-card border border-border rounded-2xl p-6 w-[360px] shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-foreground font-bold text-lg">模拟下单</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Symbol */}
        <div className="mb-4 p-3 bg-secondary rounded-xl">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground text-sm">交易对</span>
            <span className="text-foreground font-bold">{symbol}</span>
          </div>
          {currentPrice && (
            <div className="flex items-center justify-between mt-1">
              <span className="text-muted-foreground text-xs">当前价格</span>
              <span className="text-blue-400 text-sm font-mono">${currentPrice.toLocaleString()}</span>
            </div>
          )}
        </div>

        {/* Buy / Sell Toggle */}
        <div className="flex rounded-xl overflow-hidden mb-4 border border-border">
          <button
            onClick={() => setSide("BUY")}
            className={`flex-1 py-2.5 text-sm font-bold transition-all ${
              side === "BUY" ? "bg-green-600 text-white" : "bg-secondary text-muted-foreground hover:text-foreground/90"
            }`}
          >
            买入 BUY
          </button>
          <button
            onClick={() => setSide("SELL")}
            className={`flex-1 py-2.5 text-sm font-bold transition-all ${
              side === "SELL" ? "bg-red-600 text-white" : "bg-secondary text-muted-foreground hover:text-foreground/90"
            }`}
          >
            卖出 SELL
          </button>
        </div>

        {/* Quantity */}
        <div className="mb-4">
          <label className="text-muted-foreground text-xs mb-1.5 block">数量</label>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setQuantity(q => Math.max(0.001, parseFloat(q) - 0.01).toFixed(4))}
              className="w-8 h-8 bg-secondary rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground border border-border"
            >
              <Minus className="w-3 h-3" />
            </button>
            <input
              type="number"
              value={quantity}
              onChange={e => setQuantity(e.target.value)}
              step="0.01"
              min="0.001"
              className="flex-1 bg-secondary border border-border rounded-lg px-3 py-2 text-foreground text-sm text-center focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={() => setQuantity(q => (parseFloat(q) + 0.01).toFixed(4))}
              className="w-8 h-8 bg-secondary rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground border border-border"
            >
              <Plus className="w-3 h-3" />
            </button>
          </div>
          {estimatedCost > 0 && (
            <p className="text-muted-foreground text-xs mt-1.5 text-right">
              预估金额：<span className="text-foreground/80">${estimatedCost.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
            </p>
          )}
        </div>

        {/* Quick qty buttons */}
        <div className="flex gap-2 mb-4">
          {["0.01", "0.1", "0.5", "1"].map(v => (
            <button
              key={v}
              onClick={() => setQuantity(v)}
              className={`flex-1 py-1.5 text-xs rounded-lg border transition-all ${
                quantity === v
                  ? "bg-blue-600/20 border-blue-500/50 text-blue-400"
                  : "bg-secondary border-border text-muted-foreground hover:text-foreground/90"
              }`}
            >
              {v}
            </button>
          ))}
        </div>

        {error   && <div className="mb-3 p-2 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-xs">{error}</div>}
        {success && <div className="mb-3 p-2 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 text-xs">{success}</div>}

        <Button
          onClick={handleSubmit}
          disabled={loading}
          className={`w-full font-bold py-3 rounded-xl ${
            side === "BUY"
              ? "bg-green-600 hover:bg-green-500 text-white"
              : "bg-red-600 hover:bg-red-500 text-white"
          }`}
        >
          {loading ? <RefreshCw className="w-4 h-4 animate-spin mr-2" /> : null}
          {loading ? "提交中..." : `${side === "BUY" ? "买入" : "卖出"} ${symbol}`}
        </Button>
      </div>
    </div>
  );
}

// ─── Main Dashboard ─────────────────────────────────────────────────────────
export default function DashboardPage() {
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab") || "overview";
  const requestedSymbol = normalizeSymbolParam(searchParams.get("symbol"));
  const requestedInterval = searchParams.get("interval") || "1h";
  const requestedAsOf = searchParams.get("as_of_time") || "";
  const requestedAsOfIso = normalizeResearchAsOfInput(requestedAsOf) || "";
  const initialDashboardTab: DashboardTabValue = DASHBOARD_TAB_VALUES.includes(requestedTab as DashboardTabValue)
    ? (requestedTab as DashboardTabValue)
    : "overview";
  const pageTitle =
    initialDashboardTab === "positions"
      ? "模拟交易"
      : initialDashboardTab === "diagnostics"
      ? "系统诊断"
      : initialDashboardTab === "agents"
      ? "智能体面板"
      : "行情总览";
  const pageDescription =
    initialDashboardTab === "positions"
      ? "这里集中处理虚拟账户、模拟下单、持仓盈亏、风控状态和最近成交；不会连接真实资金账户。"
      : initialDashboardTab === "diagnostics"
      ? "这里集中查看数据链路、OpenBB/CCXT、Hummingbot 和 PRD 流程状态。"
      : initialDashboardTab === "agents"
      ? "这里查看子分析 Agent 状态；默认最终建议仍由 TradingAgents 决策链生成。"
      : "这里集中看价格、K 线、数据来源、热门币种、新闻和宏观背景；模拟执行请切到顶部的“模拟盘”。";
  const isPaperTradingPage = initialDashboardTab === "positions";
  const [ticker, setTicker] = useState<Ticker | null>(null);
  const [currentSymbol, setCurrentSymbol] = useState(requestedSymbol);
  const [currentInterval, setCurrentInterval] = useState(requestedInterval);
  const [currentExchange, setCurrentExchange] = useState("okx");
  const [wsStatus, setWsStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");

  // Paper trading state
  const [balance, setBalance] = useState<{ total_balance: number; available_balance: number } | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [riskStatus, setRiskStatus] = useState<RiskStatus | null>(null);
  const [paperOrders, setPaperOrders] = useState<PaperOrder[]>([]);
  const [showOrderPanel, setShowOrderPanel] = useState(false);
  const [positionsLoading, setPositionsLoading] = useState(true);
  const [ordersLoading, setOrdersLoading] = useState(true);

  // Ollama status
  const [ollamaStatus, setOllamaStatus] = useState<{ online: boolean; checked: boolean; model_available?: boolean }>({ online: false, checked: false });
  const [comparisonData, setComparisonData] = useState<ComparisonData | null>(null);
  const [loadingComparison, setLoadingComparison] = useState(false);
  const [trendingCoins, setTrendingCoins] = useState<TrendingCoin[]>([]);
  const [trendingStatus, setTrendingStatus] = useState<"loading" | "ok" | "unavailable">("loading");

  // Hummingbot status
  const [hummingbotStatus, setHummingbotStatus] = useState<{ connected: boolean; apiUrl: string; version: string; timestamp: string } | null>(null);
  const [hummingbotDocker, setHummingbotDocker] = useState<{ connected: boolean; containerCount: number } | null>(null);
  const [hummingbotConnectors, setHummingbotConnectors] = useState<{ connected: boolean; count: number } | null>(null);
  const [hummingbotBots, setHummingbotBots] = useState<{ connected: boolean; count: number; source: string } | null>(null);
  const [hummingbotReadonly, setHummingbotReadonly] = useState<{ portfolio: boolean; orders: boolean; positions: boolean }>({ portfolio: false, orders: false, positions: false });

  // L1 data: macro + news
  const [macro, setMacro] = useState<Record<string, { value: number | null; date: string | null }>>({});
  const [headlines, setHeadlines] = useState<Array<{ title: string; source: string; url: string; date: string; symbol: string }>>([]);
  const [pipelineStats, setPipelineStats] = useState<{ macro_stored: number; news_stored: number; running: boolean } | null>(null);
  const [researchSnapshot, setResearchSnapshot] = useState<ResearchSnapshot | null>(null);
  const [factorDefinitionMap, setFactorDefinitionMap] = useState<Record<string, string>>({});
  const [researchAsOf, setResearchAsOf] = useState(formatResearchAsOfInput(requestedAsOf));
  const [appliedResearchAsOf, setAppliedResearchAsOf] = useState(requestedAsOfIso);
  const [researchLoading, setResearchLoading] = useState(false);
  const [researchError, setResearchError] = useState<string | null>(null);
  const researchAsOfInputRef = useRef<HTMLInputElement | null>(null);

  const fetchMacroNews = useCallback(async () => {
    try {
      const [macroRes, newsRes, pipelineRes] = await Promise.all([
        fetch("/api/v1/market/macro"),
        fetch("/api/v1/market/news?symbol=BTC&limit=8"),
        fetch("/api/v1/system/pipeline"),
      ]);
      const md = await macroRes.json();
      const nd = await newsRes.json();
      const pd = await pipelineRes.json();
      setMacro(md.indicators || {});
      setHeadlines(nd.articles || []);
      setPipelineStats(pd);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { fetchMacroNews(); }, [fetchMacroNews]);

  const fetchFactorDefinitions = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/signals/factor-definitions");
      if (!res.ok) return;
      const data = await res.json();
      const rows: FactorDefinition[] = Array.isArray(data?.data) ? data.data : [];
      const nextMap = rows.reduce<Record<string, string>>((acc, item) => {
        if (item.factor_name && item.display_name) {
          acc[item.factor_name] = item.display_name;
          acc[item.factor_name.toLowerCase()] = item.display_name;
        }
        return acc;
      }, {});
      setFactorDefinitionMap(nextMap);
    } catch {
      // 因子字典只是展示增强；接口暂不可用时保留兜底中文名。
    }
  }, []);

  useEffect(() => { void fetchFactorDefinitions(); }, [fetchFactorDefinitions]);

  const fetchResearchSnapshot = useCallback(async (signal?: AbortSignal) => {
    if (!currentSymbol) return;
    setResearchLoading(true);
    setResearchError(null);
    try {
      const params = new URLSearchParams({ interval: currentInterval });
      if (appliedResearchAsOf) {
        params.set("as_of_time", appliedResearchAsOf);
      }
      let lastError = "";
      for (let attempt = 0; attempt < 3; attempt += 1) {
        const res = await fetch(`/api/v1/market/research-snapshot/${currentSymbol}?${params.toString()}`, {
          signal,
        });
        if (res.ok) {
          setResearchSnapshot(await res.json());
          return;
        }
        const data = await res.json().catch(() => null);
        lastError = typeof data?.detail === "string" ? data.detail : `HTTP ${res.status}`;
        if (![500, 502, 503, 504].includes(res.status) || attempt === 2) {
          throw new Error(lastError);
        }
        await wait(1200 * (attempt + 1));
      }
      throw new Error(lastError || "研究快照暂不可用");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setResearchSnapshot(null);
      const message = error instanceof Error ? error.message : "研究快照暂不可用";
      setResearchError(
        message.startsWith("HTTP 5")
          ? "后端服务刚启动或正在重启，请稍等几秒刷新；系统不会用假数据补位。"
          : message
      );
    } finally {
      setResearchLoading(false);
    }
  }, [currentSymbol, currentInterval, appliedResearchAsOf]);

  useEffect(() => {
    const controller = new AbortController();
    void fetchResearchSnapshot(controller.signal);
    return () => controller.abort();
  }, [fetchResearchSnapshot]);

  useEffect(() => {
    let cancelled = false;
    setTrendingStatus("loading");

    fetch("/api/v1/market/coingecko/trending")
      .then(r => {
        if (!r.ok) throw new Error(`CoinGecko trending failed: ${r.status}`);
        return r.json();
      })
      .then(d => {
        if (cancelled) return;
        const trending = Array.isArray(d.trending) ? d.trending : [];
        setTrendingCoins(trending);
        setTrendingStatus(trending.length > 0 ? "ok" : "unavailable");
      })
      .catch(() => {
        if (cancelled) return;
        setTrendingCoins([]);
        setTrendingStatus("unavailable");
      });

    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!currentSymbol) return;
    setLoadingComparison(true);

    const selectedExchange = currentExchange;
    const selectedExchangeLabel = selectedExchange.toUpperCase();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 45000);

    // 交易所报价只显示真实请求结果，不做模拟 fallback，避免误导。
    const fetchPriceFromExchange = async (exchangeId: string) => {
      try {
        const res = await fetch(`/api/v1/market/${exchangeId}/price/${currentSymbol}`, { signal: controller.signal });
        if (res.ok) {
          const data = await res.json();
          return { price: hasFiniteNumber(data.price) ? toFiniteNumber(data.price) : null, error: undefined };
        }
        const data = await res.json().catch(() => null);
        const detail = typeof data?.detail === "string" ? data.detail : `${selectedExchangeLabel} 实时报价暂不可用`;
        return { price: null, error: detail };
      } catch (error) {
        const message = error instanceof DOMException && error.name === "AbortError"
          ? `${selectedExchangeLabel} 实时报价请求超时，请确认 Clash 仍在运行`
          : `${selectedExchangeLabel} 实时报价暂不可用`;
        return { price: null, error: message };
      }
    };

    fetchPriceFromExchange(selectedExchange).then(({ price: exchangePrice, error: exchangeError }) => {
      setComparisonData((current) => {
        const gatewayPrice = hasFiniteNumber(current?.gateway_price)
          ? toFiniteNumber(current?.gateway_price)
          : hasFiniteNumber(lastTickerRef.current?.price)
            ? toFiniteNumber(lastTickerRef.current?.price)
            : null;
        return buildComparisonData(gatewayPrice, exchangePrice, selectedExchangeLabel, exchangeError);
      });
    }).finally(() => {
      clearTimeout(timeout);
      setLoadingComparison(false);
    });

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [currentSymbol, currentExchange]);

  useEffect(() => {
    if (!hasFiniteNumber(ticker?.price)) return;
    const gatewayPrice = toFiniteNumber(ticker.price);
    setComparisonData((current) => {
      if (!current) return current;
      return buildComparisonData(gatewayPrice, current.exchange_price, current.exchange_label, current.error);
    });
  }, [ticker?.price]);

  // Cooldown & Cache refs
  const analysisCache = useRef<AnalysisCache>({});
  const cooldownTracker = useRef<CooldownTracker>({});
  const [cooldownRemaining, setCooldownRemaining] = useState<Record<string, number>>({});

  // WebSocket ref
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const lastTickerRef = useRef<Ticker | null>(null); // 保留最后的价格数据

  // Agent State
  const [agents, setAgents] = useState([
    { id: "trend", name: "趋势跟踪Agent", type: "trend", status: "运行中", provider: "ollama", action: "分析趋势", icon: TrendingUp, logs: "点击「分析」开始", analyzing: false, isStreaming: false, thinkingContent: "", outputContent: "", thinkCollapsed: true, profit: "+$145.20", winRate: "...", winRateLoading: true, color: "blue" },
    { id: "mean_reversion", name: "均值回归Agent", type: "mean_reversion", status: "运行中", provider: "ollama", action: "寻找反转", icon: Activity, logs: "点击「分析」开始", analyzing: false, isStreaming: false, thinkingContent: "", outputContent: "", thinkCollapsed: true, profit: "+$32.50", winRate: "...", winRateLoading: true, color: "purple" },
    { id: "risk", name: "风险管理Agent", type: "risk", status: "运行中", provider: "ollama", action: "监控风险", icon: Shield, logs: "点击「分析」开始", analyzing: false, isStreaming: false, thinkingContent: "", outputContent: "", thinkCollapsed: true, profit: "--", winRate: "...", winRateLoading: true, color: "orange" },
  ]);
  const [configuringAgent, setConfiguringAgent] = useState<string | null>(null);


  const symbols = [
    { value: "BTCUSDT", label: "BTC/USDT" }, { value: "ETHUSDT", label: "ETH/USDT" },
    { value: "SOLUSDT", label: "SOL/USDT" }, { value: "BNBUSDT", label: "BNB/USDT" },
    { value: "DOGEUSDT", label: "DOGE/USDT" },
  ];

  // 只展示当前项目已经实际接入过的模拟盘报价来源，避免把“库支持”误认为“已接入”。
  const exchanges = [
    { value: "okx", label: "OKX", detail: "CCXT/OKX 实时报价，用于模拟盘标记价格和模拟成交参考" },
  ];
  const currentExchangeInfo = exchanges.find(ex => ex.value === currentExchange) ?? exchanges[0];

  const intervals = [
    { value: "1m", label: "1分钟" }, { value: "5m", label: "5分钟" },
    { value: "15m", label: "15分钟" }, { value: "1h", label: "1小时" },
    { value: "4h", label: "4小时" }, { value: "1d", label: "1天" },
  ];
  const aiProviders = [
    { value: "openai", label: "Custom Model (Aliyun Qwen)" },
    { value: "ollama", label: "Ollama (Local)" },
  ];

  const handleSymbolChange = useCallback((symbol: string) => {
    setCurrentSymbol(symbol);
    setTicker(null);
    setComparisonData(null);
    setResearchSnapshot(null);
    setResearchError(null);
    lastTickerRef.current = null;
  }, []);

  // ── Fetch balance & positions ──────────────────────────────────────────────
  const fetchBalance = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/trading/balance");
      if (res.ok) {
        const data = await res.json();
        setBalance({
          total_balance: toFiniteNumber(data.total_balance),
          available_balance: toFiniteNumber(data.available_balance),
        });
      }
    } catch { /* ignore */ }
  }, []);

  const fetchPositions = useCallback(async () => {
    setPositionsLoading(true);
    try {
      const res = await fetch(`/api/v1/trading/positions?exchange_id=${currentExchange}`);
      if (res.ok) {
        const data = await res.json();
        setPositions(data.positions || []);
      }
    } catch { /* ignore */ }
    finally { setPositionsLoading(false); }
  }, [currentExchange]);

  const fetchRiskStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/trading/risk-status?exchange_id=${currentExchange}`);
      if (res.ok) setRiskStatus(await res.json());
    } catch { /* ignore */ }
  }, [currentExchange]);

  const fetchPaperOrders = useCallback(async () => {
    setOrdersLoading(true);
    try {
      const res = await fetch(`/api/v1/trading/orders?limit=8`);
      if (res.ok) {
        const data = await res.json();
        setPaperOrders(data.orders || []);
      }
    } catch { /* ignore */ }
    finally { setOrdersLoading(false); }
  }, []);

  // ── Fetch Hummingbot Status ────────────────────────────────────────────
  const fetchHummingbotStatus = useCallback(async () => {
    try {
      const [statusRes, dockerRes, connectorsRes, botsRes, portfolioRes, ordersRes, positionsRes] = await Promise.allSettled([
        fetch("/api/v1/hummingbot/status"),
        fetch("/api/v1/hummingbot/docker"),
        fetch("/api/v1/hummingbot/connectors"),
        fetch("/api/v1/hummingbot/bots"),
        fetch("/api/v1/hummingbot/portfolio"),
        fetch("/api/v1/hummingbot/orders"),
        fetch("/api/v1/hummingbot/positions"),
      ]);

      // Status
      if (statusRes.status === "fulfilled" && statusRes.value.ok) {
        const data = await statusRes.value.json();
        setHummingbotStatus({
          connected: data.connected,
          apiUrl: "http://localhost:8000",
          version: data.data?.version || data.data?.hb_version || "—",
          timestamp: data.timestamp || "",
        });
      } else {
        setHummingbotStatus({ connected: false, apiUrl: "http://localhost:8000", version: "—", timestamp: "" });
      }

      // Docker
      if (dockerRes.status === "fulfilled" && dockerRes.value.ok) {
        const data = await dockerRes.value.json();
        const containers = data.data?.active_containers;
        const count = Array.isArray(containers) ? containers.length : 0;
        setHummingbotDocker({ connected: data.connected, containerCount: count });
      } else {
        setHummingbotDocker({ connected: false, containerCount: 0 });
      }

      // Connectors
      if (connectorsRes.status === "fulfilled" && connectorsRes.value.ok) {
        const data = await connectorsRes.value.json();
        const connectors = data.data;
        const count = Array.isArray(connectors) ? connectors.length : (typeof connectors === "object" && connectors !== null ? Object.keys(connectors).length : 0);
        setHummingbotConnectors({ connected: data.connected, count });
      } else {
        setHummingbotConnectors({ connected: false, count: 0 });
      }

      // Bots
      if (botsRes.status === "fulfilled" && botsRes.value.ok) {
        const data = await botsRes.value.json();
        let count = 0;
        if (data.data?.bots && typeof data.data.bots === "object") {
          const bots = data.data.bots;
          if (Array.isArray((bots as Record<string, unknown>).active_bots)) {
            count = ((bots as { active_bots: unknown[] }).active_bots).length;
          } else if (Array.isArray((bots as Record<string, unknown>).discovered_bots)) {
            count = ((bots as { discovered_bots: unknown[] }).discovered_bots).length;
          }
        } else if (data.data?.containers_fallback?.containers) {
          count = data.data.containers_fallback.containers.length;
        }
        setHummingbotBots({ connected: data.connected, count, source: data.data?.source || "—" });
      } else {
        setHummingbotBots({ connected: false, count: 0, source: "—" });
      }

      // Portfolio
      let hasPortfolio = false;
      if (portfolioRes.status === "fulfilled" && portfolioRes.value.ok) {
        try {
          const data = await portfolioRes.value.json();
          if (data.connected && data.data) {
            const accounts = data.data?.accounts;
            const portfolioState = data.data?.portfolio_state;
            hasPortfolio = (Array.isArray(accounts) && accounts.length > 0) ||
                           (portfolioState && typeof portfolioState === "object" && Object.keys(portfolioState).length > 0);
          }
        } catch { /* ignore */ }
      }

      // Orders
      let hasOrders = false;
      if (ordersRes.status === "fulfilled" && ordersRes.value.ok) {
        try {
          const data = await ordersRes.value.json();
          if (data.connected && data.data) {
            const active = data.data?.active_orders;
            const history = data.data?.history_orders;
            hasOrders = (Array.isArray(active) && active.length > 0) ||
                        (Array.isArray(history) && history.length > 0);
          }
        } catch { /* ignore */ }
      }

      // Positions
      let hasPositions = false;
      if (positionsRes.status === "fulfilled" && positionsRes.value.ok) {
        try {
          const data = await positionsRes.value.json();
          if (data.connected && data.data) {
            const positions = data.data?.positions;
            hasPositions = Array.isArray(positions) && positions.length > 0;
          }
        } catch { /* ignore */ }
      }

      setHummingbotReadonly({ portfolio: hasPortfolio, orders: hasOrders, positions: hasPositions });
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchBalance();
    fetchPositions();
    fetchRiskStatus();
    fetchPaperOrders();
    fetchHummingbotStatus();
    const t = setInterval(() => { fetchBalance(); fetchPositions(); fetchRiskStatus(); fetchPaperOrders(); fetchHummingbotStatus(); }, 30000);
    return () => clearInterval(t);
  }, [fetchBalance, fetchPositions, fetchRiskStatus, fetchPaperOrders, fetchHummingbotStatus]);

  // ── WebSocket ──────────────────────────────────────────────────────────────
  const connectWS = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setWsStatus("connecting");
    const wsUrl = getWsUrl();
    console.log("Connecting to WebSocket:", wsUrl);

    // 清理旧连接
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }

    // 连接超时（10秒）
    const connectTimeout = setTimeout(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.CONNECTING) {
        console.warn("WebSocket connection timeout");
        wsRef.current.close();
        setWsStatus("disconnected");
        reconnectAttempts.current += 1;
        const delay = Math.min(3000 * Math.pow(1.5, reconnectAttempts.current), 30000);
        reconnectTimer.current = setTimeout(() => connectWS(), delay);
      }
    }, 10000);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        clearTimeout(connectTimeout);
        setWsStatus("connected");
        reconnectAttempts.current = 0;
        ws.send(JSON.stringify({ action: "subscribe", symbol: currentSymbol }));
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "ticker") {
            const previousTicker = lastTickerRef.current;
            const tickerData = {
              symbol:         typeof msg.symbol === "string" ? msg.symbol : currentSymbol,
              price:          toFiniteNumber(msg.price, previousTicker?.price ?? 0),
              change_24h:     toFiniteNumber(msg.change_24h, previousTicker?.change_24h ?? 0),
              change_percent: toFiniteNumber(msg.change_percent ?? msg.change_pct, previousTicker?.change_percent ?? 0),
              volume:         toFiniteNumber(msg.volume, previousTicker?.volume ?? 0),
              high_24h:       hasFiniteNumber(msg.high_24h) ? toFiniteNumber(msg.high_24h) : previousTicker?.high_24h,
              low_24h:        hasFiniteNumber(msg.low_24h) ? toFiniteNumber(msg.low_24h) : previousTicker?.low_24h,
            };
            lastTickerRef.current = tickerData;
            setTicker(tickerData);
            reconnectAttempts.current = 0;
          }
        } catch { /* ignore */ }
      };

      ws.onerror = () => {
        clearTimeout(connectTimeout);
        setWsStatus("disconnected");
        reconnectAttempts.current += 1;
      };

      ws.onclose = () => {
        clearTimeout(connectTimeout);
        setWsStatus("disconnected");
        if (wsRef.current === ws) {
          const delay = Math.min(3000 * Math.pow(1.5, reconnectAttempts.current), 30000);
          reconnectTimer.current = setTimeout(() => connectWS(), delay);
        }
      };
    } catch (e) {
      clearTimeout(connectTimeout);
      console.warn("Failed to create WebSocket:", e);
      setWsStatus("disconnected");
      reconnectAttempts.current += 1;
      reconnectTimer.current = setTimeout(() => connectWS(), 5000);
    }
  }, [currentSymbol]);

  // Subscribe to new symbol on change
  useEffect(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "subscribe", symbol: currentSymbol }));
    }
  }, [currentSymbol]);

  useEffect(() => {
    connectWS();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        // 清理监听器以防止卸载后状态更新导致的内存泄漏和报错
        wsRef.current.onopen = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.onmessage = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connectWS]);

  // ── Ollama status ──────────────────────────────────────────────────────────
  useEffect(() => {
    fetch("/api/v1/market/ollama/status").then(r => r.ok ? r.json() : null).then(d => {
      if (d) setOllamaStatus({ ...d, checked: true });
    }).catch(() => setOllamaStatus({ online: false, checked: true }));
  }, []);

  // ── Agent Win-Rate (from backtest engine) ──────────────────────────────────
  const fetchAgentWinRates = useCallback(async (symbol: string) => {
    // 并发为所有 Agent 发起轻量回测，获取真实胜率
    const agentIds = Object.keys(AGENT_STRATEGY_MAP);

    // 先标记为 loading
    setAgents(p => p.map(a => agentIds.includes(a.id) ? { ...a, winRate: "...", winRateLoading: true } : a));

    await Promise.allSettled(
      agentIds.map(async (agentId) => {
        const cfg = AGENT_STRATEGY_MAP[agentId];
        try {
          const res = await fetch("/api/v1/strategy/backtest/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              strategy_type:   cfg.strategy_type,
              symbol:          symbol,
              interval:        cfg.interval,
              limit:           cfg.limit,
              initial_capital: 10000,
              params:          cfg.params,
            }),
          });
          if (res.ok) {
            const data = await res.json();
            const winRate = data.metrics?.win_rate;
            if (hasFiniteNumber(winRate)) {
              setAgents(p => p.map(a =>
                a.id === agentId
                  ? { ...a, winRate: `${toFiniteNumber(winRate).toFixed(1)}%`, winRateLoading: false }
                  : a
              ));
            } else {
              setAgents(p => p.map(a => a.id === agentId ? { ...a, winRate: "--", winRateLoading: false } : a));
            }
          } else {
            setAgents(p => p.map(a => a.id === agentId ? { ...a, winRate: "--", winRateLoading: false } : a));
          }
        } catch {
          setAgents(p => p.map(a => a.id === agentId ? { ...a, winRate: "--", winRateLoading: false } : a));
        }
      })
    );
  }, []);

  // 初始化 & 切换交易对时刷新胜率
  useEffect(() => {
    fetchAgentWinRates(currentSymbol);
  }, [currentSymbol, fetchAgentWinRates]);

  // ── Cooldown timer ─────────────────────────────────────────────────────────
  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now();
      const next: Record<string, number> = {};
      let any = false;
      Object.entries(cooldownTracker.current).forEach(([id, t]) => {
        const r = Math.max(0, COOLDOWN_SECONDS - Math.floor((now - t) / 1000));
        next[id] = r;
        if (r > 0) any = true;
      });
      setCooldownRemaining(any ? next : {});
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // ── Agent Analysis ─────────────────────────────────────────────────────────
  interface Agent {
    id: string;
    name: string;
    type: string;
    status: string;
    provider: string;
    action: string;
    icon: React.ComponentType<{ className?: string }>;
    logs: string;
    analyzing: boolean;
    isStreaming: boolean;
    thinkingContent: string;
    outputContent: string;
    thinkCollapsed: boolean;
    profit: string;
    winRate: string;
    winRateLoading: boolean;
    color: string;
  }

  const fetchAgentAnalysis = useCallback(async (agent: Agent, forceRefresh = false) => {
    const cacheKey = `${agent.id}-${currentSymbol}`;
    const now = Date.now();

    const lastTime = cooldownTracker.current[agent.id] || 0;
    if (!forceRefresh && (now - lastTime) / 1000 < COOLDOWN_SECONDS && lastTime > 0) {
      const r = Math.ceil(COOLDOWN_SECONDS - (now - lastTime) / 1000);
      setAgents(p => p.map(a => a.id === agent.id ? { ...a, logs: `⏳ 冷却中，${r}秒后可再次分析` } : a));
      return;
    }

    const cached = analysisCache.current[cacheKey];
    if (!forceRefresh && cached && now - cached.timestamp < 5 * 60 * 1000) {
      setAgents(p => p.map(a => a.id === agent.id ? { ...a, logs: cached.result, outputContent: cached.outputContent ?? cached.result, thinkingContent: cached.thinkingContent ?? "", analyzing: false, isStreaming: false } : a));
      return;
    }

    if (agent.provider === "ollama") {
      setAgents(p => p.map(a => a.id === agent.id ? { ...a, analyzing: true, isStreaming: true, logs: "AI 正在思考中...", thinkingContent: "", outputContent: "", thinkCollapsed: true } : a));
      try {
        const res = await fetch(`/api/v1/market/agent-analysis-stream/${agent.type}/${currentSymbol}?provider=${agent.provider}&interval=1h`);
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "", inThink = false, thinkBuf = "", outputBuf = "", tagBuf = "";

        const processChunk = (text: string) => {
          const input = tagBuf + text; tagBuf = "";
          let i = 0;
          while (i < input.length) {
            if (inThink) {
              const ci = input.indexOf("</think>", i);
              if (ci !== -1) { thinkBuf += input.slice(i, ci); inThink = false; i = ci + 8; }
              else { thinkBuf += input.slice(i); i = input.length; }
            } else {
              const oi = input.indexOf("<think>", i);
              if (oi !== -1) { outputBuf += input.slice(i, oi); inThink = true; i = oi + 7; }
              else { outputBuf += input.slice(i); i = input.length; }
            }
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n"); buf = lines.pop() ?? "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const p = JSON.parse(line.slice(6).trim());
              if (p.done) {
                cooldownTracker.current[agent.id] = Date.now();
                setCooldownRemaining(x => ({ ...x, [agent.id]: COOLDOWN_SECONDS }));
                const fo = outputBuf.trim(), ft = thinkBuf.trim();
                analysisCache.current[cacheKey] = { result: fo, outputContent: fo, thinkingContent: ft, timestamp: Date.now() };
                setAgents(x => x.map(a => a.id === agent.id ? { ...a, analyzing: false, isStreaming: false, logs: fo, outputContent: fo, thinkingContent: ft } : a));
                return;
              }
              if (p.error) { 
                setAgents(x => x.map(a => a.id === agent.id ? { ...a, analyzing: false, isStreaming: false, logs: `分析失败: ${p.error}` } : a)); 
                // 失败时清除冷却，允许立即重试
                delete cooldownTracker.current[agent.id];
                return; 
              }
              if (p.chunk) { processChunk(p.chunk); setAgents(x => x.map(a => a.id === agent.id ? { ...a, thinkingContent: thinkBuf, outputContent: outputBuf, logs: outputBuf } : a)); }
            } catch { /* ignore */ }
          }
        }
      } catch {
        setAgents(p => p.map(a => a.id === agent.id ? { ...a, analyzing: false, isStreaming: false, logs: "分析失败: 网络错误" } : a));
        // 失败时清除冷却，允许立即重试
        delete cooldownTracker.current[agent.id];
      }
      return;
    }

    setAgents(p => p.map(a => a.id === agent.id ? { ...a, analyzing: true, logs: "AI 正在思考中..." } : a));
    try {
      const res = await fetch(`/api/v1/market/agent-analysis/${agent.type}/${currentSymbol}?provider=${agent.provider}&interval=1h`);
      if (res.ok) {
        const data = await res.json();
        analysisCache.current[cacheKey] = { result: data.analysis, outputContent: data.analysis, thinkingContent: "", timestamp: Date.now() };
        cooldownTracker.current[agent.id] = Date.now();
        setCooldownRemaining(x => ({ ...x, [agent.id]: COOLDOWN_SECONDS }));
        setAgents(p => p.map(a => a.id === agent.id ? { ...a, logs: data.analysis, outputContent: data.analysis, analyzing: false } : a));
      } else {
        setAgents(p => p.map(a => a.id === agent.id ? { ...a, logs: "分析失败: 服务异常", analyzing: false } : a));
        // 失败时清除冷却，允许立即重试
        delete cooldownTracker.current[agent.id];
      }
    } catch {
      setAgents(p => p.map(a => a.id === agent.id ? { ...a, logs: "分析失败: 网络错误", analyzing: false } : a));
      // 失败时清除冷却，允许立即重试
      delete cooldownTracker.current[agent.id];
    }
  }, [currentSymbol]);

  const handleProviderChange = (agentId: string, newProvider: string) => {
    setAgents(p => p.map(a => a.id === agentId ? { ...a, provider: newProvider } : a));
    Object.keys(analysisCache.current).filter(k => k.startsWith(agentId)).forEach(k => delete analysisCache.current[k]);
  };

  const toggleAgentStatus = (agentId: string) =>
    setAgents(p => p.map(a => a.id === agentId ? { ...a, status: a.status === "运行中" ? "暂停" : "运行中" } : a));

  const toggleThink = (agentId: string) =>
    setAgents(p => p.map(a => a.id === agentId ? { ...a, thinkCollapsed: !a.thinkCollapsed } : a));

  const handleClosePosition = async (pos: Position) => {
    try {
      await fetch("/api/v1/trading/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: pos.symbol, side: "SELL", order_type: "MARKET", quantity: pos.quantity, exchange_id: currentExchange }),
      });
      fetchPositions();
      fetchBalance();
      fetchPaperOrders();
    } catch { /* ignore */ }
  };

  const handleCloseAll = async () => {
    await fetch(`/api/v1/trading/positions/close-all?exchange_id=${currentExchange}`, { method: "POST" });
    fetchPositions();
    fetchBalance();
    fetchPaperOrders();
  };

  const formatCurrency = (v: unknown) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(toFiniteNumber(v));
  const formatNumber   = (v: unknown) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(toFiniteNumber(v));
  const formatCompactNumber = (v: unknown) => new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(toFiniteNumber(v));
  const formatPercent = (v: unknown) => `${(toFiniteNumber(v) * 100).toFixed(1)}%`;
  const formatDateTime = (value?: string | null) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };
  const formatSignalLabel = (signal?: string) => {
    const map: Record<string, string> = { BUY: "买入", SELL: "卖出", WAIT: "观望", HOLD: "持有" };
    const normalized = signal?.toUpperCase();
    return normalized ? (map[normalized] || signal || "—") : "—";
  };
  const signalBadgeClass = (signal?: string) => {
    const normalized = signal?.toUpperCase();
    if (normalized === "BUY") return "border-emerald-400/25 bg-emerald-400/10 text-emerald-200";
    if (normalized === "SELL") return "border-red-400/25 bg-red-400/10 text-red-200";
    return "border-slate-500/35 bg-slate-800/60 text-slate-300";
  };
  const formatSignedScore = (value: unknown) => {
    if (!hasFiniteNumber(value)) return "—";
    const numeric = toFiniteNumber(value);
    return `${numeric > 0 ? "+" : ""}${numeric.toFixed(2)}`;
  };
  const formatVwapMethod = (method?: string) => {
    if (method === "quote_volume_exact") return "精确 VWAP（quote_volume / volume）";
    if (method === "typical_price_proxy") return "估算 VWAP（OHLCV 代理）";
    return method || "未标注";
  };
  const formatDirectionStrength = (signal: ResearchSnapshotSignal) => {
    const normalized = signal.signal_type?.toUpperCase();
    if (normalized === "WAIT" || normalized === "HOLD" || signal.is_triggered === false) {
      return "未触发买卖";
    }
    const value = hasFiniteNumber(signal.direction_strength) ? signal.direction_strength : signal.strength;
    return hasFiniteNumber(value) ? formatPercent(value) : "—";
  };
  const formatRoleOpinion = (opinion?: string) => {
    const normalized = opinion?.toLowerCase();
    if (normalized === "buy" || normalized === "bullish" || normalized === "long") return "偏多";
    if (normalized === "sell" || normalized === "bearish" || normalized === "short") return "偏空";
    if (normalized === "hold" || normalized === "wait" || normalized === "neutral") return "中性";
    return opinion || "未标注";
  };
  const formatOrderSide = (side: string) => {
    if (side === "BUY") return "买入";
    if (side === "SELL") return "卖出";
    return side || "—";
  };
  const formatOrderStatus = (status: string) => {
    const statusMap: Record<string, string> = {
      FILLED: "已成交",
      OPEN: "挂单中",
      CANCELED: "已撤单",
      REJECTED: "已拒绝",
      FAILED: "失败",
    };
    return statusMap[status] || status || "—";
  };
  const researchBarSummary = researchSnapshot?.bar_panel?.summary;
  const researchBarRows = researchSnapshot?.bar_panel?.rows || [];
  const researchFactorGroups = [
    { key: "technical", label: "技术因子", items: researchSnapshot?.factor_panel?.groups?.technical || [], hint: "由 L5 因子管道基于标准化 K 线计算" },
    { key: "sentiment", label: "情绪因子", items: researchSnapshot?.factor_panel?.groups?.sentiment || [], hint: "由新闻情绪和资产映射加工" },
    { key: "macro", label: "宏观因子", items: researchSnapshot?.factor_panel?.groups?.macro || [], hint: "由 OpenBB/FRED/OECD 宏观事件进入 L5" },
  ];
  const researchSignals = researchSnapshot?.signal_panel || researchSnapshot?.signals || [];
  const researchNews = researchSnapshot?.news_panel || [];
  const researchAgentSections = researchSnapshot?.tradingagents_panel?.sections || [];

  return (
    <div className={`min-h-screen ${
      isPaperTradingPage
        ? "bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.12),transparent_34%),radial-gradient(circle_at_top_right,rgba(245,158,11,0.10),transparent_28%),linear-gradient(180deg,#07110f_0%,#09090b_42%,#030712_100%)]"
        : "bg-background"
    }`}>
      <AppTopNav
        activeSection={isPaperTradingPage ? "paper" : "overview"}
        rightSlot={
          <>
            {exchanges.length > 1 ? (
              <Select value={currentExchange} onValueChange={setCurrentExchange}>
                <SelectTrigger className="w-[150px] bg-secondary border-border text-foreground h-8 text-sm">
                  <SelectValue placeholder="标记价格" />
                </SelectTrigger>
                <SelectContent className="bg-secondary border-border">
                  {exchanges.map(ex => (
                    <SelectItem key={ex.value} value={ex.value} className="text-foreground focus:bg-secondary focus:text-foreground cursor-pointer">
                      {ex.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}

            {isPaperTradingPage ? (
              <Badge variant="outline" className="hidden border-emerald-500/25 bg-emerald-500/10 text-emerald-200 sm:inline-flex">
                本地模拟盘
              </Badge>
            ) : (
              <>
                <Select key="symbol-select" value={currentSymbol} onValueChange={handleSymbolChange}>
                  <SelectTrigger className="w-[140px] bg-secondary border-border text-foreground h-8 text-sm">
                    <SelectValue placeholder="选择币种" />
                  </SelectTrigger>
                  <SelectContent className="bg-secondary border-border">
                    {symbols.map(s => (
                      <SelectItem key={s.value} value={s.value} className="text-foreground focus:bg-secondary focus:text-foreground cursor-pointer">{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Badge variant="outline" className={
                  wsStatus === "connected"    ? "bg-green-500/10 text-green-400 border-green-500/20" :
                  wsStatus === "connecting"   ? "bg-yellow-500/10 text-yellow-400 border-yellow-500/20" :
                                                "bg-red-500/10 text-red-400 border-red-500/20"
                }>
                  <span className={`w-2 h-2 rounded-full mr-2 inline-block ${wsStatus === "connected" ? "bg-green-500 animate-pulse" : wsStatus === "connecting" ? "bg-yellow-500 animate-pulse" : "bg-red-500"}`} />
                  {wsStatus === "connected" ? "实时" : wsStatus === "connecting" ? "连接中" : `断线${reconnectAttempts.current > 0 ? ` (重连${reconnectAttempts.current})` : ""}`}
                </Badge>
              </>
            )}
          </>
        }
      />

      {/* ── Main ── */}
      <main className="container mx-auto px-4 py-6">
        {initialDashboardTab !== "positions" && (
        <section className="mb-6 overflow-hidden rounded-3xl border border-border/70 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-5 shadow-2xl shadow-black/20">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge className="bg-cyan-500/15 text-cyan-200 border border-cyan-500/20">加密优先</Badge>
                <Badge variant="outline" className="border-emerald-500/25 bg-emerald-500/10 text-emerald-300">OpenBB + CCXT</Badge>
                <Badge variant="outline" className="border-border bg-background/40 text-muted-foreground">Ollama 本地智能体</Badge>
              </div>
              <h2 className="text-2xl font-bold tracking-tight text-foreground md:text-3xl">
                {pageTitle}
              </h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {pageDescription}
              </p>
            </div>
            <div className="grid min-w-[280px] grid-cols-2 gap-3 text-sm">
              <div className="rounded-2xl border border-border/70 bg-background/35 p-3">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">K 线口径</p>
                <p className="mt-1 font-semibold text-foreground">行情网关</p>
                <p className="mt-1 text-[10px] text-muted-foreground">图表标签显示实际来源；ClickHouse 只是缓存</p>
              </div>
              <div className="rounded-2xl border border-border/70 bg-background/35 p-3">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">模拟盘口径</p>
                <p className="mt-1 font-semibold text-foreground">{currentExchangeInfo.label} 标记价格</p>
                <p className="mt-1 text-[10px] text-muted-foreground">只影响虚拟成交参考，不会真实下单</p>
              </div>
            </div>
          </div>
        </section>
        )}

        <Tabs defaultValue={initialDashboardTab} className="space-y-6">
          <TabsContent value="overview" className="mt-0 space-y-6">

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Card className="bg-card border-border hover:border-blue-500/30 transition-all">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">{currentSymbol} 价格</p>
                  <p className="text-2xl font-bold text-foreground mt-1">
                    {ticker ? formatCurrency(ticker.price) : "—"}
                  </p>
                </div>
                <div className="w-12 h-12 bg-blue-500/10 rounded-xl flex items-center justify-center border border-blue-500/20">
                  <DollarSign className="w-6 h-6 text-blue-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border hover:border-green-500/30 transition-all">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">24h 涨跌幅</p>
                  <p className={`text-2xl font-bold mt-1 ${(ticker?.change_percent ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {ticker ? `${toFiniteNumber(ticker.change_percent) >= 0 ? "+" : ""}${toFiniteNumber(ticker.change_percent).toFixed(2)}%` : "—"}
                  </p>
                </div>
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center border ${(ticker?.change_percent ?? 0) >= 0 ? "bg-green-500/10 border-green-500/20" : "bg-red-500/10 border-red-500/20"}`}>
                  {(ticker?.change_percent ?? 0) >= 0
                    ? <TrendingUp className="w-6 h-6 text-green-400" />
                    : <TrendingDown className="w-6 h-6 text-red-400" />}
                </div>
              </div>
              <p className={`text-xs mt-2 ${(ticker?.change_24h ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                {ticker ? `${toFiniteNumber(ticker.change_24h) >= 0 ? "+" : ""}${formatNumber(ticker.change_24h)}` : ""}
              </p>
            </CardContent>
          </Card>

          <Card className="bg-card border-border hover:border-purple-500/30 transition-all">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">24h 成交量</p>
                  <p className="text-2xl font-bold text-foreground mt-1">
                    {ticker ? formatNumber(ticker.volume) : "—"}
                  </p>
                </div>
                <div className="w-12 h-12 bg-purple-500/10 rounded-xl flex items-center justify-center border border-purple-500/20">
                  <BarChart2 className="w-6 h-6 text-purple-400" />
                </div>
              </div>
              <p className="text-xs text-muted-foreground mt-2">USDT</p>
            </CardContent>
          </Card>

          <Card className="bg-card border-border hover:border-orange-500/30 transition-all">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">K 线周期</p>
                  <p className="text-2xl font-bold text-foreground mt-1">
                    {intervals.find(i => i.value === currentInterval)?.label || currentInterval}
                  </p>
                </div>
                <div className="w-12 h-12 bg-orange-500/10 rounded-xl flex items-center justify-center border border-orange-500/20">
                  <BarChart3 className="w-6 h-6 text-orange-400" />
                </div>
              </div>
              <p className="text-xs text-muted-foreground mt-2">图表右上角可切换</p>
            </CardContent>
          </Card>
        </div>

        {/* Real source comparison */}
        <Card className="bg-card border-border mb-6">
            <CardContent className="p-4 flex flex-wrap items-center justify-between gap-4 text-sm">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground font-bold uppercase">真实来源对照 ({currentSymbol})</span>
                {loadingComparison && <RefreshCw className="w-3 h-3 animate-spin text-muted-foreground" />}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  K 线来源看图表右上角标签；模拟盘标记价格只影响模拟下单、持仓盈亏、风控和交易所实时报价对照。
                </p>
              </div>

              {comparisonData ? (
                <div className="flex items-center gap-6">
                  <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
                    <span className="text-muted-foreground text-xs uppercase">行情网关</span>
                    <span className="font-mono text-foreground/90 font-bold">
                      {hasFiniteNumber(comparisonData.gateway_price) ? `$${formatNumber(comparisonData.gateway_price)}` : "—"}
                    </span>
                  </div>
                  <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
                    <span className="text-muted-foreground text-xs uppercase">{comparisonData.exchange_source}</span>
                    <span className={`font-mono font-bold ${comparisonData.status === "ok" ? "text-foreground/90" : "text-amber-300"}`}>
                      {hasFiniteNumber(comparisonData.exchange_price) ? `$${formatNumber(comparisonData.exchange_price)}` : loadingComparison ? "请求中..." : "暂不可用"}
                    </span>
                  </div>
                  <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2 pl-4 border-l border-border">
                    <span className="text-muted-foreground text-xs uppercase">价差</span>
                    <span className="font-mono font-bold text-foreground/90">
                      {hasFiniteNumber(comparisonData.price_diff) ? formatNumber(comparisonData.price_diff) : "—"}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {hasFiniteNumber(comparisonData.price_diff_percent) ? `(${toFiniteNumber(comparisonData.price_diff_percent).toFixed(4)}%)` : comparisonData.error || "等待真实报价"}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="text-muted-foreground text-xs">暂无数据</div>
              )}
            </CardContent>
          </Card>

        {/* Chart */}
        <div className="mb-6 relative">
          <div className="absolute top-4 right-4 z-10">
            <Select key="interval-select" value={currentInterval} onValueChange={setCurrentInterval}>
              <SelectTrigger className="w-24 bg-secondary border-border text-foreground">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-secondary border-border">
                {intervals.map(i => (
                  <SelectItem key={i.value} value={i.value} className="text-foreground focus:bg-secondary focus:text-foreground cursor-pointer">{i.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <TradingViewChart symbol={currentSymbol} interval={currentInterval} />
        </div>

        {/* Research Snapshot */}
        <Card className="mb-6 overflow-hidden border-cyan-500/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_35%),linear-gradient(135deg,rgba(15,23,42,0.98),rgba(2,6,23,0.98))]">
          <CardHeader className="pb-3">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge className="border border-cyan-400/25 bg-cyan-400/15 text-cyan-100">研究快照</Badge>
                  <Badge variant="outline" className="border-slate-500/40 bg-slate-900/60 text-slate-300">
                    {researchSnapshot?.mode === "point_in_time" ? "按历史时间回看" : "当前最新状态"}
                  </Badge>
                  {researchLoading && (
                    <Badge variant="outline" className="border-cyan-400/25 bg-cyan-400/10 text-cyan-200">
                      <RefreshCw className="mr-1 h-3 w-3 animate-spin" /> 正在整理上下文
                    </Badge>
                  )}
                </div>
                <CardTitle className="text-lg text-white">TradingAgents 使用的同一时间点材料</CardTitle>
                <p className="mt-2 max-w-3xl text-xs leading-5 text-slate-400">
                  这里不是诊断页，而是研究工作台：系统把 K 线、因子、L5 信号、新闻、宏观和最近一次决策按同一个 as_of_time 对齐，避免回看时偷看到未来数据。
                </p>
              </div>
              <div className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-white/[0.04] p-3 sm:flex-row sm:items-end">
                <div>
                  <label className="mb-1 block text-[11px] text-slate-400">回看时间，可留空看当前</label>
                  <input
                    ref={researchAsOfInputRef}
                    type="text"
                    value={researchAsOf}
                    onChange={(event) => setResearchAsOf(event.target.value)}
                    placeholder="例如 2026-05-28 09:30"
                    className="h-9 w-[210px] rounded-lg border border-white/10 bg-slate-950/70 px-3 text-xs text-slate-100 outline-none focus:border-cyan-400/50"
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 border-cyan-400/30 bg-cyan-400/10 text-cyan-100 hover:bg-cyan-400/15"
                    onClick={() => {
                      const nextAsOf = researchAsOfInputRef.current?.value || researchAsOf;
                      const normalizedAsOf = normalizeResearchAsOfInput(nextAsOf);
                      if (normalizedAsOf === null) {
                        setResearchError("时间格式无法识别，请用 2026-05-28 09:30 这类格式。");
                        return;
                      }
                      setResearchAsOf(nextAsOf);
                      setAppliedResearchAsOf(normalizedAsOf);
                    }}
                    disabled={researchLoading}
                  >
                    按该时间回看
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-9 text-slate-300 hover:bg-white/10 hover:text-white"
                    onClick={() => { setResearchAsOf(""); setAppliedResearchAsOf(""); }}
                    disabled={researchLoading}
                  >
                    查看当前
                  </Button>
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {researchError ? (
              <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
                研究快照暂不可用：{researchError}
              </div>
            ) : researchLoading && !researchSnapshot ? (
              <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-5 text-sm text-cyan-100">
                <div className="flex items-center gap-2 font-semibold">
                  <RefreshCw className="h-4 w-4 animate-spin" /> 正在按同一时间点整理研究材料
                </div>
                <p className="mt-2 text-xs leading-5 text-cyan-100/75">
                  这个过程会读取 K 线、因子、信号、新闻、宏观和历史决策，通常需要几秒到十几秒；加载完成前不显示 0，避免误会成没有数据。
                </p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
                  {[
                    { label: "行情 Bar", value: researchSnapshot?.counts?.bars, hint: `展示 ${researchSnapshot?.counts?.bars_displayed ?? "—"} 根` },
                    { label: "因子", value: researchSnapshot?.counts?.factors, hint: `技术 ${researchSnapshot?.counts?.technical_factors ?? 0} / 情绪 ${researchSnapshot?.counts?.sentiment_factors ?? 0} / 宏观 ${researchSnapshot?.counts?.macro_factors ?? 0}` },
                    { label: "信号", value: researchSnapshot?.counts?.signals, hint: `展示 ${researchSnapshot?.counts?.signals_displayed ?? "—"} 条触发记录` },
                    { label: "新闻", value: researchSnapshot?.counts?.news, hint: "标准化 NewsEvent" },
                    { label: "宏观事件", value: researchSnapshot?.counts?.macro, hint: "FRED/OECD 标签" },
                    { label: "Agent 角色", value: researchSnapshot?.counts?.tradingagents_roles, hint: "TradingAgentsGraph" },
                  ].map((item) => (
                    <div key={item.label} className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
                      <p className="text-[11px] text-slate-400">{item.label}</p>
                      <p className="mt-1 text-2xl font-black text-white">{item.value ?? "—"}</p>
                      <p className="mt-1 text-[10px] text-slate-500">{item.hint}</p>
                    </div>
                  ))}
                </div>

                <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.06] p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <p className="text-sm font-bold text-cyan-100">全局时间轴 / 回看模式</p>
                      <p className="mt-1 text-xs leading-5 text-cyan-100/75">
                        当前页面所有面板都按同一个 as_of_time 截止：行情、因子、信号、新闻和 Agent 决策不会各看各的时间。
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2 text-[11px]">
                      <Badge variant="outline" className="border-cyan-400/30 bg-slate-950/40 text-cyan-100">
                        as_of_time：{formatDateTime(researchSnapshot?.global_time_axis?.as_of_time || researchSnapshot?.as_of_time)}
                      </Badge>
                      <Badge variant="outline" className="border-cyan-400/30 bg-slate-950/40 text-cyan-100">
                        {researchSnapshot?.global_time_axis?.alignment_rule || researchSnapshot?.lineage?.rule || "available_time <= as_of_time"}
                      </Badge>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.05fr_0.95fr]">
                  <div className="rounded-2xl border border-white/10 bg-slate-950/45 p-4">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-bold text-white">行情面板</p>
                        <p className="mt-1 text-[11px] text-slate-400">
                          标的 {researchSnapshot?.symbol || currentSymbol} · 周期 {researchSnapshot?.interval || currentInterval} · 标准化 Bar 数据
                        </p>
                      </div>
                      <Badge variant="outline" className="border-cyan-400/25 bg-cyan-400/10 text-cyan-200">
                        volume + VWAP
                      </Badge>
                    </div>

                    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                      {[
                        { label: "收盘价", value: hasFiniteNumber(researchBarSummary?.close) ? formatCurrency(researchBarSummary?.close) : "—" },
                        { label: "成交量", value: hasFiniteNumber(researchBarSummary?.volume) ? formatCompactNumber(researchBarSummary?.volume) : "—" },
                        { label: "当前 Bar VWAP", value: hasFiniteNumber(researchBarSummary?.vwap) ? formatCurrency(researchBarSummary?.vwap) : "—" },
                        { label: "48根窗口 VWAP", value: hasFiniteNumber(researchBarSummary?.window_vwap) ? formatCurrency(researchBarSummary?.window_vwap) : "—" },
                      ].map((item) => (
                        <div key={item.label} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                          <p className="text-[10px] text-slate-500">{item.label}</p>
                          <p className="mt-1 font-mono text-sm font-bold text-slate-100">{item.value}</p>
                        </div>
                      ))}
                    </div>

                    <p className="mt-3 text-[11px] leading-5 text-slate-500">
                      VWAP 计算方式：{formatVwapMethod(researchBarSummary?.vwap_method)}。{researchSnapshot?.bar_panel?.note}
                    </p>

                    <div className="mt-4 overflow-hidden rounded-xl border border-white/10">
                      <div className="grid grid-cols-4 bg-white/[0.04] px-3 py-2 text-[10px] font-semibold text-slate-500">
                        <span>时间</span>
                        <span className="text-right">收盘价</span>
                        <span className="text-right">成交量</span>
                        <span className="text-right">Bar VWAP</span>
                      </div>
                      {researchBarRows.slice(-6).map((bar) => (
                        <div key={bar.event_time} className="grid grid-cols-4 border-t border-white/10 px-3 py-2 text-[11px] text-slate-300">
                          <span>{formatDateTime(bar.event_time)}</span>
                          <span className="text-right font-mono">{hasFiniteNumber(bar.close) ? formatCurrency(bar.close) : "—"}</span>
                          <span className="text-right font-mono">{hasFiniteNumber(bar.volume) ? formatCompactNumber(bar.volume) : "—"}</span>
                          <span className="text-right font-mono">{hasFiniteNumber(bar.vwap) ? formatCurrency(bar.vwap) : "—"}</span>
                        </div>
                      ))}
                      {researchBarRows.length === 0 && (
                        <div className="px-3 py-4 text-xs text-slate-500">这个时间点没有可见的标准化 Bar。</div>
                      )}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-slate-950/45 p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <div>
                        <p className="text-sm font-bold text-white">信号面板</p>
                        <p className="mt-1 text-[11px] text-slate-400">
                          L5 策略输出。观望代表没有明确买入/卖出触发，所以方向强度显示为“未触发买卖”。
                        </p>
                      </div>
                      <Badge variant="outline" className="border-slate-500/35 bg-slate-800/60 text-slate-300">
                        signal_events
                      </Badge>
                    </div>
                    <div className="space-y-2">
                      {researchSignals.slice(0, 6).map((signal) => (
                        <div key={signal.id ?? `${signal.source_strategy}-${signal.event_time}`} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-xs font-semibold text-slate-200" title={signal.source_strategy || undefined}>
                                {formatStrategyDisplayName(signal.source_strategy)}
                              </p>
                              <p className="mt-1 text-[10px] text-slate-500">
                                {formatDateTime(signal.timestamp || signal.event_time)} · {signal.provider || signal.data_source || "L5"}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className={signalBadgeClass(signal.signal_type)}>
                                {formatSignalLabel(signal.signal_type)}
                              </Badge>
                              <span className="text-[11px] text-slate-400">
                                方向强度 {formatDirectionStrength(signal)}
                              </span>
                            </div>
                          </div>
                          <p className="mt-2 text-xs leading-5 text-slate-400">{signal.trigger_condition || "暂无触发条件说明。"}</p>
                          <p className="mt-1 text-[10px] text-slate-500">
                            策略置信度 {hasFiniteNumber(signal.confidence) ? formatPercent(signal.confidence) : "—"}；置信度是策略对当前判断的把握，不等于买卖强度。
                          </p>
                        </div>
                      ))}
                      {researchSignals.length === 0 && (
                        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-xs text-slate-500">
                          这个时间点之前没有可见的 L5 信号。
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.95fr_1.05fr]">
                  <div className="rounded-2xl border border-white/10 bg-slate-950/45 p-4">
                    <div className="mb-3">
                      <p className="text-sm font-bold text-white">因子面板</p>
                      <p className="mt-1 text-[11px] text-slate-400">
                        技术因子、情绪因子和宏观事件标签都按同一 as_of_time 对齐。
                      </p>
                    </div>
                    <div className="space-y-3">
                      {researchFactorGroups.map((group) => (
                        <div key={group.key} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                          <div className="mb-2 flex items-center justify-between gap-2">
                            <div>
                              <p className="text-xs font-semibold text-slate-200">{group.label}</p>
                              <p className="mt-1 text-[10px] text-slate-500">{group.hint}</p>
                            </div>
                            <Badge variant="outline" className="border-slate-500/35 bg-slate-900/50 text-slate-300">
                              {group.items.length} 个
                            </Badge>
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            {group.items.slice(0, 6).map((factor) => {
                              const factorLabel = formatFactorDisplayName(factor.name, factorDefinitionMap);
                              return (
                                <div key={`${group.key}-${factor.name}`} className="rounded-lg border border-white/10 bg-slate-950/45 px-2 py-1.5">
                                  <p className="truncate text-[10px] text-slate-400" title={`${factorLabel} · 原始字段：${factor.name}`}>
                                    {factorLabel}
                                  </p>
                                  <p className="truncate font-mono text-xs text-slate-200">
                                    {hasFiniteNumber(factor.value) ? formatNumber(factor.value) : factor.value ?? "—"}
                                  </p>
                                </div>
                              );
                            })}
                          </div>
                          {group.items.length === 0 && (
                            <p className="text-xs text-slate-500">当前快照没有该类因子。</p>
                          )}
                        </div>
                      ))}
                      {(researchSnapshot?.factor_panel?.macro_event_tags || []).length > 0 && (
                        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                          <p className="mb-2 text-xs font-semibold text-slate-200">宏观事件标签</p>
                          <div className="flex flex-wrap gap-2">
                            {(researchSnapshot?.factor_panel?.macro_event_tags || []).slice(0, 8).map((tag) => (
                              <Badge key={`${tag.label}-${tag.event_time}`} variant="outline" className="border-amber-400/25 bg-amber-400/10 text-amber-100">
                                {tag.label}: {hasFiniteNumber(tag.value) ? formatNumber(tag.value) : tag.value ?? "—"}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-slate-950/45 p-4">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-bold text-white">TradingAgents 分析面板</p>
                        <p className="mt-1 text-[11px] text-slate-400">
                          展示最新一轮多角色分析输入输出，默认决策引擎为 TradingAgentsGraph QuantAgent 适配版。
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {researchSnapshot?.tradingagents_panel?.audit_url && (
                          <Link href={researchSnapshot.tradingagents_panel.audit_url} className="text-[11px] text-cyan-300 hover:text-cyan-200">
                            查看审计
                          </Link>
                        )}
                        <Link href="/decisions" className="text-[11px] text-cyan-300 hover:text-cyan-200">
                          决策中心
                        </Link>
                      </div>
                    </div>
                    {researchSnapshot?.tradingagents_panel ? (
                      <div className="space-y-3">
                        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="outline" className={signalBadgeClass(researchSnapshot.tradingagents_panel.final_signal)}>
                              {formatSignalLabel(researchSnapshot.tradingagents_panel.final_signal)}
                            </Badge>
                            <span className="text-xs text-slate-400">置信度 {formatPercent(researchSnapshot.tradingagents_panel.confidence)}</span>
                            <span className="text-xs text-slate-500">角色 {researchSnapshot.tradingagents_panel.role_count ?? 0} 个</span>
                            {researchSnapshot.tradingagents_panel.risk_veto && (
                              <Badge variant="outline" className="border-amber-400/25 bg-amber-400/10 text-amber-200">风控否决</Badge>
                            )}
                          </div>
                          <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-300">
                            {researchSnapshot.tradingagents_panel.summary || "这条历史决策没有写入摘要。"}
                          </p>
                          <p className="mt-1 text-[10px] text-slate-500">
                            {researchSnapshot.tradingagents_panel.engine} · {formatDateTime(researchSnapshot.tradingagents_panel.decision_time)}
                          </p>
                        </div>

                        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                          {researchAgentSections.map((section) => {
                            const firstRole = section.items?.[0];
                            return (
                              <div key={section.key} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                                <div className="mb-2 flex items-center justify-between gap-2">
                                  <p className="text-xs font-semibold text-slate-200">{section.title}</p>
                                  <Badge variant="outline" className="border-slate-500/35 bg-slate-900/50 text-slate-300">
                                    {section.items?.length || 0}
                                  </Badge>
                                </div>
                                {firstRole ? (
                                  <>
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="truncate text-[11px] text-slate-400" title={firstRole.label}>{firstRole.label}</span>
                                      <span className="text-[10px] text-slate-500">{formatRoleOpinion(firstRole.opinion)}</span>
                                    </div>
                                    <p className="mt-2 line-clamp-4 text-xs leading-5 text-slate-300">
                                      {firstRole.summary || firstRole.reasoning || "该角色没有写入文本输出。"}
                                    </p>
                                    <p className="mt-2 text-[10px] text-slate-500">
                                      数据链路：{firstRole.data_source_chain || "AnalysisContext / OpenBB / CCXT / ClickHouse / L5"}
                                    </p>
                                  </>
                                ) : (
                                  <p className="text-xs leading-5 text-slate-500">本次决策没有单独写入该角色输出。</p>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-xs text-slate-400">
                        当前时间点之前还没有 TradingAgents 决策记录。可以先在“决策中心”手动运行一次，再回到这里回看。
                      </div>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.05fr_0.95fr]">
                  <div className="rounded-2xl border border-white/10 bg-slate-950/45 p-4">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-bold text-white">新闻面板</p>
                        <p className="mt-1 text-[11px] text-slate-400">标准化 NewsEvent 列表，含情绪评分和资产映射。</p>
                      </div>
                      <Badge variant="outline" className="border-cyan-400/25 bg-cyan-400/10 text-cyan-200">OpenBB/yfinance → DuckDB</Badge>
                    </div>
                    <div className="space-y-2">
                      {researchNews.slice(0, 5).map((item) => (
                        <div key={`${item.title}-${item.published_at}`} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <p className="line-clamp-2 text-xs font-semibold text-slate-200">{item.title || "未命名新闻"}</p>
                              <p className="mt-1 text-[10px] text-slate-500">
                                {item.source || item.provider || "未知来源"} · {formatDateTime(item.published_at)}
                              </p>
                            </div>
                            <Badge variant="outline" className="border-slate-500/35 bg-slate-900/50 text-slate-300">
                              情绪 {formatSignedScore(item.sentiment_score)}
                            </Badge>
                          </div>
                          <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-400">{item.summary || "暂无摘要。"}</p>
                          <div className="mt-2 flex flex-wrap gap-1">
                            {(item.asset_mappings || []).slice(0, 6).map((asset) => (
                              <span key={asset} className="rounded-full border border-white/10 bg-slate-950/50 px-2 py-0.5 text-[10px] text-slate-400">
                                {asset}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                      {researchNews.length === 0 && (
                        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-xs text-slate-500">
                          这个时间点之前没有可见的标准化新闻。
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-slate-950/45 p-4">
                    <p className="text-sm font-bold text-white">来源与一致性说明</p>
                    <div className="mt-3 space-y-2 text-xs leading-5 text-slate-400">
                      <p>K 线：页面读取的是标准化后的 Bar；本地 ClickHouse 是缓存/存储层，不是原始来源。上游链路为 MarketDataGateway 调 OpenBB/yfinance，必要时可降级到 CCXT/OKX。</p>
                      <p>因子与信号：由 L5 管道从 K 线、新闻、宏观上下文计算并写入 factor_snapshots / signal_events，面板数字直接来自后端研究快照。</p>
                      <p>新闻与宏观：新闻经 OpenBB/yfinance 标准化为 NewsEvent；宏观经 OpenBB/FRED/OECD 标准化为宏观事件，再参与因子和 Agent 上下文。</p>
                      <p>回看模式：输入任意历史时间后，后端统一使用 available_time ≤ as_of_time，避免研究页面看到未来数据。</p>
                    </div>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Trending Coins */}
        <div className="mb-6 rounded-2xl border border-border/70 bg-card/70 p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="flex items-center gap-2 text-sm font-bold text-foreground">
                <TrendingUp className="w-4 h-4 text-cyan-400" /> 热门币种（CoinGecko）
              </h3>
              <p className="mt-1 text-[11px] text-muted-foreground">
                来源：CoinGecko Trending API；这是热门搜索/趋势列表，不是 OpenBB、CCXT 或 K 线来源，也不代表交易建议。
              </p>
            </div>
            <Badge variant="outline" className="border-cyan-500/20 bg-cyan-500/10 text-cyan-300">
              coingecko:trending
            </Badge>
          </div>
          {trendingStatus === "loading" ? (
            <div className="flex items-center gap-2 rounded-xl border border-border/50 bg-secondary/30 p-3 text-xs text-muted-foreground">
              <RefreshCw className="h-3.5 w-3.5 animate-spin" /> 正在获取 CoinGecko 热门币种...
            </div>
          ) : trendingCoins.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
              {trendingCoins.slice(0, 4).map((coin, idx) => (
                <div key={coin.item.id || idx} className="flex items-center gap-3 p-3 bg-card/50 rounded-xl border border-border/50 hover:border-border transition-all">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={coin.item.thumb} alt={coin.item.name} width={32} height={32} className="rounded-full" loading="lazy" />
                  <div>
                    <p className="text-sm font-bold text-foreground/90">{coin.item.name}</p>
                    <p className="text-xs text-muted-foreground">#{coin.item.market_cap_rank} · {coin.item.symbol}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-200">
              CoinGecko Trending 暂不可用，页面不会用 BTC/ETH/SOL 这类假数据补位。
            </div>
          )}
        </div>

        {/* Macro & News */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
          <Card className="lg:col-span-1 bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Globe className="w-4 h-4 text-blue-400" /> 宏观指标
                <Badge className="text-[10px]">OpenBB/FRED/OECD</Badge>
                {pipelineStats && (
                  <Badge variant="outline" className={`text-[9px] ${pipelineStats.running ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-slate-500/10 text-muted-foreground border-muted-foreground/20"}`}>
                    {pipelineStats.macro_stored}条
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {[
                { k: "fed_funds_rate", l: "联邦基金利率", u: "%" },
                { k: "treasury_10y", l: "10年国债", u: "%" },
                { k: "inflation_expect", l: "通胀预期", u: "%" },
                { k: "cpi", l: "CPI", u: "%" },
                { k: "unemployment", l: "失业率", u: "%" },
              ].map(({ k, l, u }) => {
                const d = macro[k];
                const v = d?.value;
                return (
                  <div key={k} className="flex justify-between py-1.5 border-b border-border/50 last:border-0">
                    <span className="text-xs text-muted-foreground">{l}</span>
                    <span className="text-xs font-mono font-bold">
                      {hasFiniteNumber(v) ? `${toFiniteNumber(v).toFixed(2)}${u}` : <span className="text-muted-foreground/50">—</span>}
                    </span>
                  </div>
                );
              })}
            </CardContent>
          </Card>
          <Card className="lg:col-span-2 bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Newspaper className="w-4 h-4 text-amber-400" /> 加密新闻
                <Badge variant="outline" className="border-amber-500/20 bg-amber-500/10 text-amber-300 text-[9px]">
                  OpenBB/yfinance + DuckDB
                </Badge>
                {pipelineStats && (
                  <Badge variant="outline" className="text-[9px] bg-amber-500/10 text-amber-400 border-amber-500/20">
                    {pipelineStats.news_stored}条
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-1.5 max-h-[240px] overflow-y-auto">
                {headlines.length > 0 ? headlines.map((h, i) => (
                  <a key={i} href={h.url} target="_blank" rel="noopener noreferrer"
                    className="flex items-start gap-2 p-2 rounded hover:bg-secondary/50 transition-all group">
                    <ExternalLink className="w-3 h-3 text-muted-foreground shrink-0 mt-0.5 group-hover:text-foreground" />
                    <div className="min-w-0">
                      <div className="text-xs text-foreground/80 group-hover:text-foreground leading-snug truncate">{h.title}</div>
                      <div className="flex gap-2 mt-0.5">
                        <span className="text-[10px] text-muted-foreground">{h.source}</span>
                        <span className="text-[10px] text-muted-foreground/50">
                          {h.date ? new Date(h.date).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}
                        </span>
                      </div>
                    </div>
                  </a>
                )) : (
                  <div className="rounded-xl border border-border/60 bg-secondary/20 p-4 text-xs text-muted-foreground">
                    暂无新闻记录。系统不会用示例新闻占位；可在数据源页面查看新闻管道状态。
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
          </TabsContent>

          <TabsContent value="diagnostics" className="mt-0 space-y-6">
            <Prd104StatusPanel />
            <PrdV1FlowPanel />

        {/* Hummingbot Status Card */}
        <Card className="bg-gradient-to-br bg-card border-cyan-700/30 mb-6">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-foreground flex items-center gap-2 text-base">
                <div className="w-8 h-8 bg-cyan-500/10 rounded-lg flex items-center justify-center border border-cyan-500/20">
                  <Server className="w-4 h-4 text-cyan-400" />
                </div>
                Hummingbot 状态
              </CardTitle>
              <div className="flex items-center gap-2">
                <Badge
                  variant="outline"
                  className={hummingbotStatus?.connected ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-slate-500/10 text-muted-foreground border-muted-foreground/20"}
                >
                  {hummingbotStatus?.connected ? (
                    <><CheckCircle className="w-3 h-3 mr-1" /> 已连接</>
                  ) : (
                    <><WifiOff className="w-3 h-3 mr-1" /> 未连接</>
                  )}
                </Badge>
                <Button variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground hover:text-foreground" onClick={fetchHummingbotStatus}>
                  <RefreshCw className="w-3 h-3 mr-1" /> 刷新
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {/* API Connection */}
              <div className="p-3 bg-secondary/50 rounded-lg border border-border/50">
                <p className="text-[10px] text-muted-foreground uppercase mb-1">API 状态</p>
                <p className={`text-sm font-semibold ${hummingbotStatus?.connected ? "text-green-400" : "text-muted-foreground"}`}>
                  {hummingbotStatus?.connected ? "已连接" : "未连接"}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5 truncate" title="http://localhost:8000">
                  {hummingbotStatus?.version || "—"}
                </p>
              </div>

              {/* Docker Status */}
              <div className="p-3 bg-secondary/50 rounded-lg border border-border/50">
                <p className="text-[10px] text-muted-foreground uppercase mb-1">Docker 容器</p>
                <p className={`text-sm font-semibold ${hummingbotDocker?.connected ? "text-green-400" : "text-muted-foreground"}`}>
                  {hummingbotDocker?.connected ? "可达" : "不可达"}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5">{hummingbotDocker?.containerCount ?? 0} 个活跃</p>
              </div>

              {/* Connectors */}
              <div className="p-3 bg-secondary/50 rounded-lg border border-border/50">
                <p className="text-[10px] text-muted-foreground uppercase mb-1">连接器</p>
                <p className={`text-sm font-semibold ${hummingbotConnectors?.connected ? "text-cyan-400" : "text-muted-foreground"}`}>
                  {hummingbotConnectors?.connected ? hummingbotConnectors.count : "—"}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5">可用交易所</p>
              </div>

              {/* Bots */}
              <div className="p-3 bg-secondary/50 rounded-lg border border-border/50">
                <p className="text-[10px] text-muted-foreground uppercase mb-1">机器人</p>
                <p className={`text-sm font-semibold ${hummingbotBots?.count && hummingbotBots.count > 0 ? "text-green-400" : "text-muted-foreground"}`}>
                  {hummingbotBots?.count ?? "—"}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5 truncate" title={hummingbotBots?.source || ""}>
                  {hummingbotBots?.source && hummingbotBots.source !== "—" ? "MQTT" : "运行中"}
                </p>
              </div>
            </div>

            {/* Readonly data indicators */}
            {hummingbotStatus?.connected && (
              <div className="mt-3 grid grid-cols-3 gap-3">
                {/* Portfolio indicator */}
                <div className={`flex items-center gap-2 p-2 rounded-lg border ${hummingbotReadonly.portfolio ? "bg-green-500/5 border-green-500/20" : "bg-secondary/30 border-border/30"}`}>
                  <div className={`w-1.5 h-1.5 rounded-full ${hummingbotReadonly.portfolio ? "bg-green-400" : "bg-slate-600"}`} />
                  <div>
                    <p className="text-[10px] text-muted-foreground">实盘资产</p>
                    <p className={`text-[10px] font-semibold ${hummingbotReadonly.portfolio ? "text-green-400" : "text-muted-foreground"}`}>
                      {hummingbotReadonly.portfolio ? "有数据" : "无数据"}
                    </p>
                  </div>
                </div>
                {/* Orders indicator */}
                <div className={`flex items-center gap-2 p-2 rounded-lg border ${hummingbotReadonly.orders ? "bg-orange-500/5 border-orange-500/20" : "bg-secondary/30 border-border/30"}`}>
                  <div className={`w-1.5 h-1.5 rounded-full ${hummingbotReadonly.orders ? "bg-orange-400" : "bg-slate-600"}`} />
                  <div>
                    <p className="text-[10px] text-muted-foreground">实盘订单</p>
                    <p className={`text-[10px] font-semibold ${hummingbotReadonly.orders ? "text-orange-400" : "text-muted-foreground"}`}>
                      {hummingbotReadonly.orders ? "有数据" : "无数据"}
                    </p>
                  </div>
                </div>
                {/* Positions indicator */}
                <div className={`flex items-center gap-2 p-2 rounded-lg border ${hummingbotReadonly.positions ? "bg-emerald-500/5 border-emerald-500/20" : "bg-secondary/30 border-border/30"}`}>
                  <div className={`w-1.5 h-1.5 rounded-full ${hummingbotReadonly.positions ? "bg-emerald-400" : "bg-slate-600"}`} />
                  <div>
                    <p className="text-[10px] text-muted-foreground">实盘持仓</p>
                    <p className={`text-[10px] font-semibold ${hummingbotReadonly.positions ? "text-emerald-400" : "text-muted-foreground"}`}>
                      {hummingbotReadonly.positions ? "有数据" : "无数据"}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Footer */}
            <div className="mt-3 flex items-center justify-between pt-3 border-t border-border/50">
              <p className="text-[10px] text-muted-foreground">
                {hummingbotStatus?.timestamp
                  ? `最后更新: ${new Date(hummingbotStatus.timestamp).toLocaleTimeString()}`
                  : "点击刷新获取状态"}
              </p>
              <Link href="/hummingbot">
                <Button variant="ghost" size="sm" className="h-7 text-xs text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10">
                  <Server className="w-3 h-3 mr-1" /> 进入 Hummingbot 管理中心
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
          </TabsContent>

          <TabsContent value="positions" className="mt-0 space-y-6">
        <div className="space-y-6">
          <section className="overflow-hidden rounded-[2rem] border border-emerald-500/20 bg-[linear-gradient(135deg,rgba(6,78,59,0.68),rgba(15,23,42,0.92)_48%,rgba(69,26,3,0.54))] p-5 shadow-2xl shadow-emerald-950/30">
            <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
              <div className="space-y-5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="border border-emerald-400/25 bg-emerald-400/15 text-emerald-100">本地模拟盘</Badge>
                  <Badge variant="outline" className="border-amber-400/25 bg-amber-400/10 text-amber-200">只做练习，不碰真实资金</Badge>
                  <Badge variant="outline" className="border-sky-400/25 bg-sky-400/10 text-sky-200">标记价格：CCXT/{currentExchangeInfo.label}</Badge>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-200/75">Paper Trading Desk</p>
                  <h3 className="mt-2 text-3xl font-black tracking-tight text-white md:text-4xl">模拟盘交易台</h3>
                  <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-300">
                    这里是独立的虚拟账户工作区：看资金、做模拟下单、查持仓、看订单流水。行情总览负责看市场；这里负责练习执行和验证策略。
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-3xl border border-white/10 bg-black/25 p-5">
                    <p className="text-xs text-slate-400">账户总额</p>
                    <p className="mt-2 text-4xl font-black text-white">
                      {balance ? formatCurrency(balance.total_balance) : "—"}
                    </p>
                    <p className="mt-2 text-xs text-slate-400">本地数据库里的虚拟 USDT，不是真实资金。</p>
                  </div>
                  <div className="rounded-3xl border border-emerald-400/20 bg-emerald-400/10 p-5">
                    <p className="text-xs text-emerald-100/75">可用余额</p>
                    <p className="mt-2 text-4xl font-black text-emerald-200">
                      {balance ? formatCurrency(balance.available_balance) : "—"}
                    </p>
                    <p className="mt-2 text-xs text-emerald-100/70">模拟下单前会先过风控检查。</p>
                  </div>
                </div>
              </div>

              <div className="rounded-[1.75rem] border border-white/10 bg-black/30 p-4 backdrop-blur">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <p className="text-xs text-slate-400">当前模拟交易对</p>
                    <p className="mt-1 text-2xl font-bold text-white">
                      {symbols.find(s => s.value === currentSymbol)?.label || currentSymbol}
                    </p>
                  </div>
                  <Select key="paper-symbol-select" value={currentSymbol} onValueChange={handleSymbolChange}>
                    <SelectTrigger className="w-[142px] border-white/10 bg-white/10 text-white">
                      <SelectValue placeholder="选择币种" />
                    </SelectTrigger>
                    <SelectContent className="bg-secondary border-border">
                      {symbols.map(s => (
                        <SelectItem key={s.value} value={s.value} className="text-foreground focus:bg-secondary focus:text-foreground cursor-pointer">{s.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-4">
                    <p className="text-xs text-slate-400">当前持仓</p>
                    <p className="mt-2 text-3xl font-black text-white">{positions.length}</p>
                    <p className="mt-1 text-xs text-slate-500">未平仓模拟仓位</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-4">
                    <p className="text-xs text-slate-400">最近订单</p>
                    <p className="mt-2 text-3xl font-black text-white">{paperOrders.length}</p>
                    <p className="mt-1 text-xs text-slate-500">展示最近 8 条</p>
                  </div>
                </div>

                <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4">
                  <p className="text-xs text-slate-400">价格和成交口径</p>
                  <p className="mt-2 text-sm leading-6 text-slate-200">
                    模拟成交参考 {currentExchangeInfo.label} 的 CCXT 实时报价；K 线和市场新闻仍在“总览/数据源”页面查看，避免和模拟账户混在一起。
                  </p>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
                  <Button
                    onClick={() => setShowOrderPanel(true)}
                    className="bg-emerald-500 text-slate-950 hover:bg-emerald-400"
                  >
                    <Plus className="mr-1.5 h-3.5 w-3.5" /> 模拟下单
                  </Button>
                  <Link href="/trades">
                    <Button variant="outline" className="w-full border-white/15 bg-white/5 text-slate-100 hover:bg-white/10">
                      <History className="mr-1.5 h-3.5 w-3.5" /> 交易流水
                    </Button>
                  </Link>
                  <Link href="/analytics?mode=paper">
                    <Button variant="outline" className="w-full border-white/15 bg-white/5 text-slate-100 hover:bg-white/10">
                      <BarChart className="mr-1.5 h-3.5 w-3.5" /> 绩效分析
                    </Button>
                  </Link>
                </div>
              </div>
            </div>
          </section>

          {riskStatus && (
            <Card className="border-border/50 bg-card/90">
              <CardHeader className="pb-3">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                  <CardTitle className="flex items-center gap-2 text-base text-foreground">
                    <Shield className="h-4 w-4 text-emerald-400" /> 风控状态
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">
                    这些限制只作用于模拟盘下单，用来防止本地策略误操作。
                  </p>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <div className={`rounded-xl border p-3 ${riskStatus.kill_switch_active ? "border-red-500/30 bg-red-500/10 text-red-300" : "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"}`}>
                    <p className="text-[10px] uppercase tracking-wider opacity-80">交易开关</p>
                    <p className="mt-1 text-sm font-bold">{riskStatus.kill_switch_active ? "已触发" : "安全"}</p>
                  </div>
                  <div className="rounded-xl border border-border/60 bg-secondary/30 p-3">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">总回撤</p>
                    <p className={`mt-1 text-sm font-bold ${riskStatus.drawdown_breached ? "text-red-400" : "text-foreground"}`}>
                      {riskStatus.total_drawdown_pct}% / {riskStatus.drawdown_limit_pct}%
                    </p>
                  </div>
                  <div className="rounded-xl border border-border/60 bg-secondary/30 p-3">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">日内盈亏</p>
                    <p className={`mt-1 text-sm font-bold ${riskStatus.daily_loss_breached ? "text-red-400" : "text-foreground"}`}>
                      {formatCurrency(riskStatus.daily_pnl)}
                    </p>
                  </div>
                  <div className="rounded-xl border border-border/60 bg-secondary/30 p-3">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">最大杠杆</p>
                    <p className="mt-1 text-sm font-bold text-foreground">{riskStatus.max_leverage}x</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* ── Positions ── */}
          <Card className="bg-card border-border/50">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-foreground flex items-center gap-2">
                    <div className="w-8 h-8 bg-blue-500/10 rounded-lg flex items-center justify-center border border-blue-500/20">
                      <Activity className="w-4 h-4 text-blue-400" />
                    </div>
                    持仓
                    {positions.length > 0 && (
                      <Badge variant="outline" className="text-[10px] bg-blue-500/10 text-blue-400 border-blue-500/20 ml-1">
                        {positions.length}
                      </Badge>
                    )}
                  </CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    当前未平仓的模拟仓位，盈亏按 {currentExchangeInfo.label} 标记价格估算。
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground hover:text-foreground px-2" onClick={fetchPositions}>
                    <RefreshCw className="w-3 h-3 mr-1" /> 刷新
                  </Button>
                  {positions.length > 0 && (
                    <Button variant="outline" size="sm" className="h-7 text-xs border-red-500/30 text-red-400 hover:bg-red-500/10 hover:text-red-300" onClick={handleCloseAll}>
                      一键平仓
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              {positionsLoading ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载持仓中...
                </div>
              ) : positions.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
                  <Activity className="w-10 h-10 mb-3 opacity-30" />
                  <p className="text-sm">暂无持仓</p>
                  <p className="text-xs text-muted-foreground/50 mt-1">点击上方「模拟下单」开始模拟交易</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {positions.map((pos, idx) => (
                    <div key={idx} className="group relative p-4 bg-gradient-to-br bg-card rounded-xl border border-border/50 hover:hover:border-border transition-all hover:shadow-lg">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <div className="w-8 h-8 bg-green-500/15 text-green-400 border border-green-500/20 rounded-lg flex items-center justify-center">
                            <TrendingUp className="w-4 h-4" />
                          </div>
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span className="font-bold text-foreground">{pos.symbol}</span>
                              <Badge variant="outline" className="text-[9px] px-1 py-0 bg-green-500/10 text-green-400 border-green-500/20">LONG</Badge>
                            </div>
                            <p className="text-[10px] text-muted-foreground">持仓 {Number(pos.quantity).toFixed(6)}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className={`text-lg font-bold ${pos.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {pos.pnl >= 0 ? "+" : ""}${Number(pos.pnl).toFixed(2)}
                          </p>
                          <div className={`inline-flex items-center px-1.5 rounded text-[10px] font-medium ${pos.pnl >= 0 ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                            {pos.pnl_pct >= 0 ? "+" : ""}{Number(pos.pnl_pct).toFixed(2)}%
                          </div>
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-1 p-2 bg-card/50 rounded-lg border border-border/50 text-center">
                        <div>
                          <p className="text-muted-foreground text-[9px] uppercase">开仓</p>
                          <p className="text-foreground/90 font-medium text-xs">${Number(pos.avg_price).toFixed(2)}</p>
                        </div>
                        <div className="border-x border-border/50">
                          <p className="text-muted-foreground text-[9px] uppercase">标记价</p>
                          <p className="text-blue-400 font-medium text-xs">${Number(pos.mark_price).toFixed(2)}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground text-[9px] uppercase">数量</p>
                          <p className="text-foreground/80 font-medium text-xs">{Number(pos.quantity).toFixed(4)}</p>
                        </div>
                      </div>

                      <div className="mt-2 flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          variant="ghost" size="sm"
                          className="h-6 text-[10px] text-red-400 hover:bg-red-500/10 px-2"
                          onClick={() => handleClosePosition(pos)}
                        >
                          平仓
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="bg-card border-border/50">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-foreground flex items-center gap-2">
                    <div className="w-8 h-8 bg-amber-500/10 rounded-lg flex items-center justify-center border border-amber-500/20">
                      <History className="w-4 h-4 text-amber-400" />
                    </div>
                    最近订单
                  </CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    这里是模拟盘订单流水，成交价来自当时的标记价格，不代表真实账户成交记录。
                  </p>
                </div>
                <Button variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground hover:text-foreground px-2" onClick={fetchPaperOrders}>
                  <RefreshCw className="w-3 h-3 mr-1" /> 刷新
                </Button>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              {ordersLoading ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载订单中...
                </div>
              ) : paperOrders.length === 0 ? (
                <div className="rounded-xl border border-border/60 bg-secondary/20 p-5 text-center text-sm text-muted-foreground">
                  暂无模拟订单。点击“模拟下单”后，成交会出现在这里。
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] text-left text-sm">
                    <thead className="border-b border-border/60 text-xs text-muted-foreground">
                      <tr>
                        <th className="py-2 font-medium">时间</th>
                        <th className="py-2 font-medium">交易对</th>
                        <th className="py-2 font-medium">方向</th>
                        <th className="py-2 font-medium">数量</th>
                        <th className="py-2 font-medium">成交价</th>
                        <th className="py-2 font-medium">手续费</th>
                        <th className="py-2 font-medium">已实现盈亏</th>
                        <th className="py-2 font-medium">状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paperOrders.map((order) => (
                        <tr key={order.order_id} className="border-b border-border/30 last:border-0">
                          <td className="py-2 text-xs text-muted-foreground">
                            {order.created_at ? new Date(order.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—"}
                          </td>
                          <td className="py-2 font-medium text-foreground">{order.symbol}</td>
                          <td className="py-2">
                            <Badge variant="outline" className={order.side === "BUY" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-red-500/20 bg-red-500/10 text-red-300"}>
                              {formatOrderSide(order.side)}
                            </Badge>
                          </td>
                          <td className="py-2 font-mono text-foreground/80">{toFiniteNumber(order.quantity).toFixed(6)}</td>
                          <td className="py-2 font-mono text-foreground/80">{formatCurrency(order.price)}</td>
                          <td className="py-2 font-mono text-muted-foreground">{formatCurrency(order.fee)}</td>
                          <td className={`py-2 font-mono ${hasFiniteNumber(order.pnl) ? (toFiniteNumber(order.pnl) >= 0 ? "text-emerald-400" : "text-red-400") : "text-muted-foreground"}`}>
                            {hasFiniteNumber(order.pnl) ? formatCurrency(order.pnl) : "—"}
                          </td>
                          <td className="py-2 text-xs text-muted-foreground">{formatOrderStatus(order.status)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
          </TabsContent>

          <TabsContent value="agents" className="mt-0 space-y-6">
        <div className="space-y-6">
          {/* ── AI Agents ── */}
          <Card className="bg-card border-border/50">
            <CardHeader className="pb-4">
              <CardTitle className="text-foreground flex items-center gap-2">
                <div className="w-8 h-8 bg-purple-500/10 rounded-lg flex items-center justify-center border border-purple-500/20">
                  <Brain className="w-4 h-4 text-purple-400" />
                </div>
                子分析 Agent 状态
                <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse ml-1" />
              </CardTitle>
              <p className="mt-2 text-xs text-muted-foreground">
                默认最终决策由 TradingAgents 生成；这里的趋势、均值回归和风险 Agent 主要用于生成子观点、信号和人工排查，不再作为最终拍板引擎。
              </p>
            </CardHeader>
            <CardContent className="pt-0">
              {ollamaStatus.checked && !ollamaStatus.online && agents.some(a => a.provider === "ollama") && (
                <div className="mb-4 p-3 bg-orange-500/10 border border-orange-500/30 rounded-lg flex items-start gap-2">
                  <WifiOff className="w-4 h-4 text-orange-400 mt-0.5 shrink-0" />
                  <div className="text-xs text-orange-300">
                    <p className="font-semibold mb-1">Ollama 本地服务未运行</p>
                    <a href="https://ollama.com/download" target="_blank" rel="noopener noreferrer" className="text-blue-400 underline">下载 Ollama</a>
                    <span className="ml-2 text-orange-400/70">启动后运行：<code className="bg-secondary px-1 rounded">ollama run qwen3:8b</code></span>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {agents.map((agent) => {
                  const remaining = cooldownRemaining[agent.id] || 0;
                  const isOllamaOffline = agent.provider === "ollama" && ollamaStatus.checked && !ollamaStatus.online;
                  const canAnalyze = agent.status === "运行中" && !agent.analyzing && remaining === 0 && !isOllamaOffline;
                  const hasError = agent.logs.includes("失败") || isOllamaOffline;
                  const colorMap: Record<string, { bg: string; text: string; border: string; glow: string }> = {
                    blue:   { bg: "bg-blue-500/10",   text: "text-blue-400",   border: "border-blue-500/20",   glow: "hover:shadow-blue-500/10" },
                    purple: { bg: "bg-purple-500/10", text: "text-purple-400", border: "border-purple-500/20", glow: "hover:shadow-purple-500/10" },
                    orange: { bg: "bg-orange-500/10", text: "text-orange-400", border: "border-orange-500/20", glow: "hover:shadow-orange-500/10" },
                  };
                  const s = colorMap[agent.color] || colorMap.blue;

                  return (
                    <div key={agent.id} className={`group relative bg-gradient-to-br bg-card rounded-xl border ${hasError ? "border-red-500/30" : "border-border/50"} hover:hover:border-border transition-all hover:shadow-lg ${s.glow} flex flex-col`}>
                      <div className="p-3">
                        <div className="flex items-center gap-3">
                          <div className={`w-10 h-10 ${s.bg} rounded-lg flex items-center justify-center border ${s.border} shrink-0`}>
                            <agent.icon className={`w-5 h-5 ${s.text}`} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-1">
                              <p className="font-bold text-foreground text-sm truncate">{agent.name}</p>
                              <Badge variant="outline" className={`text-[9px] px-1 py-0 ${agent.status === "运行中" ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-slate-500/10 text-muted-foreground border-muted-foreground/20"}`}>
                                {agent.status}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className="text-[10px] text-muted-foreground truncate">{aiProviders.find(p => p.value === agent.provider)?.label || agent.provider}</span>
                              {agent.winRateLoading ? (
                                <span className="text-[10px] text-muted-foreground">胜率: <span className="text-muted-foreground animate-pulse">计算中…</span></span>
                              ) : agent.winRate !== "--" ? (
                                <span className="text-[10px] text-muted-foreground">
                                  胜率: <span className={parseFloat(agent.winRate) >= 50 ? "text-green-400" : "text-red-400"}>{agent.winRate}</span>
                                </span>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex-1 flex flex-col">
                        {configuringAgent === agent.id && (
                          <div className="mx-3 mb-2 p-2 bg-card rounded-lg border border-border">
                            <div className="text-[10px] text-muted-foreground mb-1">选择模型:</div>
                            <Select value={agent.provider} onValueChange={v => handleProviderChange(agent.id, v)}>
                              <SelectTrigger className="w-full h-7 bg-secondary border-border text-foreground text-[10px]">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent className="bg-secondary border-border">
                                {aiProviders.map(p => (
                                  <SelectItem key={p.value} value={p.value} className="text-[10px] text-foreground cursor-pointer focus:bg-secondary">{p.label}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        )}

                        {agent.provider === "ollama" && agent.thinkingContent && (
                          <div className="mx-3 mb-1">
                            <button onClick={() => toggleThink(agent.id)} className="flex items-center gap-1 text-[9px] text-amber-400/70 hover:text-amber-400 w-full">
                              <Brain className="w-3 h-3 shrink-0" /> <span>思考过程</span>
                              {agent.thinkCollapsed ? <ChevronDown className="w-3 h-3 ml-auto" /> : <ChevronUp className="w-3 h-3 ml-auto" />}
                            </button>
                            {!agent.thinkCollapsed && (
                              <div className="mt-1 p-2 bg-amber-500/5 border border-amber-500/15 rounded-lg max-h-[200px] overflow-y-auto">
                                <p className="text-[9px] text-amber-300/60 italic whitespace-pre-wrap">{agent.thinkingContent}</p>
                              </div>
                            )}
                          </div>
                        )}

                        <div className="mx-3 mb-2 flex-1 min-h-0">
                          <div className={`bg-card/50 rounded-lg p-2 border ${hasError ? "border-red-500/20 bg-red-500/5" : "border-border"}`}>
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-1.5">
                                <div className={`w-1.5 h-1.5 rounded-full ${agent.analyzing ? "bg-blue-400 animate-pulse" : hasError ? "bg-red-400" : "bg-slate-600"}`} />
                                <span className={`text-[9px] uppercase font-semibold tracking-wider ${hasError ? "text-red-400" : "text-blue-400"}`}>{hasError ? "错误" : "AI分析"}</span>
                              </div>
                              {analysisCache.current[`${agent.id}-${currentSymbol}`] && !agent.analyzing && !hasError && (
                                <span className="text-[8px] text-muted-foreground">已缓存</span>
                              )}
                            </div>
                            <div className="prose prose-invert prose-sm max-w-none h-[320px] overflow-y-auto custom-scrollbar">
                              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                                h1: ({ children }) => <h1 className="text-sm font-bold text-foreground mb-1">{children}</h1>,
                                h2: ({ children }) => <h2 className="text-xs font-semibold text-foreground/90 mb-1 mt-2">{children}</h2>,
                                h3: ({ children }) => <h3 className="text-[11px] font-semibold text-foreground/80 mb-0.5 mt-1">{children}</h3>,
                                p:  ({ children }) => <div className="text-[10px] text-foreground/80 leading-relaxed mb-1">{children}</div>,
                                ul: ({ children }) => <ul className="list-disc list-inside text-[10px] text-foreground/80 mb-1 space-y-0">{children}</ul>,
                                ol: ({ children }) => <ol className="list-decimal list-inside text-[10px] text-foreground/80 mb-1 space-y-0">{children}</ol>,
                                li: ({ children }) => <li className="text-[10px] text-foreground/80">{children}</li>,
                                strong: ({ children }) => <strong className="text-foreground font-semibold">{children}</strong>,
                                code: ({ children }) => <code className="bg-secondary text-foreground/90 px-0.5 rounded text-[9px] font-mono">{children}</code>,
                              }}>
                                {agent.outputContent || agent.logs}
                              </ReactMarkdown>
                            </div>
                          </div>
                        </div>

                        <div className="px-3 pb-3 flex justify-between items-center gap-1">
                          <Button
                            variant="outline" size="sm"
                            className={`h-7 text-[10px] px-2 border-border ${canAnalyze ? `${s.text} ${s.border} hover:bg-secondary` : "text-muted-foreground/50 border-border cursor-not-allowed"}`}
                            disabled={!canAnalyze}
                            onClick={() => { const a = agents.find(x => x.id === agent.id); if (a) fetchAgentAnalysis(a, false); }}
                          >
                            {agent.analyzing ? <><RefreshCw className="w-3 h-3 mr-0.5 animate-spin" />分析中</>
                              : remaining > 0 ? <><RefreshCw className="w-3 h-3 mr-0.5" />{remaining}s</>
                              : isOllamaOffline ? <><WifiOff className="w-3 h-3 mr-0.5" />离线</>
                              : <><Zap className="w-3 h-3 mr-0.5" />分析</>}
                          </Button>
                          <div className="flex gap-1">
                            <Button variant="ghost" size="sm" className="h-7 text-[10px] text-muted-foreground hover:text-foreground px-2" onClick={() => toggleAgentStatus(agent.id)}>
                              {agent.status === "运行中" ? "暂停" : "启动"}
                            </Button>
                            <Button variant="ghost" size="sm" className={`h-7 text-[10px] px-2 ${configuringAgent === agent.id ? `${s.text} ${s.bg}` : "text-muted-foreground hover:text-foreground"}`}
                              onClick={() => setConfiguringAgent(configuringAgent === agent.id ? null : agent.id)}>
                              <Settings className="w-3 h-3" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>
          </TabsContent>

        </Tabs>
      </main>

      {/* ── Order Panel Modal ── */}
      {showOrderPanel && (
        <OrderPanel
          symbol={currentSymbol}
          exchangeId={currentExchange}
          currentPrice={ticker?.price ?? null}
          onClose={() => setShowOrderPanel(false)}
          onOrderPlaced={() => { fetchPositions(); fetchBalance(); fetchPaperOrders(); setShowOrderPanel(false); }}
        />
      )}
    </div>
  );
}
