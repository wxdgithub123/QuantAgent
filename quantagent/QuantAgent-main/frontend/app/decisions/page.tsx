"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  BarChart,
  BarChart3,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  History,
  Layers,
  Minus,
  PieChart,
  RefreshCw,
  Server,
  Shield,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import {
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart as RPieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Prd104StatusPanel } from "@/components/prd/Prd104StatusPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface RoleOpinion {
  role?: string;
  opinion?: string;
  confidence?: number;
  risk_flag?: boolean;
  reasoning?: string;
  key_points?: string[];
}

interface DecisionRow {
  id: number;
  symbol: string;
  timestamp: string | null;
  final_signal: string;
  confidence: number;
  vote_breakdown: Record<string, number>;
  risk_veto: boolean;
  summary: string;
  agent_signals: Array<RoleOpinion & { agent_type?: string; agent?: string; signal?: string; type?: string }>;
  bull_view?: string;
  bear_view?: string;
  input_snapshot_ids?: Record<string, unknown>;
  role_opinions?: RoleOpinion[];
  position_advice?: Record<string, unknown>;
  risk_notes?: string;
}

interface Stats {
  total: number;
  recent_7d: number;
  avg_confidence: number;
  veto_count: number;
  by_signal: Record<string, number>;
  by_symbol: Record<string, number>;
  error?: string;
}

interface NativeTradingAgentsResult {
  status?: string;
  symbol?: string;
  decision?: string;
  confidence?: number;
  reasoning?: string;
  analyst_reports?: RoleOpinion[];
  error?: string;
  raw?: {
    native_symbol?: string;
    selected_analysts?: string[];
    data_source_note?: string;
    openai_base_url?: string;
    quick_model?: string;
    deep_model?: string;
    trade_date?: string;
  };
}

interface BackfillStatusRow {
  symbol?: string;
  interval?: string;
  status?: string;
}

const PIE_COLORS = ["#34d399", "#fb7185", "#94a3b8", "#38bdf8", "#fbbf24", "#a78bfa"];
const FALLBACK_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "XRPUSDT"];
const NATIVE_TRADINGAGENTS_ANALYSTS = ["market", "news", "social", "fundamentals"];
const PREFERRED_SYMBOL_ORDER = new Map(FALLBACK_SYMBOLS.map((symbol, index) => [symbol, index]));
const VOTE_LABELS: Record<string, string> = {
  bullish: "看多",
  bearish: "看空",
  neutral: "观望",
};
const VOTE_COLORS: Record<string, string> = {
  bullish: "#34d399",
  bearish: "#fb7185",
  neutral: "#94a3b8",
};

function formatPercent(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return `${(value * 100).toFixed(1)}%`;
}

function signalLabel(signal?: string) {
  const normalized = String(signal || "WAIT").toUpperCase();
  if (normalized === "BUY") return "买入";
  if (normalized === "SELL") return "卖出";
  if (normalized === "HOLD") return "持有";
  return "观望";
}

function signalBadgeClass(signal?: string) {
  const normalized = String(signal || "WAIT").toUpperCase();
  if (normalized === "BUY") return "border-emerald-400/30 bg-emerald-500/15 text-emerald-300";
  if (normalized === "SELL") return "border-rose-400/30 bg-rose-500/15 text-rose-300";
  return "border-slate-400/20 bg-slate-500/15 text-slate-300";
}

function roleLabel(role?: string) {
  if (!role) return "未标注角色";
  if (role === "tradingagents_openai_decision") return "TradingAgents + DMXAPI / gpt-4o-mini";
  if (role === "tradingagents_context_adapter") return "TradingAgents 基线评分";
  if (role === "tradingagents_native_market") return "原版 TradingAgents 市场分析";
  if (role === "tradingagents_native_news") return "原版 TradingAgents 新闻分析";
  if (role === "tradingagents_native_situation") return "原版 TradingAgents 情景摘要";
  if (role === "tradingagents_native_trader") return "原版 TradingAgents 交易员";
  if (role === "tradingagents_native_final_judge") return "原版 TradingAgents 最终裁决";
  if (role === "technical") return "技术面 Agent";
  if (role === "news") return "新闻 Agent";
  if (role === "macro") return "宏观 Agent";
  if (role === "risk") return "风险 Agent";
  return role;
}

