"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import {
  Activity, BarChart3, BarChart, History, Server, RefreshCw, Zap, Layers,
  Brain, TrendingUp, Shield, CheckCircle2,
  ChevronDown, ChevronUp, PieChart, ArrowUp, ArrowDown, Minus,
} from "lucide-react";
import {
  PieChart as RPieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from "recharts";

// ─── Types ──────────────────────────────────────────────────────────────────

interface DecisionRow {
  id: number;
  symbol: string;
  timestamp: string | null;
  final_signal: string;
  confidence: number;
  vote_breakdown: Record<string, number>;
  risk_veto: boolean;
  summary: string;
  agent_signals: Array<{ agent_type?: string; role?: string; agent?: string; signal?: string; type?: string; confidence?: number; reasoning?: string }>;
  bull_view?: string;
  bear_view?: string;
  input_snapshot_ids?: Record<string, unknown>;
  role_opinions?: Array<{
    role?: string;
    opinion?: string;
    confidence?: number;
    risk_flag?: boolean;
    reasoning?: string;
    key_points?: string[];
  }>;
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

const SIGNAL_COLORS: Record<string, string> = {
  BUY: "#22c55e", SELL: "#ef4444", WAIT: "#94a3b8",
  LONG_REVERSAL: "#3b82f6", SHORT_REVERSAL: "#f59e0b", HOLD: "#6b7280",
};
const VOTE_COLORS: Record<string, string> = { bullish: "#22c55e", bearish: "#ef4444", neutral: "#94a3b8" };
const PIE_COLORS = ["#22c55e", "#ef4444", "#94a3b8", "#3b82f6", "#f59e0b", "#8b5cf6"];

// ─── Page ───────────────────────────────────────────────────────────────────

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<DecisionRow[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runFast, setRunFast] = useState(true);
  const [error, setError] = useState("");
  const [filterSymbol, setFilterSymbol] = useState("BTCUSDT");

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
    } catch (e: any) { setError(e.message); }
  }, [filterSymbol]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/coordination/stats");
      if (res.ok) setStats(await res.json());
    } catch { /* ignore */ }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([fetchDecisions(), fetchStats()]);
  }, [fetchDecisions, fetchStats]);

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

  useEffect(() => { refreshAll().finally(() => setLoading(false)); }, [refreshAll]);

  const signalPieData = stats?.by_signal ? Object.entries(stats.by_signal).map(([k, v]) => ({ name: k, value: v })) : [];
  const confidenceTrendData = [...decisions]
    .reverse()
    .slice(-30)
    .map(d => ({
      time: d.timestamp ? new Date(d.timestamp).toLocaleDateString() : "",
      confidence: d.confidence * 100,
      signal: d.final_signal,
    }));

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
              <Link href="/signals" className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg transition-all flex items-center gap-1.5"><Layers className="w-4 h-4" /> 因子/信号</Link>
              <Link href="/decisions" className="px-3 py-1.5 text-sm text-pink-400 bg-pink-500/10 rounded-lg border border-pink-500/20 font-medium flex items-center gap-1.5"><Brain className="w-4 h-4" /> 决策中心</Link>
            </nav>
            <div className="flex items-center gap-2">
              <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-foreground" onClick={refreshAll}>
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

        <Card className="mb-6 overflow-hidden border-pink-500/20 bg-gradient-to-br from-pink-500/10 via-card to-cyan-500/10">
          <CardContent className="p-4">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Zap className="h-4 w-4 text-pink-400" />
                  <h2 className="text-sm font-semibold text-foreground">PRD 10.4 完整决策链路</h2>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  触发 AnalysisContext - 四角色分析 - 多空辩论 - coordination_history 写入。
                </p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <input
                  placeholder="BTCUSDT"
                  value={filterSymbol}
                  onChange={(e) => setFilterSymbol(e.target.value.toUpperCase())}
                  className="w-full rounded border border-border bg-background/80 px-3 py-2 font-mono text-xs text-foreground/90 sm:w-36"
                />
                <label className="flex items-center gap-2 rounded border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={runFast}
                    onChange={(e) => setRunFast(e.target.checked)}
                  />
                  fast=true
                </label>
                <Button
                  size="sm"
                  className="bg-pink-500 text-white hover:bg-pink-400"
                  disabled={running}
                  onClick={runFullDecision}
                >
                  {running ? <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Brain className="mr-1.5 h-3.5 w-3.5" />}
                  {running ? "运行中..." : "运行完整决策"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Stats cards */}
        {stats && !stats.error && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <Card className="bg-card border-border">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">总决策数</p>
                <p className="text-2xl font-bold text-blue-400 mt-1">{stats.total}</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">近7天</p>
                <p className="text-2xl font-bold text-purple-400 mt-1">{stats.recent_7d}</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">平均置信度</p>
                <p className="text-2xl font-bold text-green-400 mt-1">{(stats.avg_confidence * 100).toFixed(1)}%</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Risk Veto</p>
                <p className="text-2xl font-bold text-red-400 mt-1">{stats.veto_count}</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">交易对</p>
                <p className="text-2xl font-bold text-cyan-400 mt-1">{Object.keys(stats.by_symbol || {}).length}</p>
              </CardContent>
            </Card>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          {/* Decision table */}
          <div className="lg:col-span-2">
            <Card className="bg-card border-border/50">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-foreground text-sm flex items-center gap-2">
                    <Brain className="w-4 h-4 text-pink-400" /> 决策历史
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <input
                      placeholder="Symbol filter" value={filterSymbol} onChange={(e) => setFilterSymbol(e.target.value.toUpperCase())}
                      className="bg-secondary border border-border text-foreground/90 text-xs rounded px-2 py-1 w-32"
                    />
                    <Button size="sm" variant="outline" className="h-7 text-xs border-border text-foreground/80" onClick={fetchDecisions}>筛选</Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <Table>
                  <TableHeader className="bg-card/50">
                    <TableRow className="border-border">
                      <TableHead className="text-muted-foreground text-xs">Symbol</TableHead>
                      <TableHead className="text-muted-foreground text-xs">决策</TableHead>
                      <TableHead className="text-muted-foreground text-xs">置信度</TableHead>
                      <TableHead className="text-muted-foreground text-xs">Veto</TableHead>
                      <TableHead className="text-muted-foreground text-xs">时间</TableHead>
                      <TableHead className="text-muted-foreground text-xs w-10"></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {decisions.length === 0 ? (
                      <TableRow className="border-border">
                        <TableCell colSpan={6} className="text-center text-muted-foreground py-10 text-sm">
                          暂无决策记录 — 点击上方“运行完整决策”后这里会显示历史
                        </TableCell>
                      </TableRow>
                    ) : (
                      decisions.map(d => (
                        <Fragment key={d.id}>
                          <TableRow key={d.id} className="border-border hover:bg-card/50 cursor-pointer" onClick={() => setExpandedId(expandedId === d.id ? null : d.id)}>
                            <TableCell className="text-foreground/90 text-xs font-mono">{d.symbol}</TableCell>
                            <TableCell>
                              <Badge className={cn("text-[10px]",
                                d.final_signal === "BUY" ? "bg-green-500/15 text-green-400" :
                                d.final_signal === "SELL" ? "bg-red-500/15 text-red-400" :
                                "bg-slate-500/10 text-muted-foreground")}>
                                {d.final_signal === "BUY" ? <ArrowUp className="w-3 h-3 mr-0.5" /> :
                                 d.final_signal === "SELL" ? <ArrowDown className="w-3 h-3 mr-0.5" /> :
                                 <Minus className="w-3 h-3 mr-0.5" />}
                                {d.final_signal}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-foreground/90 text-xs">{(d.confidence * 100).toFixed(1)}%</TableCell>
                            <TableCell>
                              {d.risk_veto ? <Shield className="w-4 h-4 text-red-400" /> : <CheckCircle2 className="w-4 h-4 text-muted-foreground/50" />}
                            </TableCell>
                            <TableCell className="text-muted-foreground text-[11px]">{d.timestamp ? new Date(d.timestamp).toLocaleString() : "-"}</TableCell>
                            <TableCell>{expandedId === d.id ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}</TableCell>
                          </TableRow>
                          {expandedId === d.id && (
                            <TableRow key={`detail-${d.id}`} className="border-border bg-card/30">
                              <TableCell colSpan={6} className="p-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                  {/* Vote breakdown */}
                                  <div>
                                    <h4 className="text-xs font-semibold text-muted-foreground mb-2">投票分布</h4>
                                    {Object.keys(d.vote_breakdown || {}).length > 0 ? (
                                      <ResponsiveContainer width="100%" height={160}>
                                        <RPieChart>
                                          <Pie data={
                                            Object.entries(d.vote_breakdown).map(([k, v]) => ({ name: k, value: v }))
                                          } dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} label={({ name, value }) => `${name}: ${value.toFixed(2)}`}>
                                            {Object.keys(d.vote_breakdown).map((_, i) => (
                                              <Cell key={i} fill={Object.values(VOTE_COLORS)[i] || PIE_COLORS[i % PIE_COLORS.length]} />
                                            ))}
                                          </Pie>
                                          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", fontSize: "11px" }} />
                                        </RPieChart>
                                      </ResponsiveContainer>
                                    ) : <p className="text-xs text-muted-foreground">无投票数据</p>}
                                  </div>
                                  {/* Agent signals */}
                                  <div>
                                    <h4 className="text-xs font-semibold text-muted-foreground mb-2">Agent 信号</h4>
                                    {d.agent_signals && d.agent_signals.length > 0 ? (
                                      <div className="space-y-1.5 max-h-[200px] overflow-y-auto custom-scrollbar">
                                        {d.agent_signals.map((sig: any, i: number) => (
                                          <div key={i} className="flex items-center justify-between p-2 bg-background/50 rounded border border-border">
                                            <span className="text-xs text-foreground/80">{sig.role || sig.agent_type || sig.agent || `Agent ${i + 1}`}</span>
                                            <div className="flex items-center gap-2">
                                              <Badge className={cn("text-[10px]",
                                                (sig.signal || sig.type) === "BUY" ? "bg-green-500/15 text-green-400" :
                                                (sig.signal || sig.type) === "SELL" ? "bg-red-500/15 text-red-400" :
                                                "bg-slate-500/10 text-muted-foreground")}>
                                                {sig.signal || sig.type || "WAIT"}
                                              </Badge>
                                              <span className="text-[10px] text-muted-foreground">{(sig.confidence != null ? (sig.confidence * 100).toFixed(0) + "%" : "")}</span>
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    ) : <p className="text-xs text-muted-foreground">无 Agent 信号数据</p>}
                                  </div>
                                  {/* Summary */}
                                  {d.summary && (
                                    <div className="md:col-span-2 mt-2">
                                      <h4 className="text-xs font-semibold text-muted-foreground mb-1">LLM 综合摘要</h4>
                                      <p className="text-xs text-foreground/80 bg-background/50 rounded p-3 border border-border leading-relaxed">{d.summary}</p>
                                    </div>
                                  )}
                                  <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-3">
                                    <div className="rounded border border-green-500/20 bg-green-500/5 p-3">
                                      <h4 className="text-xs font-semibold text-green-400 mb-1">多头观点</h4>
                                      <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/80">{d.bull_view || "暂无多头观点"}</p>
                                    </div>
                                    <div className="rounded border border-red-500/20 bg-red-500/5 p-3">
                                      <h4 className="text-xs font-semibold text-red-400 mb-1">空头观点</h4>
                                      <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/80">{d.bear_view || "暂无空头观点"}</p>
                                    </div>
                                  </div>
                                  <div className="md:col-span-2 rounded border border-border bg-background/50 p-3">
                                    <h4 className="text-xs font-semibold text-muted-foreground mb-2">角色意见</h4>
                                    {d.role_opinions && d.role_opinions.length > 0 ? (
                                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                        {d.role_opinions.map((role, i) => (
                                          <div key={`${role.role || "role"}-${i}`} className="rounded border border-border bg-card/60 p-2">
                                            <div className="mb-1 flex items-center justify-between gap-2">
                                              <span className="text-xs font-semibold text-foreground/90">{role.role || `role-${i + 1}`}</span>
                                              <Badge className="bg-slate-500/10 text-[10px] text-muted-foreground">
                                                {role.opinion || "neutral"} · {role.confidence != null ? `${(role.confidence * 100).toFixed(0)}%` : "--"}
                                              </Badge>
                                            </div>
                                            <p className="line-clamp-3 text-[11px] leading-relaxed text-muted-foreground">{role.reasoning || "暂无理由"}</p>
                                            {role.risk_flag && <p className="mt-1 text-[11px] text-red-400">risk_flag=true</p>}
                                          </div>
                                        ))}
                                      </div>
                                    ) : <p className="text-xs text-muted-foreground">暂无角色结构化意见</p>}
                                  </div>
                                  <div className="rounded border border-cyan-500/20 bg-cyan-500/5 p-3">
                                    <h4 className="text-xs font-semibold text-cyan-400 mb-1">仓位建议</h4>
                                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed text-foreground/80">
                                      {JSON.stringify(d.position_advice || {}, null, 2)}
                                    </pre>
                                  </div>
                                  <div className="rounded border border-amber-500/20 bg-amber-500/5 p-3">
                                    <h4 className="text-xs font-semibold text-amber-400 mb-1">风险备注</h4>
                                    <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/80">{d.risk_notes || "无明显风险"}</p>
                                  </div>
                                  <div className="md:col-span-2 rounded border border-border bg-background/50 p-3">
                                    <h4 className="text-xs font-semibold text-muted-foreground mb-1">输入快照 ID</h4>
                                    <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed text-muted-foreground">
                                      {JSON.stringify(d.input_snapshot_ids || {}, null, 2)}
                                    </pre>
                                  </div>
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </Fragment>
                      ))
                    )}
                  </TableBody>
                </Table>
                <p className="text-[10px] text-muted-foreground/50 mt-2">共 {decisions.length} 条记录</p>
              </CardContent>
            </Card>
          </div>

          {/* Right column: charts */}
          <div className="lg:col-span-1 space-y-6">
            {/* Signal distribution */}
            <Card className="bg-card border-border/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-foreground text-sm flex items-center gap-2">
                  <PieChart className="w-4 h-4 text-pink-400" /> 信号分布
                </CardTitle>
              </CardHeader>
              <CardContent>
                {signalPieData.length === 0 ? (
                  <div className="py-10 text-center text-muted-foreground text-xs">暂无数据</div>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <RPieChart>
                      <Pie data={signalPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}>
                        {signalPieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", fontSize: "11px" }} />
                      <Legend />
                    </RPieChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Confidence trend */}
            <Card className="bg-card border-border/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-foreground text-sm flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-cyan-400" /> 置信度趋势
                </CardTitle>
              </CardHeader>
              <CardContent>
                {confidenceTrendData.length === 0 ? (
                  <div className="py-10 text-center text-muted-foreground text-xs">暂无数据</div>
                ) : (
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={confidenceTrendData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="time" stroke="#64748b" fontSize={9} />
                      <YAxis stroke="#64748b" fontSize={9} domain={[0, 100]} />
                      <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", fontSize: "11px" }} />
                      <Line type="monotone" dataKey="confidence" stroke="#ec4899" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {loading && !stats && (
          <div className="flex items-center justify-center py-20 text-muted-foreground text-sm">
            <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
          </div>
        )}
      </main>
    </div>
  );
}
