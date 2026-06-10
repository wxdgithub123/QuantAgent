"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  RefreshCw, Filter, ArrowUp, ArrowDown, Minus, Info, Activity,
} from "lucide-react";

// New components
import { RulesViewer } from "@/components/signals/RulesViewer";
import { ResearchControls } from "@/components/signals/ResearchControls";
import { ResearchSummary } from "@/components/signals/ResearchSummary";
import { SignalDrawer } from "@/components/signals/SignalDrawer";
import { DiagnosticsPanel } from "@/components/signals/DiagnosticsPanel";
import { FactorTimeline } from "@/components/signals/FactorTimeline";

// ─── Types ──────────────────────────────────────────────────────────────────

interface FactorRow {
  id: number;
  symbol: string;
  timestamp: string | null;
  factor_name: string;
  factor_value: number;
  source: string;
  interval?: string | null;
  provider?: string | null;
  data_source?: string | null;
  schema_version?: string | null;
  available_time?: string | null;
  definition?: {
    display_name: string;
    category: string;
    unit: string;
  };
}

interface SignalEventRow {
  id: number;
  symbol: string;
  timestamp: string | null;
  event_time?: string | null;          // 事件发生时间
  available_time?: string | null;      // 系统可见时间
  as_of_time?: string | null;          // 查询时点
  signal_type: string;
  signal_value: number;
  confidence: number;
  source_strategy: string;
  strategy_id: string;
}

interface FactorDefinition {
  factor_name?: string;
  display_name: string;
  category: string;
  family?: string | null;
  description: string;
  calculation: string;
  upstream_data: string;
  provider_hint: string;
  unit: string;
}

