"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Prd104StatusPanel } from "@/components/prd/Prd104StatusPanel";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import {
  Activity, BarChart3, BarChart, History, Server, RefreshCw,
  TrendingUp, Layers, Filter, PieChart, ArrowUp, ArrowDown,
  Minus, Shield,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart as RPieChart, Pie, Cell, BarChart as RBarChart, Bar, Legend,
} from "recharts";

// ─── Types ──────────────────────────────────────────────────────────────────

interface FactorRow {
  id: number;
  symbol: string;
  timestamp: string | null;
  factor_name: string;
  factor_value: number;
  parameters: Record<string, unknown>;
  source: string;
  interval?: string | null;
  provider?: string | null;
  data_source?: string | null;
  definition?: FactorDefinition;
}

interface SignalRow {
  id: number;
  symbol: string;
  timestamp: string | null;
  signal_type: string;
  signal_value: number;
  confidence: number;
  source_strategy: string;
  strategy_id: string;
  factors: Record<string, number>;
}

interface FactorSeriesPoint {
  timestamp: string | null;
  value: number;
  parameters: Record<string, unknown>;
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
  default_interval?: string | null;
  snapshot_count?: number;
  symbol_count?: number;
  latest_timestamp?: string | null;
  observed_providers?: string[];
  observed_data_sources?: string[];
}

interface Summary {
  factor_total: number;
  distinct_factor_count?: number;
  event_total: number;
  recent_7d: number;
  by_signal_type: Record<string, number>;
  by_strategy: Record<string, number>;
  by_symbol: Record<string, number>;
  by_factor_category?: Record<string, number>;
  error?: string;
}

const PIE_COLORS = ["#22c55e", "#ef4444", "#94a3b8", "#3b82f6", "#f59e0b", "#8b5cf6", "#ec4899"];

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function formatSourceLabel(value?: string | null) {
  if (!value) return "未记录";
  if (value === "indicators") return "内部指标计算";
  if (value === "l5_pipeline") return "L5因子流水线";
  if (value === "storage") return "行情缓存读取";
  if (value === "active-storage") return "当前行情库";
  if (value === "live-fetch") return "实时拉取后入库";
  return value;
}

function formatProviderLabel(value?: string | null) {
  if (!value) return "未记录上游来源";
  if (value === "active-storage") return "行情库缓存";
  if (value === "openbb:yfinance") return "OpenBB / yfinance";
  if (value === "openbb:fred") return "OpenBB / FRED";
  if (value === "openbb:oecd") return "OpenBB / OECD";
  if (value === "ccxt") return "CCXT";
  return value;
}