function roleDescription(role?: string) {
  if (role === "tradingagents_openai_decision") return "实际调用 OpenAI 兼容接口，由 DMXAPI 转发到 gpt-4o-mini 输出最终结构化判断。";
  if (role === "tradingagents_context_adapter") return "不调用大模型的本地基线判断，用来兜底和解释输入上下文。";
  if (role?.startsWith("tradingagents_native_")) return "来自原版 TradingAgentsGraph 沙盒，使用原版 yfinance / Google News RSS 工具链。";
  return "参与本次决策的结构化分析结果。";
}

function roleScoreLabel(role?: string) {
  if (role === "tradingagents_context_adapter") return "基线参考分";
  if (role === "tradingagents_openai_decision") return "模型置信度";
  return "置信度";
}

function primaryEngine(decision?: DecisionRow) {
  const roles = decision?.agent_signals || decision?.role_opinions || [];
  const firstRole = roles[0]?.role;
  if (firstRole === "tradingagents_openai_decision") return "TradingAgents + DMXAPI / gpt-4o-mini";
  if (firstRole === "tradingagents_context_adapter") return "TradingAgents 基线";
  return firstRole ? roleLabel(firstRole) : "未记录";
}

function snapshotCount(snapshot: Record<string, unknown> | undefined, key: string) {
  const value = snapshot?.[key];
  return Array.isArray(value) ? value.length : 0;
}

function contextCountFromKeyPoints(decision?: DecisionRow, key?: string) {
  if (!decision || !key) return null;
  const points = decision.agent_signals.flatMap((signal) => signal.key_points || []);
  const match = points.map(String).find((point) => point.startsWith(`${key}=`));
  if (!match) return null;
  const [, raw] = match.split("=");
  const count = Number(raw);
  return Number.isFinite(count) ? count : null;
}

function normalizeSymbol(value: string) {
  return value.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
}

function buildSymbolOptions(rows: BackfillStatusRow[]) {
  const available = rows
    .filter((row) => row.status === "ok" && typeof row.symbol === "string")
    .map((row) => normalizeSymbol(row.symbol || ""))
    .filter((symbol) => symbol.endsWith("USDT") && symbol !== "SOURCE");
  const unique = Array.from(new Set([...available, ...FALLBACK_SYMBOLS]));
  return unique.sort((left, right) => {
    const leftRank = PREFERRED_SYMBOL_ORDER.get(left) ?? 999;
    const rightRank = PREFERRED_SYMBOL_ORDER.get(right) ?? 999;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return left.localeCompare(right);
  });
}

