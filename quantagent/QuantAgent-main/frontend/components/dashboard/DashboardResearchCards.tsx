"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowUp, ArrowDown, Minus, ChevronRight, Activity, Database, Zap, FileSearch } from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────────

interface ContextSummary {
  symbol: string;
  interval: string;
  as_of_time: string | null;
  factor_snapshots: number;
  distinct_factors: number;
  event_total: number;
  strong_signals: number;
  latest_signal_at: string | null;
  data_sources: string[];
  error?: string;
}

interface SignalEventBrief {
  id: number;
  symbol: string;
  timestamp: string | null;
  signal_type: string;
  confidence: number;
  source_strategy: string;
}

interface AnalysisContext {
  instrument_id?: string;
  symbol?: string;
  timeframe?: string;
  as_of_time?: string;
  bars_count?: number;
  factors_count?: number;
  signals_count?: number;
  news_count?: number;
  macro_count?: number;
  latest_factors?: Record<string, number>;
  data_versions?: Record<string, unknown>;
  pit_check?: { available_time: string; as_of_time: string; passed: boolean };
}

export interface DashboardResearchCardsProps {
  symbol: string;
  interval: string;
  appliedAsOf: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function safeGet<T>(json: unknown, fallback: T): T {
  try {
    if (!json || typeof json !== "object") return fallback;
    const d = json as Record<string, unknown>;
    if (d.error) return fallback;
    return (d as unknown as T) || fallback;
  } catch {
    return fallback;
  }
}

// ─── Component ───────────────────────────────────────────────────────────────

export function DashboardResearchCards({ symbol, interval, appliedAsOf }: DashboardResearchCardsProps) {
  const [contextSummary, setContextSummary] = useState<ContextSummary | null>(null);
  const [recentSignals, setRecentSignals] = useState<SignalEventBrief[]>([]);
  const [analysisCtx, setAnalysisCtx] = useState<AnalysisContext | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      const params = new URLSearchParams({ symbol, interval });
      if (appliedAsOf) params.set("as_of_time", appliedAsOf);

      try {
        // Fetch summary + recent signals + analysis context in parallel
        const [summaryRes, signalsRes, ctxRes] = await Promise.all([
          fetch(`/api/v1/signals/summary/by-context?${params.toString()}`).then((r) => r.ok ? r.json() : null),
          fetch(`/api/v1/signals/events?symbol=${symbol}&interval=${interval}&limit=3${appliedAsOf ? `&as_of_time=${appliedAsOf}` : ""}`).then((r) => r.ok ? r.json() : null),
          fetch(`/api/v1/signals/context/${symbol}?interval=${interval}&signal_limit=5${appliedAsOf ? `&as_of_time=${appliedAsOf}` : ""}`).then((r) => r.ok ? r.json() : null),
        ]);

        if (!cancelled) {
          setContextSummary(safeGet<ContextSummary | null>(summaryRes, null));
          if (signalsRes?.data) {
            setRecentSignals(signalsRes.data.slice(0, 3));
          } else if (Array.isArray(signalsRes)) {
            setRecentSignals(signalsRes.slice(0, 3));
          }
          setAnalysisCtx(safeGet<AnalysisContext | null>(ctxRes, null));
        }
      } catch {
        if (!cancelled) {
          setContextSummary(null);
          setRecentSignals([]);
          setAnalysisCtx(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [symbol, interval, appliedAsOf]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* ── Card 1: Factor Snapshots Summary ── */}
      <Card className="border-blue-500/20 bg-card">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm text-foreground flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-400" />
              因子快照
            </CardTitle>
            <Link href={`/signals?symbol=${symbol}${appliedAsOf ? `&as_of_time=${appliedAsOf}` : ""}`} className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-0.5">
              查看详情 <ChevronRight className="w-3 h-3" />
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-3 w-28" />
            </div>
          ) : contextSummary && !contextSummary.error ? (
            <div className="space-y-2">
              <div className="flex items-baseline gap-2">
                <span className="text-xl font-bold text-blue-400 font-mono">
                  {contextSummary.factor_snapshots.toLocaleString()}
                </span>
                <span className="text-xs text-muted-foreground">条快照</span>
              </div>
              <p className="text-xs text-muted-foreground">
                {contextSummary.distinct_factors} 种因子
                {contextSummary.latest_signal_at && (
                  <> · 最新: {new Date(contextSummary.latest_signal_at).toLocaleDateString("zh-CN")}</>
                )}
              </p>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground py-4 text-center">暂无因子数据</p>
          )}
        </CardContent>
      </Card>

      {/* ── Card 2: Signal Events Summary ── */}
      <Card className="border-purple-500/20 bg-card">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm text-foreground flex items-center gap-2">
              <Zap className="w-4 h-4 text-purple-400" />
              信号事件
            </CardTitle>
            <Link href={`/signals?symbol=${symbol}${appliedAsOf ? `&as_of_time=${appliedAsOf}` : ""}`} className="text-[10px] text-purple-400 hover:text-purple-300 flex items-center gap-0.5">
              查看详情 <ChevronRight className="w-3 h-3" />
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-3 w-32" />
            </div>
          ) : recentSignals.length > 0 ? (
            <div className="space-y-2">
              <div className="flex items-baseline gap-2">
                <span className="text-xl font-bold text-purple-400 font-mono">
                  {contextSummary?.event_total ?? recentSignals.length}
                </span>
                <span className="text-xs text-muted-foreground">
                  个事件 · 强信号: {contextSummary?.strong_signals ?? 0}
                </span>
              </div>
              <div className="space-y-1">
                {recentSignals.map((sig) => (
                  <div key={sig.id} className="flex items-center justify-between text-[11px]">
                    <Badge className={cn(
                      "text-[10px]",
                      sig.signal_type === "BUY" ? "bg-green-500/15 text-green-400" :
                      sig.signal_type === "SELL" ? "bg-red-500/15 text-red-400" :
                      "bg-muted text-muted-foreground"
                    )}>
                      {sig.signal_type === "BUY" ? <ArrowUp className="w-2.5 h-2.5 mr-0.5" /> :
                       sig.signal_type === "SELL" ? <ArrowDown className="w-2.5 h-2.5 mr-0.5" /> :
                       <Minus className="w-2.5 h-2.5 mr-0.5" />}
                      {sig.signal_type}
                    </Badge>
                    <span className="text-muted-foreground">{sig.source_strategy}</span>
                    <span className="font-mono text-foreground/70">{(sig.confidence * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground py-4 text-center">暂无信号事件</p>
          )}
        </CardContent>
      </Card>

      {/* ── Card 3: AnalysisContext Summary ── */}
      <Card className="border-cyan-500/20 bg-card">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm text-foreground flex items-center gap-2">
              <FileSearch className="w-4 h-4 text-cyan-400" />
              AnalysisContext
            </CardTitle>
            <Link href={`/signals?symbol=${symbol}${appliedAsOf ? `&as_of_time=${appliedAsOf}` : ""}`} className="text-[10px] text-cyan-400 hover:text-cyan-300 flex items-center gap-0.5">
              查看详情 <ChevronRight className="w-3 h-3" />
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-3 w-40" />
            </div>
          ) : analysisCtx ? (
            <div className="space-y-2 text-xs text-muted-foreground">
              <div className="grid grid-cols-2 gap-1.5">
                <div className="bg-secondary/50 rounded px-2 py-1">
                  <span className="text-[10px] text-muted-foreground">K线数量</span>
                  <p className="font-mono text-foreground">{analysisCtx.bars_count ?? "—"}</p>
                </div>
                <div className="bg-secondary/50 rounded px-2 py-1">
                  <span className="text-[10px] text-muted-foreground">因子种类</span>
                  <p className="font-mono text-foreground">{analysisCtx.factors_count ?? "—"}</p>
                </div>
                <div className="bg-secondary/50 rounded px-2 py-1">
                  <span className="text-[10px] text-muted-foreground">信号数</span>
                  <p className="font-mono text-foreground">{analysisCtx.signals_count ?? "—"}</p>
                </div>
                <div className="bg-secondary/50 rounded px-2 py-1">
                  <span className="text-[10px] text-muted-foreground">新闻/宏观</span>
                  <p className="font-mono text-foreground">
                    {analysisCtx.news_count ?? "—"}/{analysisCtx.macro_count ?? "—"}
                  </p>
                </div>
              </div>
              {/* PIT Check */}
              {analysisCtx.pit_check && (
                <div className={cn(
                  "flex items-center gap-1.5 rounded px-2 py-1 text-[10px]",
                  analysisCtx.pit_check.passed
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-red-500/10 text-red-400"
                )}>
                  <Activity className="w-3 h-3" />
                  {analysisCtx.pit_check.passed
                    ? "PIT 合规 ✅"
                    : "PIT 违规 ❌"}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground py-4 text-center">暂无上下文数据</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
