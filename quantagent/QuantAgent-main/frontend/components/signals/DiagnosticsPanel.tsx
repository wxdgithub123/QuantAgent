"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronUp, CheckCircle, XCircle, AlertTriangle } from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────────────────

interface HealthStatus {
  status: string;
  service: string;
  dependencies: {
    database: string;
    redis: string;
    clickhouse: string;
    ingestion: string;
  };
  metrics: {
    redis_latency_ms: number;
    websocket_connections: number;
    ingestion_mode: string;
  };
}

interface GlobalSummary {
  factor_total?: number;
  event_total?: number;
  by_signal_type?: Record<string, number>;
  by_strategy?: Record<string, number>;
  by_symbol?: Record<string, number>;
  error?: string;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function DiagnosticsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [summary, setSummary] = useState<GlobalSummary | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [h, s] = await Promise.all([
          fetch("/health").then((r) => r.json()),
          fetch("/api/v1/signals/summary").then((r) => r.json()),
        ]);
        if (!cancelled) {
          setHealth(h);
          setSummary(s);
        }
      } catch {
        /* diagnostics are best-effort */
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [isOpen]);

  const statusIcon = (status: string) => {
    switch (status) {
      case "connected":
      case "healthy":
      case "initialized":
      case "ok":
        return <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />;
      case "degraded":
      case "partial":
      case "connecting":
        return <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />;
      default:
        return <XCircle className="w-3.5 h-3.5 text-red-400" />;
    }
  };

  return (
    <Card className="border-border/50">
      <CardHeader
        className="pb-2 cursor-pointer select-none"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm text-foreground flex items-center gap-2">
            🔧 诊断信息
            {!isOpen && health && (
              <Badge
                className={cn(
                  "text-[10px]",
                  health.status === "healthy" ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                )}
              >
                {health.status}
              </Badge>
            )}
          </CardTitle>
          {isOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
        </div>
      </CardHeader>

      {isOpen && (
        <CardContent className="pb-4 space-y-4">
          {loading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : (
            <>
              {/* Health checks */}
              {health && (
                <div>
                  <p className="text-xs font-semibold text-foreground mb-2">服务健康</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {Object.entries(health.dependencies).map(([key, value]) => (
                      <div key={key} className="flex items-center gap-1.5 rounded-lg bg-secondary/50 px-2.5 py-1.5">
                        {statusIcon(value)}
                        <span className="text-[11px] text-muted-foreground capitalize">{key}</span>
                        <span className="text-[10px] text-foreground/70 ml-auto">{value}</span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-2 text-[10px] text-muted-foreground">
                    <span>Redis 延迟: {health.metrics.redis_latency_ms.toFixed(1)}ms</span>
                    <span>WS 连接: {health.metrics.websocket_connections}</span>
                    <span>摄入模式: {health.metrics.ingestion_mode}</span>
                  </div>
                </div>
              )}

              {/* Global summary */}
              {summary && !summary.error && (
                <div>
                  <p className="text-xs font-semibold text-foreground mb-2">全局统计</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <div className="rounded-md bg-secondary/50 px-2.5 py-1.5 text-center">
                      <p className="text-[10px] text-muted-foreground">因子快照总数</p>
                      <p className="font-mono text-xs text-foreground">{summary.factor_total?.toLocaleString() ?? "—"}</p>
                    </div>
                    <div className="rounded-md bg-secondary/50 px-2.5 py-1.5 text-center">
                      <p className="text-[10px] text-muted-foreground">信号事件总数</p>
                      <p className="font-mono text-xs text-foreground">{summary.event_total?.toLocaleString() ?? "—"}</p>
                    </div>
                    <div className="rounded-md bg-secondary/50 px-2.5 py-1.5 text-center">
                      <p className="text-[10px] text-muted-foreground">活跃交易对</p>
                      <p className="font-mono text-xs text-foreground">{Object.keys(summary.by_symbol || {}).length || "—"}</p>
                    </div>
                    <div className="rounded-md bg-secondary/50 px-2.5 py-1.5 text-center">
                      <p className="text-[10px] text-muted-foreground">活跃策略</p>
                      <p className="font-mono text-xs text-foreground">{Object.keys(summary.by_strategy || {}).length || "—"}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Service info */}
              <div>
                <p className="text-xs font-semibold text-foreground mb-1">服务信息</p>
                <p className="text-[10px] text-muted-foreground">
                  后端: {health?.service ?? "—"} | 状态: {health?.status ?? "—"} |
                  API: <a href="http://localhost:8002/docs" className="text-blue-400 hover:underline" target="_blank">Swagger 文档</a>
                </p>
              </div>

              {/* Data source notes */}
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                <p className="text-[11px] text-amber-300 font-medium mb-1">数据源说明</p>
                <ul className="text-[10px] text-muted-foreground space-y-0.5 list-disc pl-4">
                  <li>YFinance 和 CCXT (OKX/Binance) 在国内网络下可能无法直连，需配置代理。</li>
                  <li>当前数据来自 DuckDB/ClickHouse 缓存，可能不是实时数据。</li>
                  <li>因子快照和信号事件由 L5 信号管线（factor_signal_pipeline）生成。</li>
                  <li>宏观和新闻数据由 L1 管线（macro/news adapters）拉取。</li>
                </ul>
              </div>
            </>
          )}
        </CardContent>
      )}
    </Card>
  );
}