function StatCard({
  label,
  value,
  detail,
  accent,
}: {
  label: string;
  value: string | number;
  detail: string;
  accent: string;
}) {
  return (
    <Card className="border-white/10 bg-slate-900/55 shadow-xl shadow-black/10">
      <CardContent className="p-4">
        <p className="text-xs text-slate-400">{label}</p>
        <p className={cn("mt-2 text-2xl font-bold", accent)}>{value}</p>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{detail}</p>
      </CardContent>
    </Card>
  );
}

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<DecisionRow[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runFast, setRunFast] = useState(true);
  const [error, setError] = useState("");
  const [filterSymbol, setFilterSymbol] = useState("BTCUSDT");
  const [symbolOptions, setSymbolOptions] = useState(FALLBACK_SYMBOLS);
  const [nativeRunning, setNativeRunning] = useState(false);
  const [nativeTradeDate, setNativeTradeDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [nativeResult, setNativeResult] = useState<NativeTradingAgentsResult | null>(null);
  const [nativeError, setNativeError] = useState("");

  const fetchDecisions = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (filterSymbol) params.set("symbol", filterSymbol);
      const res = await fetch(`/api/v1/coordination/history?${params}`);
      if (res.ok) {
        const d = await res.json();
        setDecisions(d.data || []);
        setError("");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [filterSymbol]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/coordination/stats");
      if (res.ok) setStats(await res.json());
    } catch {
      // Stats are helpful, but the history table can still render without them.
    }
  }, []);

  const fetchSymbolOptions = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/market/backfill/status", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const rows = Array.isArray(data?.intervals) ? data.intervals : [];
      setSymbolOptions(buildSymbolOptions(rows));
    } catch {
      setSymbolOptions(FALLBACK_SYMBOLS);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([fetchDecisions(), fetchStats(), fetchSymbolOptions()]);
  }, [fetchDecisions, fetchStats, fetchSymbolOptions]);

  const runFullDecision = useCallback(async () => {
    const symbol = (filterSymbol || "BTCUSDT").toUpperCase();
    setRunning(true);
    setError("");
    try {
      const params = new URLSearchParams({ interval: "1h", fast: String(runFast) });
      const res = await fetch(`/api/v1/market/coordinate/${symbol}?${params.toString()}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.detail || data?.error || `协调分析失败: ${res.status}`);
      }
      await refreshAll();
      setExpandedId(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, [filterSymbol, refreshAll, runFast]);

  const runNativeTradingAgents = useCallback(async () => {
    const symbol = (filterSymbol || "BTCUSDT").toUpperCase();
    setNativeRunning(true);
    setNativeError("");
    setNativeResult(null);
    try {
      const res = await fetch("/api/tradingagents-native/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          interval: "1h",
          trade_date: nativeTradeDate || undefined,
          selected_analysts: NATIVE_TRADINGAGENTS_ANALYSTS,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data?.status === "error") {
        throw new Error(data?.error || data?.detail?.detail || data?.detail || `原版实验运行失败: ${res.status}`);
      }
      setNativeResult(data);
    } catch (e: unknown) {
      setNativeError(e instanceof Error ? e.message : String(e));
    } finally {
      setNativeRunning(false);
    }
  }, [filterSymbol, nativeTradeDate]);

  useEffect(() => {
    refreshAll().finally(() => setLoading(false));
  }, [refreshAll]);

  const latestDecision = decisions[0];
  const latestSnapshot = latestDecision?.input_snapshot_ids;
  const latestSignalCount = contextCountFromKeyPoints(latestDecision, "signals") ?? snapshotCount(latestSnapshot, "signal_event_ids");
  const latestNewsCount = contextCountFromKeyPoints(latestDecision, "news_events") ?? snapshotCount(latestSnapshot, "news_payload_ids");
  const latestMacroCount = contextCountFromKeyPoints(latestDecision, "macro_events") ?? snapshotCount(latestSnapshot, "macro_keys");
  const latestFactorCount = snapshotCount(latestSnapshot, "factor_snapshot_ids");

  const signalPieData = stats?.by_signal
    ? Object.entries(stats.by_signal).map(([name, value]) => ({ name: signalLabel(name), raw: name, value }))
    : [];
  const confidenceTrendData = [...decisions]
    .reverse()
    .slice(-30)
    .map((decision) => ({
      time: decision.timestamp ? new Date(decision.timestamp).toLocaleDateString() : "",
      confidence: Number((decision.confidence * 100).toFixed(1)),
      signal: signalLabel(decision.final_signal),
    }));

  return (
    <div className="min-h-screen bg-[#071026] text-slate-100">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#101a37]/95 backdrop-blur">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400 to-fuchsia-500 shadow-lg shadow-fuchsia-500/20">
                <BarChart3 className="h-5 w-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white">QuantAgent OS</h1>
                <p className="text-[10px] text-slate-400">加密资产优先的量化研究与决策平台</p>
              </div>
            </div>
            <nav className="hidden items-center gap-1 md:flex">
              <Link href="/dashboard" className="rounded-lg px-3 py-1.5 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white">仪表盘</Link>
              <Link href="/trades" className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white"><Activity className="h-4 w-4" />交易流水</Link>
              <Link href="/analytics" className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white"><BarChart className="h-4 w-4" />性能分析</Link>
              <Link href="/replay" className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white"><History className="h-4 w-4" />历史回放</Link>
              <Link href="/terminal" className="rounded-lg px-3 py-1.5 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white">终端</Link>
              <Link href="/hummingbot" className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white"><Server className="h-4 w-4" />Hummingbot</Link>
              <Link href="/signals" className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white"><Layers className="h-4 w-4" />因子/信号</Link>
              <Link href="/decisions" className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/30 bg-fuchsia-500/15 px-3 py-1.5 text-sm font-medium text-fuchsia-200"><Brain className="h-4 w-4" />决策中心</Link>
            </nav>
            <Button size="icon" variant="ghost" className="h-8 w-8 text-slate-300 hover:text-white" onClick={refreshAll}>
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6">
        {error && (
          <div className="mb-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {error}
          </div>
        )}

        <section className="mb-6 overflow-hidden rounded-[28px] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.20),transparent_34%),linear-gradient(135deg,rgba(15,23,42,0.96),rgba(24,31,67,0.92))] p-5 shadow-2xl shadow-cyan-950/30">
          <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
            <div>
              <Badge className="border border-cyan-300/30 bg-cyan-400/10 text-cyan-200">智能决策中心</Badge>
              <h2 className="mt-4 text-2xl font-bold tracking-tight text-white">查看交易建议和判断依据</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">
                系统会汇总行情、技术因子、策略信号、新闻和宏观背景，
                交给 TradingAgents 生成可追溯的交易建议，方便你判断是否继续研究或执行。
              </p>
              <div className="mt-4 grid gap-3 sm:grid-cols-4">
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
                  <p className="text-[11px] text-slate-400">当前标的</p>
                  <p className="mt-1 font-mono text-lg font-semibold text-white">{latestDecision?.symbol || filterSymbol}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
                  <p className="text-[11px] text-slate-400">最新建议</p>
                  <p className="mt-1 text-lg font-semibold text-white">{latestDecision ? signalLabel(latestDecision.final_signal) : "--"}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
                  <p className="text-[11px] text-slate-400">置信度</p>
                  <p className="mt-1 text-lg font-semibold text-emerald-300">{formatPercent(latestDecision?.confidence)}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
                  <p className="text-[11px] text-slate-400">决策引擎</p>
                  <p className="mt-1 text-sm font-semibold text-fuchsia-200">{primaryEngine(latestDecision)}</p>
                </div>
              </div>
            </div>

            <Card className="border-fuchsia-400/20 bg-slate-950/45">
              <CardContent className="p-4">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-fuchsia-300" />
                  <h3 className="text-sm font-semibold text-white">生成一次新的交易建议</h3>
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-400">
                  点击后会读取当前已有数据并生成一条建议记录。这里不会自动下单。
                </p>
                <div className="mt-4 space-y-3">
                  <div className="space-y-2">
                    <label className="text-xs text-slate-400">选择币种</label>
                    <select
                      value={symbolOptions.includes(filterSymbol) ? filterSymbol : symbolOptions[0] || "BTCUSDT"}
                      onChange={(event) => setFilterSymbol(event.target.value)}
                      className="w-full rounded-xl border border-white/10 bg-slate-950/70 px-3 py-2 font-mono text-sm text-white outline-none transition focus:border-cyan-300/50"
                    >
                      {symbolOptions.map((symbol) => (
                        <option key={symbol} value={symbol}>
                          {symbol}
                        </option>
                      ))}
                    </select>
                    <p className="text-[11px] leading-5 text-slate-500">
                      下拉列表来自当前已有行情缓存，只展示系统已有数据的交易对。
                    </p>
                  </div>
                  <label className="flex items-start gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-slate-300">
                    <input
                      type="checkbox"
                      checked={runFast}
                      onChange={(event) => setRunFast(event.target.checked)}
                      className="mt-0.5"
                    />
                    <span>
                      快速模式：更快返回结果，适合查看当前建议。关闭后会做更完整的分析。
                    </span>
                  </label>
                  <Button
                    className="w-full bg-gradient-to-r from-fuchsia-500 to-cyan-400 font-semibold text-white hover:from-fuchsia-400 hover:to-cyan-300"
                    disabled={running}
                    onClick={runFullDecision}
                  >
                    {running ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <Brain className="mr-2 h-4 w-4" />}
                    {running ? "正在生成建议..." : "生成交易建议"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>

        <Prd104StatusPanel className="mb-6" />

        <Card className="mb-6 overflow-hidden border-amber-300/20 bg-[radial-gradient(circle_at_top_left,rgba(251,191,36,0.18),transparent_34%),linear-gradient(135deg,rgba(30,41,59,0.92),rgba(15,23,42,0.96))] shadow-xl shadow-amber-950/10">
          <CardContent className="p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-3xl">
                <Badge className="border border-amber-300/30 bg-amber-400/10 text-amber-200">实验环境</Badge>
                <h3 className="mt-3 flex items-center gap-2 text-lg font-semibold text-white">
                  <Shield className="h-5 w-5 text-amber-300" />
                  原版 TradingAgentsGraph 实验运行
                </h3>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  这个入口会调用原版 TradingAgentsGraph。它主要使用 yfinance 和 Google News RSS，
                  不读取我们主链路里的 OpenBB / CCXT / ClickHouse / 因子信号，也不会写入正式决策历史。
                </p>
                <p className="mt-2 text-xs leading-5 text-amber-100/80">
                  适合做对比研究，预计耗时约 2-5 分钟；当前启用 market、news、social、fundamentals 全部原版角色。
                  其中 fundamentals 偏股票基本面，仅作为原版框架对比参考。
                </p>
                <p className="mt-2 text-xs leading-5 text-slate-400">
                  当前角色：market 市场分析、news 新闻分析、social 情绪分析、fundamentals 基本面分析。
                </p>
              </div>

              <div className="w-full rounded-2xl border border-white/10 bg-slate-950/40 p-4 lg:max-w-sm">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                  <div className="space-y-2">
                    <label className="text-xs text-slate-400">实验币种</label>
                    <select
                      value={symbolOptions.includes(filterSymbol) ? filterSymbol : symbolOptions[0] || "BTCUSDT"}
                      onChange={(event) => setFilterSymbol(event.target.value)}
                      className="w-full rounded-xl border border-white/10 bg-slate-950/70 px-3 py-2 font-mono text-sm text-white outline-none transition focus:border-amber-300/50"
                    >
                      {symbolOptions.map((symbol) => (
                        <option key={symbol} value={symbol}>
                          {symbol}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-xs text-slate-400">分析日期</label>
                    <input
                      type="date"
                      value={nativeTradeDate}
                      onChange={(event) => setNativeTradeDate(event.target.value)}
                      className="w-full rounded-xl border border-white/10 bg-slate-950/70 px-3 py-2 text-sm text-white outline-none transition focus:border-amber-300/50"
                    />
                  </div>
                </div>
                <Button
                  className="mt-4 w-full bg-gradient-to-r from-amber-400 to-orange-500 font-semibold text-slate-950 hover:from-amber-300 hover:to-orange-400"
                  disabled={nativeRunning}
                  onClick={runNativeTradingAgents}
                >
                  {nativeRunning ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                  {nativeRunning ? "原版实验运行中..." : "运行原版实验"}
                </Button>
              </div>
            </div>

            {nativeError && (
              <div className="mt-4 rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
                {nativeError}
              </div>
            )}

            {nativeResult && (
              <div className="mt-5 grid gap-4 lg:grid-cols-[0.7fr_1.3fr]">
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                  <p className="text-xs text-slate-400">原版结果</p>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Badge className={cn("border text-sm", signalBadgeClass(nativeResult.decision))}>
                      {signalLabel(nativeResult.decision)}
                    </Badge>
                    <span className="text-sm text-slate-300">置信度 {formatPercent(nativeResult.confidence)}</span>
                  </div>
                  <div className="mt-4 space-y-2 text-xs leading-5 text-slate-400">
                    <p>原版识别代码：<span className="font-mono text-slate-200">{nativeResult.raw?.native_symbol || "--"}</span></p>
                    <p>启用角色：{nativeResult.raw?.selected_analysts?.join(", ") || NATIVE_TRADINGAGENTS_ANALYSTS.join(", ")}</p>
                    <p>模型：{nativeResult.raw?.quick_model || "gpt-4o-mini"}</p>
                    <p>来源：yfinance / Google News RSS</p>
                  </div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                  <p className="text-xs text-slate-400">原版解释</p>
                  <p className="mt-2 text-sm leading-6 text-slate-200">
                    {nativeResult.reasoning || nativeResult.error || "原版 TradingAgentsGraph 没有返回解释。"}
                  </p>
                  {nativeResult.analyst_reports && nativeResult.analyst_reports.length > 0 && (
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {nativeResult.analyst_reports.slice(0, 4).map((report, index) => (
                        <div key={`${report.role || "native"}-${index}`} className="rounded-xl border border-white/10 bg-slate-950/35 p-3">
                          <p className="text-xs font-semibold text-amber-200">{roleLabel(report.role)}</p>
                          <p className="mt-1 line-clamp-3 text-xs leading-5 text-slate-400">{report.reasoning}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {stats && !stats.error && (
          <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-5">
            <StatCard label="历史建议记录" value={stats.total} detail="系统生成过的建议数量，不代表真实下单次数。" accent="text-cyan-300" />
            <StatCard label="近 7 天新增" value={stats.recent_7d} detail="最近 7 天新增的交易建议记录。" accent="text-fuchsia-300" />
            <StatCard label="平均置信度" value={formatPercent(stats.avg_confidence)} detail="所有历史决策 confidence 的平均值。" accent="text-emerald-300" />
            <StatCard label="风险否决次数" value={stats.veto_count} detail="风险模块触发 veto 或风险标记的次数。" accent="text-rose-300" />
            <StatCard label="覆盖交易对" value={Object.keys(stats.by_symbol || {}).length} detail="已有决策记录的 symbol 数量。" accent="text-amber-300" />
          </div>
        )}

        <div className="mb-6 grid gap-4 lg:grid-cols-4">
          <Card className="border-white/10 bg-slate-900/55 lg:col-span-4">
            <CardContent className="grid gap-4 p-4 md:grid-cols-4">
              <div>
                <p className="text-xs text-slate-400">策略信号</p>
                <p className="mt-1 text-xl font-bold text-white">{latestSignalCount}</p>
                <p className="mt-1 text-[11px] text-slate-500">本次建议参考的最近策略判断</p>
              </div>
              <div>
                <p className="text-xs text-slate-400">技术因子</p>
                <p className="mt-1 text-xl font-bold text-white">{latestFactorCount}</p>
                <p className="mt-1 text-[11px] text-slate-500">本次建议使用的最新指标记录</p>
              </div>
              <div>
                <p className="text-xs text-slate-400">相关新闻</p>
                <p className="mt-1 text-xl font-bold text-white">{latestNewsCount}</p>
                <p className="mt-1 text-[11px] text-slate-500">用于判断市场情绪和事件风险</p>
              </div>
              <div>
                <p className="text-xs text-slate-400">宏观背景</p>
                <p className="mt-1 text-xl font-bold text-white">{latestMacroCount}</p>
                <p className="mt-1 text-[11px] text-slate-500">利率、通胀、就业等市场背景</p>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Card className="border-white/10 bg-slate-900/60">
              <CardHeader className="pb-3">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-base text-white">
                      <Brain className="h-4 w-4 text-fuchsia-300" />
                      决策历史
                    </CardTitle>
                    <p className="mt-1 text-xs text-slate-400">点击任意一行可以展开，查看模型、信号、新闻、宏观和风险说明。</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <select
                      value={symbolOptions.includes(filterSymbol) ? filterSymbol : symbolOptions[0] || "BTCUSDT"}
                      onChange={(event) => setFilterSymbol(event.target.value)}
                      className="w-32 rounded-lg border border-white/10 bg-slate-950/70 px-2 py-1.5 font-mono text-xs text-white outline-none focus:border-cyan-300/50"
                    >
                      {symbolOptions.map((symbol) => (
                        <option key={symbol} value={symbol}>
                          {symbol}
                        </option>
                      ))}
                    </select>
                    <Button size="sm" variant="outline" className="h-8 border-white/10 text-xs text-slate-200" onClick={fetchDecisions}>
                      筛选
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <Table>
                  <TableHeader>
                    <TableRow className="border-white/10 hover:bg-transparent">
                      <TableHead className="text-xs text-slate-400">交易对</TableHead>
                      <TableHead className="text-xs text-slate-400">建议</TableHead>
                      <TableHead className="text-xs text-slate-400">置信度</TableHead>
                      <TableHead className="text-xs text-slate-400">决策引擎</TableHead>
                      <TableHead className="text-xs text-slate-400">风险</TableHead>
                      <TableHead className="text-xs text-slate-400">时间</TableHead>
                      <TableHead className="w-10" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {decisions.length === 0 ? (
                      <TableRow className="border-white/10">
                        <TableCell colSpan={7} className="py-12 text-center text-sm text-slate-400">
                          暂无建议记录。点击上方“生成交易建议”后，这里会出现结果。
                        </TableCell>
                      </TableRow>
                    ) : (
                      decisions.map((decision) => {
                        const expanded = expandedId === decision.id;
                        const roles = decision.role_opinions?.length ? decision.role_opinions : decision.agent_signals;
                        return (
                          <Fragment key={decision.id}>
                            <TableRow
                              className="cursor-pointer border-white/10 hover:bg-white/[0.04]"
                              onClick={() => setExpandedId(expanded ? null : decision.id)}
                            >
                              <TableCell className="font-mono text-xs text-white">{decision.symbol}</TableCell>
                              <TableCell>
                                <Badge className={cn("border text-[11px]", signalBadgeClass(decision.final_signal))}>
                                  {decision.final_signal === "BUY" ? <ArrowUp className="mr-1 h-3 w-3" /> : decision.final_signal === "SELL" ? <ArrowDown className="mr-1 h-3 w-3" /> : <Minus className="mr-1 h-3 w-3" />}
                                  {signalLabel(decision.final_signal)}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-xs text-slate-200">{formatPercent(decision.confidence)}</TableCell>
                              <TableCell className="text-xs text-fuchsia-200">{primaryEngine(decision)}</TableCell>
                              <TableCell>
                                {decision.risk_veto ? (
                                  <Badge className="border border-rose-400/30 bg-rose-500/15 text-[11px] text-rose-200">
                                    <Shield className="mr-1 h-3 w-3" />
                                    已否决
                                  </Badge>
                                ) : (
                                  <span className="inline-flex items-center gap-1 text-xs text-slate-400">
                                    <CheckCircle2 className="h-3.5 w-3.5" />
                                    未触发
                                  </span>
                                )}
                              </TableCell>
                              <TableCell className="text-[11px] text-slate-400">
                                {decision.timestamp ? new Date(decision.timestamp).toLocaleString() : "-"}
                              </TableCell>
                              <TableCell>
                                {expanded ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
                              </TableCell>
                            </TableRow>
                            {expanded && (
                              <TableRow className="border-white/10 bg-slate-950/35">
                                <TableCell colSpan={7} className="p-4">
                                  <div className="grid gap-4 lg:grid-cols-2">
                                    <div className="rounded-2xl border border-fuchsia-400/20 bg-fuchsia-500/5 p-4 lg:col-span-2">
                                      <h4 className="text-sm font-semibold text-fuchsia-100">最终说明</h4>
                                      <p className="mt-2 text-sm leading-6 text-slate-200">{decision.summary || "本次决策没有返回说明。"}</p>
                                    </div>

                                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                                      <h4 className="text-sm font-semibold text-white">投票权重</h4>
                                      <div className="mt-3 space-y-3">
                                        {Object.entries(decision.vote_breakdown || {}).length === 0 ? (
                                          <p className="text-xs text-slate-500">无投票权重数据。</p>
                                        ) : (
                                          Object.entries(decision.vote_breakdown).map(([key, value]) => (
                                            <div key={key}>
                                              <div className="mb-1 flex items-center justify-between text-xs">
                                                <span className="text-slate-300">{VOTE_LABELS[key] || key}</span>
                                                <span className="font-mono text-slate-400">{formatPercent(value)}</span>
                                              </div>
                                              <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                                                <div
                                                  className="h-full rounded-full"
                                                  style={{
                                                    width: `${Math.max(0, Math.min(100, value * 100))}%`,
                                                    background: VOTE_COLORS[key] || "#38bdf8",
                                                  }}
                                                />
                                              </div>
                                            </div>
                                          ))
                                        )}
                                      </div>
                                    </div>

                                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                                      <h4 className="text-sm font-semibold text-white">本次参考材料</h4>
                                      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                                        <div className="rounded-xl bg-slate-950/60 p-3">
                                          <p className="text-slate-500">策略信号</p>
                                          <p className="mt-1 font-mono text-lg text-white">{contextCountFromKeyPoints(decision, "signals") ?? snapshotCount(decision.input_snapshot_ids, "signal_event_ids")}</p>
                                        </div>
                                        <div className="rounded-xl bg-slate-950/60 p-3">
                                          <p className="text-slate-500">技术因子</p>
                                          <p className="mt-1 font-mono text-lg text-white">{snapshotCount(decision.input_snapshot_ids, "factor_snapshot_ids")}</p>
                                        </div>
                                        <div className="rounded-xl bg-slate-950/60 p-3">
                                          <p className="text-slate-500">新闻</p>
                                          <p className="mt-1 font-mono text-lg text-white">{contextCountFromKeyPoints(decision, "news_events") ?? snapshotCount(decision.input_snapshot_ids, "news_payload_ids")}</p>
                                        </div>
                                        <div className="rounded-xl bg-slate-950/60 p-3">
                                          <p className="text-slate-500">宏观</p>
                                          <p className="mt-1 font-mono text-lg text-white">{contextCountFromKeyPoints(decision, "macro_events") ?? snapshotCount(decision.input_snapshot_ids, "macro_keys")}</p>
                                        </div>
                                      </div>
                                    </div>

                                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 lg:col-span-2">
                                      <h4 className="text-sm font-semibold text-white">模型和分析角色</h4>
                                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                                        {roles?.length ? roles.map((role, index) => (
                                          <div key={`${role.role || "role"}-${index}`} className="rounded-xl border border-white/10 bg-slate-950/45 p-3">
                                            <div className="flex items-start justify-between gap-3">
                                              <div>
                                                <p className="text-sm font-semibold text-slate-100">{roleLabel(role.role)}</p>
                                                <p className="mt-1 text-[11px] leading-5 text-slate-500">{roleDescription(role.role)}</p>
                                              </div>
                                              <Badge className="border border-slate-400/20 bg-slate-500/10 text-[11px] text-slate-300">
                                                {role.opinion || "wait"} · {roleScoreLabel(role.role)} {formatPercent(role.confidence)}
                                              </Badge>
                                            </div>
                                            <p className="mt-2 text-xs leading-5 text-slate-300">{role.reasoning || "暂无说明"}</p>
                                            {role.key_points?.length ? (
                                              <div className="mt-2 flex flex-wrap gap-1">
                                                {role.key_points.slice(0, 4).map((point) => (
                                                  <span key={point} className="rounded-full bg-cyan-400/10 px-2 py-1 text-[10px] text-cyan-200">
                                                    {point}
                                                  </span>
                                                ))}
                                              </div>
                                            ) : null}
                                          </div>
                                        )) : (
                                          <p className="text-xs text-slate-500">无角色结构化数据。</p>
                                        )}
                                      </div>
                                    </div>

                                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                                      <h4 className="text-sm font-semibold text-white">仓位建议</h4>
                                      <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-950/60 p-3 text-[11px] leading-5 text-slate-400">
                                        {JSON.stringify(decision.position_advice || {}, null, 2)}
                                      </pre>
                                    </div>
                                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                                      <h4 className="text-sm font-semibold text-white">风险备注</h4>
                                      <p className="mt-2 rounded-xl bg-slate-950/60 p-3 text-xs leading-5 text-slate-300">
                                        {decision.risk_notes || "本次没有明显风险备注。"}
                                      </p>
                                    </div>
                                  </div>
                                </TableCell>
                              </TableRow>
                            )}
                          </Fragment>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
                <p className="mt-3 text-[11px] text-slate-500">当前筛选返回 {decisions.length} 条记录。</p>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card className="border-white/10 bg-slate-900/60">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm text-white">
                  <PieChart className="h-4 w-4 text-fuchsia-300" />
                  历史建议分布
                </CardTitle>
                <p className="text-xs text-slate-500">统计系统最终给出的建议，不是底层策略的原始信号。</p>
              </CardHeader>
              <CardContent>
                {signalPieData.length === 0 ? (
                  <div className="py-10 text-center text-xs text-slate-500">暂无数据</div>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <RPieChart>
                      <Pie data={signalPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={78}>
                        {signalPieData.map((entry, index) => (
                          <Cell key={entry.raw} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,.12)", borderRadius: "12px", fontSize: "12px" }} />
                      <Legend />
                    </RPieChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card className="border-white/10 bg-slate-900/60">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm text-white">
                  <TrendingUp className="h-4 w-4 text-cyan-300" />
                  置信度趋势
                </CardTitle>
                <p className="text-xs text-slate-500">最近 30 条决策的 confidence。</p>
              </CardHeader>
              <CardContent>
                {confidenceTrendData.length === 0 ? (
                  <div className="py-10 text-center text-xs text-slate-500">暂无数据</div>
                ) : (
                  <ResponsiveContainer width="100%" height={210}>
                    <LineChart data={confidenceTrendData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,.16)" />
                      <XAxis dataKey="time" stroke="#64748b" fontSize={10} />
                      <YAxis stroke="#64748b" fontSize={10} domain={[0, 100]} />
                      <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,.12)", borderRadius: "12px", fontSize: "12px" }} />
                      <Line type="monotone" dataKey="confidence" stroke="#22d3ee" strokeWidth={2.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {loading && !stats && (
          <div className="flex items-center justify-center py-20 text-sm text-slate-400">
            <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
            加载中...
          </div>
        )}
      </main>
    </div>
  );
}