interface SignalOverview {
  symbol: string;
  interval: string;
  as_of_time: string | null;
  total_signals: number;
  factor_snapshots: number;
  distinct_factors: number;
  latest_signal_at: string | null;
  by_signal_type: Record<string, number>;
  by_strategy: Record<string, number>;
  recent_strong_signals: Array<{
    id: number; symbol: string; signal_type: string;
    confidence: number; source_strategy: string; timestamp: string | null;
  }>;
  error?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function errorMessage(error: unknown) {
  const raw = error instanceof Error ? error.message : String(error || "");
  if (!raw || raw.includes("failed to fetch") || raw.includes("timeout") || raw.includes("abort") || raw.includes("http 5")) {
    return "数据暂不可用，已展示缓存数据 / 暂无数据。";
  }
  return raw.length > 120 ? "数据暂不可用，已展示缓存数据 / 暂无数据。" : raw;
}

function formatSourceLabel(value?: string | null) {
  if (!value) return "未记录";
  if (value === "indicators") return "内部指标计算";
  if (value === "l5_pipeline") return "L5 信号管线";
  if (value === "storage") return "行情缓存读取";
  if (value === "active-storage") return "当前行情库";
  if (value === "live-fetch") return "实时拉取后入库";
  return value;
}

function formatProviderLabel(value?: string | null) {
  if (!value) return "未记录来源";
  // 数据平台 PRD M5.8 定义的 provider 名称映射
  const PROVIDER_MAP: Record<string, string> = {
    "active-storage": "本地缓存",
    "openbb:yfinance": "YFinance (OpenBB)",
    "openbb:fred": "FRED (OpenBB)",
    "openbb:oecd": "OECD (OpenBB)",
    "openbb:binance": "Binance (OpenBB)",
    "ccxt:binance": "Binance (CCXT)",
    "ccxt:okx": "OKX (CCXT)",
    "ccxt": "CCXT",
    "binance": "Binance",
    "okx": "OKX",
    "yfinance": "YFinance",
    "fred": "FRED",
    "macro": "宏观数据源",
  };
  return PROVIDER_MAP[value] || value;
}

/**
 * 通用 API 响应解析器：兼容数据平台 PRD M5.1 统一格式 {data, meta, errors}
 * 和当前后端扁平格式。返回 {data, meta, errors} 三元组。
 */
async function parseApiResponse<T>(res: Response): Promise<{ data: T[]; meta: Record<string, unknown>; errors: string[] }> {
  const json = await res.json();
  // 数据平台 PRD 格式: { data: [...], meta: {...}, errors: [...] }
  if (json && "data" in json && Array.isArray(json.data)) {
    return {
      data: json.data as T[],
      meta: (json.meta as Record<string, unknown>) || {},
      errors: (json.errors as string[]) || [],
    };
  }
  // 当前后端扁平格式：直接是数组或对象带 data 属性
  if (Array.isArray(json)) {
    return { data: json as T[], meta: {}, errors: [] };
  }
  // 兼容部分接口的 { data: [...], total: N } 格式
  if (json && Array.isArray(json.data)) {
    return { data: json.data as T[], meta: { total: json.total }, errors: [] };
  }
  // 空响应或对象响应
  if (json && typeof json === "object" && !json.error) {
    return { data: [], meta: json as Record<string, unknown>, errors: json.error ? [json.error] : [] };
  }
  return { data: [], meta: {}, errors: json?.error ? [json.error] : [] };
}

function formatFactorValue(value: number | undefined) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "-";
  const n = Number(value);
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function SignalsPage() {
  // Research context — 支持从 URL 参数读取初始交易对
  const [symbol, setSymbol] = useState(() => {
    if (typeof window !== "undefined") {
      const p = new URLSearchParams(window.location.search);
      return p.get("symbol") || "BTCUSDT";
    }
    return "BTCUSDT";
  });
  const [interval, setInterval] = useState("1h");
  const [asOfTime, setAsOfTime] = useState(() => {
    if (typeof window !== "undefined") {
      const p = new URLSearchParams(window.location.search);
      return p.get("as_of_time") || "";
    }
    return "";
  });
  const [appliedAsOf, setAppliedAsOf] = useState("");
  const [replayMode, setReplayMode] = useState(false);
  const [timeSuggestions, setTimeSuggestions] = useState<string[]>([]);
  const [showTimeline, setShowTimeline] = useState(false);

  // Data
  const [factors, setFactors] = useState<FactorRow[]>([]);
  const [events, setEvents] = useState<SignalEventRow[]>([]);
  const [factorDefinitions, setFactorDefinitions] = useState<FactorDefinition[]>([]);
  const [signalOverview, setSignalOverview] = useState<SignalOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Filters
  const [factorSearch, setFactorSearch] = useState("");
  const [factorCategory, setFactorCategory] = useState("all");
  const [factorSource, setFactorSource] = useState("all");
  const [signalTypeFilter, setSignalTypeFilter] = useState("all");
  const [factorPage, setFactorPage] = useState(0);
  const [signalPage, setSignalPage] = useState(0);
  const [providerOptions, setProviderOptions] = useState<string[]>([]);
  const PAGE_SIZE = 50;

  // Signal detail drawer
  const [selectedSignalId, setSelectedSignalId] = useState<number | null>(null);

  // Factor definitions map
  const defMap = factorDefinitions.reduce<Record<string, FactorDefinition>>((acc, d) => {
    if (d.factor_name) acc[d.factor_name] = d;
    return acc;
  }, {});

  // ── Data Fetching ──────────────────────────────────────────────────────────

  const fetchFactorDefinitions = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/signals/factor-definitions");
      if (res.ok) {
        const { data } = await parseApiResponse<FactorDefinition>(res);
        setFactorDefinitions(data || []);
      }
    } catch { /* silent */ }
  }, []);

  const fetchProviders = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/meta/providers");
      if (res.ok) {
        const { data } = await parseApiResponse<{ name: string }>(res);
        setProviderOptions(data.map((p) => p.name));
      }
    } catch {
      // 数据平台 API 尚未就绪，使用 PRD M5.8 定义的默认 provider 列表
      setProviderOptions(["OpenBB", "Binance", "FRED", "CCXT", "内部指标计算", "实时拉取"]);
    }
  }, []);

  const fetchFactors = useCallback(async () => {
    try {
      const params = new URLSearchParams({ symbol, interval, limit: String(PAGE_SIZE), offset: String(factorPage * PAGE_SIZE) });
      if (factorSearch) params.set("factor_name", factorSearch);
      if (appliedAsOf) params.set("as_of_time", appliedAsOf);
      const res = await fetch(`/api/v1/signals/factors?${params}`);
      if (res.ok) {
        const { data } = await parseApiResponse<FactorRow>(res);
        setFactors(data || []);
      }
    } catch (e: unknown) { setError(errorMessage(e)); }
  }, [symbol, interval, appliedAsOf, factorSearch, factorPage]);

  const fetchEvents = useCallback(async () => {
    try {
      const params = new URLSearchParams({ symbol, interval, limit: String(PAGE_SIZE), offset: String(signalPage * PAGE_SIZE) });
      if (signalTypeFilter !== "all") params.set("signal_type", signalTypeFilter);
      if (appliedAsOf) params.set("as_of_time", appliedAsOf);
      const res = await fetch(`/api/v1/signals/events?${params}`);
      if (res.ok) {
        const { data } = await parseApiResponse<SignalEventRow>(res);
        setEvents(data || []);
      }
    } catch (e: unknown) { setError(errorMessage(e)); }
  }, [symbol, interval, appliedAsOf, signalTypeFilter, signalPage]);

  const fetchSignalOverview = useCallback(async () => {
    try {
      const params = new URLSearchParams({ symbol, interval });
      if (appliedAsOf) params.set("as_of_time", appliedAsOf);
      const res = await fetch(`/api/v1/signals/overview?${params}`);
      if (res.ok) {
        const { data, meta, errors } = await parseApiResponse<SignalOverview>(res);
        if (errors.length === 0 && meta && Object.keys(meta).length > 0) {
          // 如果 meta 中直接包含 overview 数据（当前后端格式）
          setSignalOverview(meta as unknown as SignalOverview);
        } else if (data.length > 0) {
          setSignalOverview(data[0] as unknown as SignalOverview);
        }
      }
    } catch {
      setSignalOverview(null);
    }
  }, [symbol, interval, appliedAsOf]);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([fetchFactors(), fetchEvents(), fetchSignalOverview(), fetchFactorDefinitions()]);
    } finally { setLoading(false); }
  }, [fetchFactors, fetchEvents, fetchSignalOverview, fetchFactorDefinitions]);

  // ── Effects ────────────────────────────────────────────────────────────────

  useEffect(() => { fetchFactorDefinitions(); }, [fetchFactorDefinitions]);
  useEffect(() => { fetchProviders(); }, [fetchProviders]);
  useEffect(() => { fetchFactors(); }, [fetchFactors]);
  useEffect(() => { fetchEvents(); }, [fetchEvents]);
  useEffect(() => { fetchSignalOverview(); }, [fetchSignalOverview]);

  // Fetch time suggestions from recent events
  useEffect(() => {
    fetch("/api/v1/signals/events?symbol=BTCUSDT&interval=1h&limit=10")
      .then((r) => r.ok ? r.json() : null)
      .then((d) => {
        if (!d?.data) return;
        const times: string[] = d.data
          .map((e: { timestamp?: string }) => e.timestamp)
          .filter(Boolean)
          .slice(0, 8);
        setTimeSuggestions(times);
      })
      .catch(() => {});
  }, []);

  // Auto-apply as_of_time from URL on mount
  useEffect(() => {
    if (asOfTime) handleApply();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleApply = () => {
    if (!asOfTime.trim()) { setAppliedAsOf(""); return; }
    const raw = asOfTime.trim();
    const candidate = raw.includes("T") ? raw : raw.replace(" ", "T");
    const d = new Date(candidate);
    if (Number.isNaN(d.getTime())) { setError("时间格式无法识别，请使用 YYYY-MM-DD HH:mm 格式"); return; }
    setAppliedAsOf(d.toISOString());
  };

  const handleClear = () => {
    setAsOfTime("");
    setAppliedAsOf("");
    setFactorSearch("");
    setFactorCategory("all");
    setFactorSource("all");
    setSignalTypeFilter("all");
    setFactorPage(0);
    setSignalPage(0);
    setError("");
  };

  // Filtered factors
  const filteredFactors = factors.filter((f) => {
    const def = f.definition || defMap[f.factor_name];
    if (factorCategory !== "all") {
      const cat = def?.category || "未分类";
      if (cat !== factorCategory) return false;
    }
    if (factorSource !== "all") {
      const src = f.source || "未记录";
      if (src !== factorSource) return false;
    }
    return true;
  });

  const factorCategories = Array.from(new Set(
    [...factorDefinitions, ...factors.map(f => f.definition || defMap[f.factor_name])].filter(Boolean).map(d => d?.category).filter(Boolean)
  )) as string[];

  return (
    <div className="min-h-screen bg-background">
      {/* ── Header ── */}
      <AppTopNav
        activeSection="signals"
        title="因子/信号研究"
        subtitle="查看因子定义、策略关系，并按交易对和时间回看实际因子与信号。"
        rightSlot={
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 text-muted-foreground hover:text-foreground"
            onClick={() => { void refreshAll(); }}
          >
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
          </Button>
        }
      />

      <main className="container mx-auto px-4 py-6 space-y-6">
        {/* Error banner */}
        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-xs flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError("")} className="text-red-400/70 hover:text-red-300">✕</button>
          </div>
        )}

        {/* ── Section 1: Rules Viewer ── */}
        <section>
          <RulesViewer />
        </section>

        {/* ── Section 2: Research Controls ── */}
        <section>
          <ResearchControls
            symbol={symbol}
            interval={interval}
            asOfTime={asOfTime}
            appliedAsOf={appliedAsOf}
            replayMode={replayMode}
            timeSuggestions={timeSuggestions}
            onSymbolChange={setSymbol}
            onIntervalChange={setInterval}
            onAsOfTimeChange={setAsOfTime}
            onApply={handleApply}
            onClear={handleClear}
            onReplayModeChange={setReplayMode}
          />
        </section>

        {/* ── Section 3: Research Summary ── */}
        <section>
          <ResearchSummary symbol={symbol} interval={interval} appliedAsOf={appliedAsOf} />
        </section>

        {/* ── Section 4: Signal Overview + Strong Signals ── */}
        {signalOverview && !signalOverview.error && (
          <section className="space-y-4">
            {/* Recent strong signals */}
            {signalOverview.recent_strong_signals.length > 0 && (
              <Card className="border-purple-500/20 bg-card/80">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-foreground">最近强信号</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-2">
                    {signalOverview.recent_strong_signals.map((sig) => (
                      <Badge
                        key={sig.id}
                        className={cn(
                          "cursor-pointer text-xs px-3 py-1.5 hover:opacity-80 transition-opacity",
                          sig.signal_type === "BUY"
                            ? "bg-green-500/15 text-green-400 border-green-500/25"
                            : "bg-red-500/15 text-red-400 border-red-500/25"
                        )}
                        onClick={() => setSelectedSignalId(sig.id)}
                      >
                        {sig.signal_type} · {sig.source_strategy} · {(sig.confidence * 100).toFixed(0)}%
                        {sig.timestamp ? ` · ${new Date(sig.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}` : ""}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </section>
        )}

        {/* ── Section 5: Factor Snapshots Table ── */}
        <section>
          <Card className="border-blue-500/20">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <CardTitle className="text-sm text-foreground">因子快照</CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    每行是交易对在某个时间点的具体因子值。使用上方搜索和分类筛选精准定位。
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowTimeline(!showTimeline)}
                    className={cn(
                      "h-7 text-[10px] border-border mt-2",
                      showTimeline
                        ? "bg-cyan-500/10 text-cyan-400 border-cyan-500/25"
                        : "text-muted-foreground"
                    )}
                  >
                    <Activity className="w-3 h-3 mr-1" />
                    {showTimeline ? "隐藏时间轴" : "时间轴"}
                  </Button>
                </div>
                <Badge className="bg-blue-500/10 text-blue-300 border-blue-500/20 text-[10px]">
                  {factors.length} 条记录
                </Badge>
              </div>

              {/* Factor Timeline (toggleable) */}
              {showTimeline && (
                <div className="mt-3">
                  <FactorTimeline symbol={symbol} interval={interval} />
                </div>
              )}

              {/* Filters */}
              <div className="flex flex-wrap items-center gap-2 mt-3">
                <Filter className="w-3.5 h-3.5 text-muted-foreground" />
                <input
                  placeholder="搜索因子代码 (如 sma_10)"
                  value={factorSearch}
                  onChange={(e) => { setFactorSearch(e.target.value); setFactorPage(0); }}
                  className="bg-secondary border border-border text-foreground text-xs rounded px-2.5 py-1.5 w-52 focus:outline-none focus:border-blue-500/50"
                />
                <Select value={factorCategory} onValueChange={(v) => { setFactorCategory(v); setFactorPage(0); }}>
                  <SelectTrigger className="h-8 w-36 bg-secondary border-border text-xs">
                    <SelectValue placeholder="分类" />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    <SelectItem value="all" className="text-xs">全部分类</SelectItem>
                    {factorCategories.map((cat) => (
                      <SelectItem key={cat} value={cat} className="text-xs">{cat}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={factorSource} onValueChange={(v) => { setFactorSource(v); setFactorPage(0); }}>
                  <SelectTrigger className="h-8 w-36 bg-secondary border-border text-xs">
                    <SelectValue placeholder="来源" />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    <SelectItem value="all" className="text-xs">全部来源</SelectItem>
                    {providerOptions.map((p) => (
                      <SelectItem key={p} value={p.toLowerCase()} className="text-xs">{p}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader className="bg-card">
                    <TableRow className="border-border">
                      <TableHead className="text-muted-foreground text-xs w-[90px]">交易对</TableHead>
                      <TableHead className="text-muted-foreground text-xs">因子</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[80px]">分类</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[140px]">当前值</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[100px]">计算来源</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[120px]">上游来源</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[90px]">版本</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[140px]">可用时间</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[140px]">记录时间</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      Array.from({ length: 5 }).map((_, i) => (
                        <TableRow key={i} className="border-border">
                          {Array.from({ length: 9 }).map((_, j) => (
                            <TableCell key={j}><Skeleton className="h-3 w-16" /></TableCell>
                          ))}
                        </TableRow>
                      ))
                    ) : filteredFactors.length === 0 ? (
                      <TableRow className="border-border">
                        <TableCell colSpan={9} className="text-center text-muted-foreground py-12 text-sm">
                          <Info className="w-8 h-8 mx-auto mb-2 opacity-30" />
                          暂无因子快照数据 — 请先确认已运行信号管线，或调整筛选条件
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredFactors.map((f) => {
                        const def = f.definition || defMap[f.factor_name];
                        return (
                          <TableRow key={f.id} className="border-border hover:bg-card/50">
                            <TableCell className="text-foreground/90 text-xs font-mono">{f.symbol}</TableCell>
                            <TableCell>
                              <div className="text-blue-300 text-xs font-medium">{def?.display_name || f.factor_name}</div>
                              <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">{f.factor_name}</div>
                            </TableCell>
                            <TableCell>
                              <Badge className="bg-muted text-muted-foreground text-[10px]">
                                {def?.category || "未分类"}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-foreground/90 text-xs font-mono">
                              {formatFactorValue(f.factor_value)}
                              {def?.unit ? <span className="ml-1 text-[10px] text-muted-foreground">{def.unit}</span> : null}
                            </TableCell>
                            <TableCell className="text-muted-foreground text-xs">
                              <div>{formatSourceLabel(f.source)}</div>
                              {f.interval ? <div className="mt-0.5 text-[10px] text-muted-foreground/70">{f.interval}</div> : null}
                            </TableCell>
                            <TableCell className="text-muted-foreground text-xs">
                              <div>{formatProviderLabel(f.provider)}</div>
                              <div className="mt-0.5 text-[10px] text-muted-foreground/70">{formatSourceLabel(f.data_source)}</div>
                            </TableCell>
                            <TableCell className="text-muted-foreground text-[10px] font-mono">
                              {f.schema_version || "—"}
                            </TableCell>
                            <TableCell className="text-muted-foreground text-[11px]">
                              {f.available_time ? new Date(f.available_time).toLocaleString("zh-CN") : "—"}
                            </TableCell>
                            <TableCell className="text-muted-foreground text-[11px]">
                              {f.timestamp ? new Date(f.timestamp).toLocaleString("zh-CN") : "-"}
                            </TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
              {/* Pagination */}
              {factors.length > 0 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-border">
                  <p className="text-[10px] text-muted-foreground">
                    共 {filteredFactors.length} 条记录 (当前页)
                  </p>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs border-border"
                      disabled={factorPage === 0}
                      onClick={() => setFactorPage((p) => Math.max(0, p - 1))}
                    >
                      上一页
                    </Button>
                    <span className="text-[10px] text-muted-foreground">第 {factorPage + 1} 页</span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs border-border"
                      disabled={factors.length < PAGE_SIZE}
                      onClick={() => setFactorPage((p) => p + 1)}
                    >
                      下一页
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        {/* ── Section 6: Signal Events Table ── */}
        <section>
          <Card className="border-purple-500/20">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <CardTitle className="text-sm text-foreground">信号事件</CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    每个信号由特定策略根据因子值生成。点击「详情」查看证据链。
                  </p>
                </div>
                <Badge className="bg-purple-500/10 text-purple-300 border-purple-500/20 text-[10px]">
                  {events.length} 条记录
                </Badge>
              </div>

              {/* Signal type filter */}
              <div className="flex items-center gap-2 mt-3">
                <Filter className="w-3.5 h-3.5 text-muted-foreground" />
                <Select value={signalTypeFilter} onValueChange={(v) => { setSignalTypeFilter(v); setSignalPage(0); }}>
                  <SelectTrigger className="h-8 w-28 bg-secondary border-border text-xs">
                    <SelectValue placeholder="信号类型" />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-border">
                    <SelectItem value="all" className="text-xs">全部</SelectItem>
                    <SelectItem value="BUY" className="text-green-400 text-xs">🟢 BUY</SelectItem>
                    <SelectItem value="SELL" className="text-red-400 text-xs">🔴 SELL</SelectItem>
                    <SelectItem value="WAIT" className="text-muted-foreground text-xs">🔵 WAIT</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader className="bg-card">
                    <TableRow className="border-border">
                      <TableHead className="text-muted-foreground text-xs w-[80px]">Symbol</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[80px]">信号</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[80px]">置信度</TableHead>
                      <TableHead className="text-muted-foreground text-xs">策略</TableHead>
                      <TableHead className="text-muted-foreground text-xs">触发原因</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[140px]">事件时间</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[140px]">触发时间</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-[80px]">详情</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      Array.from({ length: 5 }).map((_, i) => (
                        <TableRow key={i} className="border-border">
                          {Array.from({ length: 8 }).map((_, j) => (
                            <TableCell key={j}><Skeleton className="h-3 w-14" /></TableCell>
                          ))}
                        </TableRow>
                      ))
                    ) : events.length === 0 ? (
                      <TableRow className="border-border">
                        <TableCell colSpan={8} className="text-center text-muted-foreground py-12 text-sm">
                          <Info className="w-8 h-8 mx-auto mb-2 opacity-30" />
                          暂无信号事件数据 — 请先运行信号管线
                        </TableCell>
                      </TableRow>
                    ) : (
                      events.map((ev) => (
                        <TableRow key={ev.id} className="border-border hover:bg-card/50">
                          <TableCell className="text-foreground/90 text-xs font-mono">{ev.symbol}</TableCell>
                          <TableCell>
                            <Badge className={cn(
                              "text-[10px]",
                              ev.signal_type === "BUY" ? "bg-green-500/15 text-green-400" :
                              ev.signal_type === "SELL" ? "bg-red-500/15 text-red-400" :
                              "bg-muted text-muted-foreground"
                            )}>
                              {ev.signal_type === "BUY" ? <ArrowUp className="w-3 h-3 mr-0.5" /> :
                               ev.signal_type === "SELL" ? <ArrowDown className="w-3 h-3 mr-0.5" /> :
                               <Minus className="w-3 h-3 mr-0.5" />}
                              {ev.signal_type}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-foreground/90 text-xs">{(ev.confidence * 100).toFixed(1)}%</TableCell>
                          <TableCell className="text-muted-foreground text-xs">{ev.source_strategy}</TableCell>
                          <TableCell className="text-muted-foreground text-xs max-w-[180px] truncate">
                            {ev.strategy_id ? `${ev.strategy_id} 策略触发` : "—"}
                          </TableCell>
                          <TableCell className="text-muted-foreground text-[11px]">
                            {/* TODO: 待后端补充 event_time 字段，当前使用 timestamp 作为事件时间 */}
                            {ev.event_time
                              ? new Date(ev.event_time).toLocaleString("zh-CN")
                              : ev.timestamp
                                ? new Date(ev.timestamp).toLocaleString("zh-CN")
                                : "—"}
                          </TableCell>
                          <TableCell className="text-muted-foreground text-[11px]">
                            {ev.timestamp ? new Date(ev.timestamp).toLocaleString("zh-CN") : "-"}
                          </TableCell>
                          <TableCell>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 text-[10px] border-border text-muted-foreground hover:text-foreground"
                              onClick={() => setSelectedSignalId(ev.id)}
                            >
                              详情
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
              {/* Pagination */}
              {events.length > 0 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-border">
                  <p className="text-[10px] text-muted-foreground">共 {events.length} 条记录 (当前页)</p>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" className="h-7 text-xs border-border" disabled={signalPage === 0} onClick={() => setSignalPage((p) => Math.max(0, p - 1))}>上一页</Button>
                    <span className="text-[10px] text-muted-foreground">第 {signalPage + 1} 页</span>
                    <Button variant="outline" size="sm" className="h-7 text-xs border-border" disabled={events.length < PAGE_SIZE} onClick={() => setSignalPage((p) => p + 1)}>下一页</Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        {/* ── Loading overlay ── */}
        {loading && (
          <div className="flex items-center justify-center py-6 text-muted-foreground text-sm">
            <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
          </div>
        )}

        {/* ── Section 7: Diagnostics ── */}
        <section>
          <DiagnosticsPanel />
        </section>
      </main>

      {/* ── Signal Detail Drawer ── */}
      <SignalDrawer
        signalId={selectedSignalId}
        symbol={symbol}
        onClose={() => setSelectedSignalId(null)}
      />
    </div>
  );
}