function formatFactorValue(value: number | undefined) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "-";
  const numeric = Number(value);
  if (Math.abs(numeric) >= 1000) return numeric.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function SignalsPage() {
  const [tab, setTab] = useState("definitions");
  const [factors, setFactors] = useState<FactorRow[]>([]);
  const [factorDefinitions, setFactorDefinitions] = useState<FactorDefinition[]>([]);
  const [events, setEvents] = useState<SignalRow[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [factorSeries, setFactorSeries] = useState<FactorSeriesPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Filters
  const [filterSymbol, setFilterSymbol] = useState("");
  const [filterFactor, setFilterFactor] = useState("");
  const [filterSignalType, setFilterSignalType] = useState("");
  const [seriesSymbol, setSeriesSymbol] = useState("BTCUSDT");
  const [seriesFactor, setSeriesFactor] = useState("sma_10");

  const fetchFactorDefinitions = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/signals/factor-definitions");
      if (res.ok) {
        const d = await res.json();
        setFactorDefinitions(d.data || []);
      }
    } catch (e: unknown) { setError(errorMessage(e)); }
  }, []);

  const fetchFactors = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (filterSymbol) params.set("symbol", filterSymbol);
      if (filterFactor) params.set("factor_name", filterFactor);
      const res = await fetch(`/api/v1/signals/factors?${params}`);
      if (res.ok) {
        const d = await res.json();
        setFactors(d.data || []);
      }
    } catch (e: unknown) { setError(errorMessage(e)); }
  }, [filterSymbol, filterFactor]);

  const fetchEvents = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (filterSymbol) params.set("symbol", filterSymbol);
      if (filterSignalType && filterSignalType !== "all") params.set("signal_type", filterSignalType);
      const res = await fetch(`/api/v1/signals/events?${params}`);
      if (res.ok) {
        const d = await res.json();
        setEvents(d.data || []);
      }
    } catch (e: unknown) { setError(errorMessage(e)); }
  }, [filterSymbol, filterSignalType]);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/signals/summary");
      if (res.ok) setSummary(await res.json());
    } catch { /* ignore */ }
  }, []);

  const fetchSeries = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/signals/factors/${seriesSymbol}/${seriesFactor}/series?limit=500`);
      if (res.ok) {
        const d = await res.json();
        setFactorSeries(d.data || []);
      }
    } catch (e: unknown) { setError(errorMessage(e)); }
  }, [seriesSymbol, seriesFactor]);

  useEffect(() => { fetchFactors(); fetchEvents(); fetchSummary(); fetchFactorDefinitions(); }, [fetchFactors, fetchEvents, fetchSummary, fetchFactorDefinitions]);

  const pieData = summary ? Object.entries(summary.by_signal_type || {}).map(([k, v]) => ({ name: k, value: v })) : [];
  const strategyBarData = summary ? Object.entries(summary.by_strategy || {}).map(([k, v]) => ({ name: k, count: v })) : [];
  const factorCategoryData = summary ? Object.entries(summary.by_factor_category || {}).map(([name, value]) => ({ name, value })) : [];
  const factorDefinitionMap = factorDefinitions.reduce<Record<string, FactorDefinition>>((acc, item) => {
    if (item.factor_name) acc[item.factor_name] = item;
    return acc;
  }, {});

  const chartData = factorSeries.map((p) => ({
    time: p.timestamp ? new Date(p.timestamp).toLocaleDateString() : "",
    value: p.value,
  })).slice(-100);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([fetchFactors(), fetchEvents(), fetchSummary(), fetchFactorDefinitions()]);
    } finally {
      setLoading(false);
    }
  }, [fetchFactorDefinitions, fetchFactors, fetchEvents, fetchSummary]);

  return (
    <div className="min-h-screen bg-background">
      {/* ── Header ── */}
      <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-40">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-foreground">QuantAgent OS</h1>
                <p className="text-[10px] text-muted-foreground">AI-Native Quantitative Trading</p>
              </div>
            </div>
            <nav className="hidden md:flex items-center gap-1">
              <Link href="/dashboard" className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg transition-all">仪表盘</Link>
              <Link href="/trades" className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg transition-all flex items-center gap-1.5"><Activity className="w-4 h-4" /> 交易流水</Link>
              <Link href="/analytics" className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg transition-all flex items-center gap-1.5"><BarChart className="w-4 h-4" /> 性能分析</Link>
              <Link href="/replay" className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg transition-all flex items-center gap-1.5"><History className="w-4 h-4" /> 历史回放</Link>
              <Link href="/terminal" className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg transition-all">终端</Link>
              <Link href="/hummingbot" className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg transition-all flex items-center gap-1.5"><Server className="w-4 h-4" /> Hummingbot</Link>
              <Link href="/signals" className="px-3 py-1.5 text-sm text-orange-400 bg-orange-500/10 rounded-lg border border-orange-500/20 font-medium flex items-center gap-1.5"><Layers className="w-4 h-4" /> 因子/信号</Link>
              <Link href="/audit" className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg transition-all flex items-center gap-1.5"><Shield className="w-4 h-4" /> 回测与审计</Link>
            </nav>
            <div className="flex items-center gap-2">
              <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-foreground" onClick={() => { void refreshAll(); }}>
                <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* ── Main ── */}
      <main className="container mx-auto px-4 py-6">
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-xs">{error}</div>
        )}

        <Prd104StatusPanel className="mb-6" />

        {/* Summary cards */}
        {summary && !summary.error && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <Card className="bg-card border-border">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">因子种类</p>
                <p className="text-2xl font-bold text-blue-400 mt-1">{summary.distinct_factor_count ?? factorDefinitions.length}</p>
                <p className="mt-1 text-[10px] text-muted-foreground">不是记录数，是不同因子名称数量</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">因子快照</p>
                <p className="text-2xl font-bold text-purple-400 mt-1">{summary.factor_total}</p>
                <p className="mt-1 text-[10px] text-muted-foreground">所有币种和时间点的明细记录</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">信号事件</p>
                <p className="text-2xl font-bold text-green-400 mt-1">{summary.event_total}</p>
                <p className="mt-1 text-[10px] text-muted-foreground">策略根据因子生成的方向判断</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">近7天信号</p>
                <p className="text-2xl font-bold text-green-400 mt-1">{summary.recent_7d}</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">交易对</p>
                <p className="text-2xl font-bold text-cyan-400 mt-1">{Object.keys(summary.by_symbol || {}).length}</p>
              </CardContent>
            </Card>
          </div>
        )}

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-card border border-border mb-6">
            <TabsTrigger value="definitions" className="text-muted-foreground data-[state=active]:text-emerald-400">因子字典</TabsTrigger>
            <TabsTrigger value="factors" className="text-muted-foreground data-[state=active]:text-blue-400">因子快照</TabsTrigger>
            <TabsTrigger value="events" className="text-muted-foreground data-[state=active]:text-purple-400">信号事件</TabsTrigger>
            <TabsTrigger value="series" className="text-muted-foreground data-[state=active]:text-cyan-400">因子时序图</TabsTrigger>
            <TabsTrigger value="summary" className="text-muted-foreground data-[state=active]:text-orange-400">汇总统计</TabsTrigger>
          </TabsList>

          {/* ── Definitions Tab ── */}
          <TabsContent value="definitions" className="space-y-4">
            <Card className="border-emerald-500/20 bg-emerald-500/5">
              <CardContent className="p-4">
                <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-foreground">因子字典说明</h2>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      这里列的是系统当前认识的“因子类型”。因子快照表里的每一行，是某个交易对在某个时间点算出来的一次数值。
                      所以“33个因子类型”和“几万条因子快照”不是一回事。
                    </p>
                  </div>
                  <Badge className="w-fit bg-emerald-500/15 text-emerald-300">
                    当前 {factorDefinitions.length} 个定义
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {factorDefinitions.length === 0 ? (
                <Card className="md:col-span-2 xl:col-span-3 bg-card border-border">
                  <CardContent className="py-12 text-center text-sm text-muted-foreground">暂无因子字典数据</CardContent>
                </Card>
              ) : (
                factorDefinitions.map((item) => (
                  <Card key={item.factor_name} className="bg-card border-border/70">
                    <CardContent className="p-4">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-sm font-semibold text-foreground">{item.display_name}</h3>
                            <Badge className="bg-slate-500/10 text-slate-300">{item.category}</Badge>
                          </div>
                          <p className="mt-1 font-mono text-[11px] text-blue-300">{item.factor_name}</p>
                        </div>
                        <p className="text-right text-[11px] text-muted-foreground">
                          快照 {item.snapshot_count?.toLocaleString() ?? 0}
                        </p>
                      </div>
                      <p className="text-xs leading-5 text-muted-foreground">{item.description}</p>
                      <div className="mt-3 space-y-2 text-[11px] leading-5 text-muted-foreground">
                        <p><span className="text-foreground/80">怎么算：</span>{item.calculation}</p>
                        <p><span className="text-foreground/80">使用数据：</span>{item.upstream_data}</p>
                        <p><span className="text-foreground/80">来源说明：</span>{item.provider_hint}</p>
                        <p>
                          <span className="text-foreground/80">实际记录：</span>
                          {(item.observed_providers || []).length > 0
                            ? item.observed_providers?.map(formatProviderLabel).join("、")
                            : "还没有快照记录"}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </TabsContent>

          {/* ── Factors Tab ── */}
          <TabsContent value="factors" className="space-y-4">
            <Card className="border-blue-500/20 bg-blue-500/5">
              <CardContent className="p-4">
                <p className="text-xs leading-5 text-muted-foreground">
                  因子快照是“某个交易对在某个时间点的具体因子值”。表里的“计算来源”说明是谁生成了这个因子，
                  “上游来源”才是它背后的行情、新闻或宏观数据来源；如果显示未记录，说明这是早期旧数据，没有完整来源字段。
                </p>
              </CardContent>
            </Card>
            <div className="flex items-center gap-3 flex-wrap">
              <Filter className="w-4 h-4 text-muted-foreground" />
              <input
                placeholder="交易对，例如 BTCUSDT" value={filterSymbol} onChange={(e) => setFilterSymbol(e.target.value.toUpperCase())}
                className="bg-secondary border border-border text-foreground/90 text-xs rounded px-2 py-1.5 w-40"
              />
              <input
                placeholder="因子代码，例如 sma_10" value={filterFactor} onChange={(e) => setFilterFactor(e.target.value)}
                className="bg-secondary border border-border text-foreground/90 text-xs rounded px-2 py-1.5 w-48"
              />
              <Button size="sm" variant="outline" className="h-7 text-xs border-border text-foreground/80" onClick={fetchFactors}>筛选</Button>
            </div>
            <div className="rounded-lg border border-border overflow-hidden">
              <Table>
                <TableHeader className="bg-card">
                  <TableRow className="border-border">
                    <TableHead className="text-muted-foreground text-xs">交易对</TableHead>
                    <TableHead className="text-muted-foreground text-xs">因子</TableHead>
                    <TableHead className="text-muted-foreground text-xs">类型</TableHead>
                    <TableHead className="text-muted-foreground text-xs">值</TableHead>
                    <TableHead className="text-muted-foreground text-xs">计算来源</TableHead>
                    <TableHead className="text-muted-foreground text-xs">上游来源</TableHead>
                    <TableHead className="text-muted-foreground text-xs">时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {factors.length === 0 ? (
                    <TableRow className="border-border">
                      <TableCell colSpan={7} className="text-center text-muted-foreground py-10 text-sm">暂无因子快照数据</TableCell>
                    </TableRow>
                  ) : (
                    factors.map((f) => {
                      const definition = f.definition || factorDefinitionMap[f.factor_name];
                      return (
                        <TableRow key={f.id} className="border-border hover:bg-card/50">
                          <TableCell className="text-foreground/90 text-xs font-mono">{f.symbol}</TableCell>
                          <TableCell>
                            <div className="text-blue-300 text-xs font-medium">{definition?.display_name || f.factor_name}</div>
                            <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">{f.factor_name}</div>
                          </TableCell>
                          <TableCell>
                            <Badge className="bg-slate-500/10 text-slate-300 text-[10px]">
                              {definition?.category || "未分类"}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-foreground/90 text-xs font-mono">
                            {formatFactorValue(f.factor_value)}
                            {definition?.unit ? <span className="ml-1 text-[10px] text-muted-foreground">{definition.unit}</span> : null}
                          </TableCell>
                          <TableCell className="text-muted-foreground text-xs">
                            <div>{formatSourceLabel(f.source)}</div>
                            {f.interval ? <div className="mt-0.5 text-[10px] text-muted-foreground/70">{f.interval}</div> : null}
                          </TableCell>
                          <TableCell className="text-muted-foreground text-xs">
                            <div>{formatProviderLabel(f.provider)}</div>
                            <div className="mt-0.5 text-[10px] text-muted-foreground/70">{formatSourceLabel(f.data_source)}</div>
                          </TableCell>
                          <TableCell className="text-muted-foreground text-[11px]">{f.timestamp ? new Date(f.timestamp).toLocaleString() : "-"}</TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </div>
            <p className="text-[10px] text-muted-foreground/50">共 {factors.length} 条记录</p>
          </TabsContent>

          {/* ── Events Tab ── */}
          <TabsContent value="events" className="space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
              <Filter className="w-4 h-4 text-muted-foreground" />
              <input
                placeholder="Symbol" value={filterSymbol} onChange={(e) => setFilterSymbol(e.target.value.toUpperCase())}
                className="bg-secondary border border-border text-foreground/90 text-xs rounded px-2 py-1.5 w-40"
              />
              <Select value={filterSignalType} onValueChange={setFilterSignalType}>
                <SelectTrigger className="w-28 bg-secondary border-border text-foreground/90 h-7 text-xs">
                  <SelectValue placeholder="信号类型" />
                </SelectTrigger>
                <SelectContent className="bg-secondary border-border">
                  <SelectItem value="all" className="text-foreground/90 text-xs">全部</SelectItem>
                  <SelectItem value="BUY" className="text-green-400 text-xs">BUY</SelectItem>
                  <SelectItem value="SELL" className="text-red-400 text-xs">SELL</SelectItem>
                  <SelectItem value="WAIT" className="text-muted-foreground text-xs">WAIT</SelectItem>
                </SelectContent>
              </Select>
              <Button size="sm" variant="outline" className="h-7 text-xs border-border text-foreground/80" onClick={fetchEvents}>筛选</Button>
            </div>
            <div className="rounded-lg border border-border overflow-hidden">
              <Table>
                <TableHeader className="bg-card">
                  <TableRow className="border-border">
                    <TableHead className="text-muted-foreground text-xs">Symbol</TableHead>
                    <TableHead className="text-muted-foreground text-xs">信号</TableHead>
                    <TableHead className="text-muted-foreground text-xs">置信度</TableHead>
                    <TableHead className="text-muted-foreground text-xs">策略</TableHead>
                    <TableHead className="text-muted-foreground text-xs">时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {events.length === 0 ? (
                    <TableRow className="border-border">
                      <TableCell colSpan={5} className="text-center text-muted-foreground py-10 text-sm">暂无信号事件数据</TableCell>
                    </TableRow>
                  ) : (
                    events.map((ev) => (
                      <TableRow key={ev.id} className="border-border hover:bg-card/50">
                        <TableCell className="text-foreground/90 text-xs font-mono">{ev.symbol}</TableCell>
                        <TableCell>
                          <Badge className={cn("text-[10px]",
                            ev.signal_type === "BUY" ? "bg-green-500/15 text-green-400" :
                            ev.signal_type === "SELL" ? "bg-red-500/15 text-red-400" :
                            "bg-slate-500/10 text-muted-foreground")}>
                            {ev.signal_type === "BUY" ? <ArrowUp className="w-3 h-3 mr-0.5" /> :
                             ev.signal_type === "SELL" ? <ArrowDown className="w-3 h-3 mr-0.5" /> :
                             <Minus className="w-3 h-3 mr-0.5" />}
                            {ev.signal_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-foreground/90 text-xs">{(ev.confidence * 100).toFixed(1)}%</TableCell>
                        <TableCell className="text-muted-foreground text-xs">{ev.source_strategy}</TableCell>
                        <TableCell className="text-muted-foreground text-[11px]">{ev.timestamp ? new Date(ev.timestamp).toLocaleString() : "-"}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
            <p className="text-[10px] text-muted-foreground/50">共 {events.length} 条记录</p>
          </TabsContent>

          {/* ── Series Chart Tab ── */}
          <TabsContent value="series" className="space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
              <input
                placeholder="Symbol" value={seriesSymbol} onChange={(e) => setSeriesSymbol(e.target.value.toUpperCase())}
                className="bg-secondary border border-border text-foreground/90 text-xs rounded px-2 py-1.5 w-36"
              />
              <input
                placeholder="Factor name" value={seriesFactor} onChange={(e) => setSeriesFactor(e.target.value)}
                className="bg-secondary border border-border text-foreground/90 text-xs rounded px-2 py-1.5 w-36"
              />
              <Button size="sm" variant="outline" className="h-7 text-xs border-border text-foreground/80" onClick={fetchSeries}>查询</Button>
            </div>
            <Card className="bg-card border-border/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-foreground text-sm">
                  {seriesSymbol} · {seriesFactor}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {chartData.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                    <TrendingUp className="w-10 h-10 mb-3 opacity-30" />
                    <p className="text-sm">暂无数据</p>
                    <p className="text-xs text-muted-foreground/50 mt-1">输入 symbol 和 factor_name 后查询</p>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={350}>
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="time" stroke="#64748b" fontSize={10} />
                      <YAxis stroke="#64748b" fontSize={10} />
                      <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", fontSize: "12px" }} />
                      <Line type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── Summary Tab ── */}
          <TabsContent value="summary">
            {!summary || summary.error ? (
              <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
                <PieChart className="w-10 h-10 mb-3 opacity-30" />
                <p className="text-sm">暂无汇总数据</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card className="bg-card border-border/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-foreground text-sm">因子类型分布</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {factorCategoryData.length === 0 ? (
                      <div className="py-10 text-center text-muted-foreground text-sm">无数据</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={300}>
                        <RPieChart>
                          <Pie data={factorCategoryData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label={({ name, value }) => `${name}: ${value}`}>
                            {factorCategoryData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                          </Pie>
                          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", fontSize: "12px" }} />
                          <Legend />
                        </RPieChart>
                      </ResponsiveContainer>
                    )}
                  </CardContent>
                </Card>
                <Card className="bg-card border-border/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-foreground text-sm">信号类型分布</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {pieData.length === 0 ? (
                      <div className="py-10 text-center text-muted-foreground text-sm">无数据</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={300}>
                        <RPieChart>
                          <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label={({ name, value }) => `${name}: ${value}`}>
                            {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                          </Pie>
                          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", fontSize: "12px" }} />
                          <Legend />
                        </RPieChart>
                      </ResponsiveContainer>
                    )}
                  </CardContent>
                </Card>
                <Card className="bg-card border-border/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-foreground text-sm">策略来源分布</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {strategyBarData.length === 0 ? (
                      <div className="py-10 text-center text-muted-foreground text-sm">无数据</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={300}>
                        <RBarChart data={strategyBarData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                          <XAxis dataKey="name" stroke="#64748b" fontSize={10} />
                          <YAxis stroke="#64748b" fontSize={10} />
                          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", fontSize: "12px" }} />
                          <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
                        </RBarChart>
                      </ResponsiveContainer>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}
          </TabsContent>
        </Tabs>

        {loading && (
          <div className="flex items-center justify-center py-10 text-muted-foreground text-sm">
            <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
          </div>
        )}
      </main>
    </div>
  );
}
