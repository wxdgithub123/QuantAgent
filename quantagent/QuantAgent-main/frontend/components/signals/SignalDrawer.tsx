"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  ArrowUp, ArrowDown, Minus, ExternalLink,
  Clock, AlertTriangle, CheckCircle, Database, BarChart3, FileSearch,
} from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────────────────

interface SignalDetail {
  signalId: number;
  symbol: string;
  signalType: string;
  strength?: number | null;
  confidence?: number | null;
  triggeredAt?: string | null;
  eventTime?: string | null;
  availableTime?: string | null;
  asOfTime?: string | null;
  sourceStrategy?: string | null;
  strategyId?: string | null;
  relatedFactors?: string[];
  factorValues?: Record<string, number>;
  triggerCondition?: string;
  explanation?: string;
  whetherTriggeredAgent?: boolean;
  relatedDecisionId?: number | null;
  relatedOrderIntentId?: string | null;
  relatedBacktestId?: number | null;
  relatedReplaySessionId?: string | null;
  relatedAuditIds?: number[];
  relatedDecisions?: Array<{ decisionId: number; finalSignal: string; confidence: number; asOfTime?: string }>;
  relatedBacktests?: Array<{ backtestId: number; strategyType: string; symbol: string; interval: string }>;
  relatedAudits?: Array<{ auditId: number; eventType: string; symbol: string }>;
}

export interface SignalDrawerProps {
  signalId: number | null;
  symbol: string;
  onClose: () => void;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatTime(v?: string | null) {
  if (!v) return "—";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString("zh-CN");
}

// ─── Component ───────────────────────────────────────────────────────────────

export function SignalDrawer({ signalId, symbol, onClose }: SignalDrawerProps) {
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<SignalDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (signalId === null) {
        setDetail(null);
        setError("");
        setLoading(false);
        return;
      }
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`/api/v1/signals/events/${signalId}/detail`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (!cancelled) setDetail(data.error ? null : data);
        if (!cancelled && data.error) setError("信号详情暂不可用");
      } catch {
        if (!cancelled) setError("无法加载信号详情，请稍后重试");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [signalId]);

