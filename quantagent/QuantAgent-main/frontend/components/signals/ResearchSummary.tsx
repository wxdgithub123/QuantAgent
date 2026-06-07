"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Activity, Database, Zap, Clock, TrendingUp } from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────────────────

interface ContextSummary {
  symbol: string;
  interval: string;
  as_of_time: string | null;
  factor_snapshots: number;
  distinct_factors: number;
  by_factor_category?: Record<string, number>;
  event_total: number;
  strong_signals: number;
  by_signal_type?: Record<string, number>;
  latest_signal_at: string | null;
  data_sources: string[];
  error?: string;
}

export interface ResearchSummaryProps {
  symbol: string;
  interval: string;
  appliedAsOf: string;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function ResearchSummary({ symbol, interval: iv, appliedAsOf }: ResearchSummaryProps) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ContextSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const params = new URLSearchParams({ symbol, interval: iv });
        if (appliedAsOf) params.set("as_of_time", appliedAsOf);
        const res = await fetch(`/api/v1/signals/summary/by-context?${params.toString()}`);
        const json = await res.json();
        if (!cancelled && !json.error) setData(json);
        else if (!cancelled) setData(null);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [symbol, iv, appliedAsOf]);

  const cards = [
    {
      label: "当前条件",
      value: `${data?.symbol ?? symbol} / ${data?.interval ?? iv}`,
      sub: data?.as_of_time
        ? `回看: ${new Date(data.as_of_time).toLocaleString("zh-CN")}`
        : "当前最新数据",
      icon: Activity,
      color: "text-blue-400",
      bg: "bg-blue-500/5 border-blue-500/20",
    },
    {
      label: "因子快照",
      value: loading ? "..." : (data?.factor_snapshots ?? "—"),
      sub: `${data?.distinct_factors ?? "—"} 种因子`,
      icon: Database,
      color: "text-cyan-400",
      bg: "bg-cyan-500/5 border-cyan-500/20",
    },
    {
      label: "信号事件",
      value: loading ? "..." : (data?.event_total ?? "—"),
      sub: `强信号: ${data?.strong_signals ?? "—"}`,
      icon: Zap,
      color: "text-purple-400",
      bg: "bg-purple-500/5 border-purple-500/20",
    },
    {
      label: "最新信号",
      value: loading ? "..." : data?.latest_signal_at
        ? new Date(data.latest_signal_at).toLocaleString("zh-CN")
        : "暂无",
      sub: data?.by_signal_type
        ? Object.entries(data.by_signal_type).map(([k, v]) => `${k}:${v}`).join(" ")
        : "",
      icon: Clock,
      color: "text-amber-400",
      bg: "bg-amber-500/5 border-amber-500/20",
    },
    {
      label: "数据来源",
      value: loading ? "..." : data?.data_sources?.join(", ") || "未记录",
      sub: "",
      icon: TrendingUp,
      color: "text-emerald-400",
      bg: "bg-emerald-500/5 border-emerald-500/20",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
      {cards.map((card) => (
        <Card key={card.label} className={`${card.bg} overflow-hidden`}>
          <CardContent className="p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <card.icon className={`w-3.5 h-3.5 ${card.color}`} />
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{card.label}</p>
            </div>
            {loading ? (
              <Skeleton className="h-5 w-3/4 mt-1" />
            ) : (
              <p className={`text-sm font-bold ${card.color} mt-0.5 truncate`}>{card.value}</p>
            )}
            {card.sub && (
              <p className="text-[10px] text-muted-foreground/70 mt-0.5 truncate">{card.sub}</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