  const open = signalId !== null;

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>信号证据链</SheetTitle>
          <SheetDescription>
            查看信号 #{(detail?.signalId ?? signalId)} 的触发因子、时间一致性和后续链路。
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-5 px-0.5">
          {loading ? (
            <div className="space-y-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : error ? (
            <div className="py-12 text-center">
              <AlertTriangle className="w-10 h-10 mx-auto mb-3 text-amber-400/30" />
              <p className="text-sm text-muted-foreground">{error}</p>
            </div>
          ) : detail ? (
            <>
              {/* ── Basic Info ── */}
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-border bg-secondary/30 p-3">
                  <p className="text-[10px] text-muted-foreground">Signal ID</p>
                  <p className="mt-1 font-mono text-xs text-foreground">#{detail.signalId}</p>
                </div>
                <div className="rounded-xl border border-border bg-secondary/30 p-3">
                  <p className="text-[10px] text-muted-foreground">Symbol / Type</p>
                  <div className="mt-1 flex items-center gap-1.5">
                    <span className="font-mono text-xs text-foreground">{detail.symbol}</span>
                    <Badge className={cn(
                      "text-[10px]",
                      detail.signalType === "BUY" ? "bg-green-500/15 text-green-400" :
                      detail.signalType === "SELL" ? "bg-red-500/15 text-red-400" :
                      "bg-muted text-muted-foreground"
                    )}>
                      {detail.signalType === "BUY" ? <ArrowUp className="w-3 h-3 mr-0.5" /> :
                       detail.signalType === "SELL" ? <ArrowDown className="w-3 h-3 mr-0.5" /> :
                       <Minus className="w-3 h-3 mr-0.5" />}
                      {detail.signalType}
                    </Badge>
                  </div>
                </div>
                <div className="rounded-xl border border-border bg-secondary/30 p-3">
                  <p className="text-[10px] text-muted-foreground">Confidence</p>
                  <p className="mt-1 font-mono text-xs text-foreground">
                    {detail.confidence !== null && detail.confidence !== undefined
                      ? `${(detail.confidence * 100).toFixed(1)}%`
                      : "—"}
                  </p>
                </div>
                <div className="rounded-xl border border-border bg-secondary/30 p-3">
                  <p className="text-[10px] text-muted-foreground">Strategy</p>
                  <p className="mt-1 font-mono text-[11px] text-foreground">{detail.sourceStrategy || "—"}</p>
                </div>
              </div>

              {/* ── Time Consistency ── */}
              <div className="rounded-xl border border-border bg-secondary/30 p-3">
                <p className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                  时间一致性检查
                </p>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  {[
                    { label: "触发时间 (triggeredAt)", value: detail.triggeredAt },
                    { label: "事件时间 (eventTime)", value: detail.eventTime },
                    { label: "可用时间 (availableTime)", value: detail.availableTime },
                    { label: "回看时间 (asOfTime)", value: detail.asOfTime },
                  ].map((row) => (
                    <div key={row.label} className="flex flex-col gap-0.5">
                      <span className="text-muted-foreground">{row.label}</span>
                      <span className="text-foreground font-mono text-[10px]">{formatTime(row.value)}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-2 flex items-center gap-1.5">
                  {detail.availableTime && detail.eventTime && new Date(detail.availableTime) >= new Date(detail.eventTime) ? (
                    <>
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-[10px] text-emerald-400">时间对齐: availableTime ≥ eventTime</span>
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                      <span className="text-[10px] text-amber-400">
                        {detail.availableTime ? "availableTime < eventTime（数据可能尚未就绪）" : "缺少时间信息"}
                      </span>
                    </>
                  )}
                </div>
              </div>

              {/* ── Trigger Reason ── */}
              <div className="rounded-xl border border-border bg-secondary/30 p-3">
                <p className="text-xs font-semibold text-foreground mb-1.5 flex items-center gap-1.5">
                  <FileSearch className="w-3.5 h-3.5 text-muted-foreground" />
                  触发原因
                </p>
                <p className="text-xs leading-5 text-muted-foreground">
                  {detail.triggerCondition || `${detail.sourceStrategy || "未知策略"} 根据关联因子触发 ${detail.signalType} 信号`}
                </p>
                {detail.explanation && (
                  <p className="mt-1 text-[11px] text-muted-foreground/70">{detail.explanation}</p>
                )}
              </div>

              {/* ── Related Factors ── */}
              <div className="rounded-xl border border-border bg-secondary/30 p-3">
                <p className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
                  <Database className="w-3.5 h-3.5 text-muted-foreground" />
                  关联因子 ({detail.relatedFactors?.length || 0})
                </p>
                {detail.relatedFactors && detail.relatedFactors.length > 0 ? (
                  <div className="space-y-1.5">
                    {detail.relatedFactors.slice(0, 15).map((f) => (
                      <div key={f} className="flex items-center justify-between text-[11px]">
                        <Badge className="bg-blue-500/10 text-blue-300 border-blue-500/20 text-[10px]">
                          {f}
                        </Badge>
                        {detail.factorValues && detail.factorValues[f] !== undefined && (
                          <span className="font-mono text-foreground/80">
                            {Number(detail.factorValues[f]).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                          </span>
                        )}
                      </div>
                    ))}
                    {detail.relatedFactors.length > 15 && (
                      <p className="text-[10px] text-muted-foreground">+{detail.relatedFactors.length - 15} more</p>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">暂无关联因子记录</p>
                )}
              </div>

              {/* ── Downstream Links ── */}
              <div className="rounded-xl border border-border bg-secondary/30 p-3">
                <p className="text-xs font-semibold text-foreground mb-3 flex items-center gap-1.5">
                  <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
                  后续操作
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <Link href={`/signals?symbol=${symbol}`}>
                    <Button variant="outline" size="sm" className="w-full h-9 text-xs border-border text-muted-foreground hover:text-foreground">
                      <FileSearch className="w-3.5 h-3.5 mr-1.5" />
                      AnalysisContext
                    </Button>
                  </Link>
                  <Link href={detail.relatedDecisionId ? `/decisions?decision_id=${detail.relatedDecisionId}` : "/decisions"}>
                    <Button variant="outline" size="sm" className="w-full h-9 text-xs border-border text-muted-foreground hover:text-foreground">
                      <Database className="w-3.5 h-3.5 mr-1.5" />
                      Agent 决策
                    </Button>
                  </Link>
                  <Link href={detail.relatedBacktestId ? `/backtest?id=${detail.relatedBacktestId}` : "/backtest"}>
                    <Button variant="outline" size="sm" className="w-full h-9 text-xs border-border text-muted-foreground hover:text-foreground">
                      <BarChart3 className="w-3.5 h-3.5 mr-1.5" />
                      加入回测
                    </Button>
                  </Link>
                  <Link href={detail.relatedAuditIds?.length ? `/audit` : "/audit"}>
                    <Button variant="outline" size="sm" className="w-full h-9 text-xs border-border text-muted-foreground hover:text-foreground">
                      <FileSearch className="w-3.5 h-3.5 mr-1.5" />
                      查看审计
                    </Button>
                  </Link>
                </div>
              </div>

              {/* ── Related IDs ── */}
              <div className="text-[10px] text-muted-foreground space-y-1">
                {detail.relatedDecisionId && <p>关联决策: #{detail.relatedDecisionId}</p>}
                {detail.relatedBacktestId && <p>关联回测: #{detail.relatedBacktestId}</p>}
                {detail.relatedAuditIds && detail.relatedAuditIds.length > 0 && (
                  <p>关联审计: {detail.relatedAuditIds.map((id) => `#${id}`).join(", ")}</p>
                )}
                {detail.relatedDecisions && detail.relatedDecisions.length > 0 && (
                  <p>相关决策: {detail.relatedDecisions.map((d) => `#${d.decisionId}`).join(", ")}</p>
                )}
              </div>
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
