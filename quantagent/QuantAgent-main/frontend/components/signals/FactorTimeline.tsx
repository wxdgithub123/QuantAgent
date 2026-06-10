"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { Activity, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────────

interface SeriesPoint {
  timestamp: string;
  value: number;
  parameters?: Record<string, unknown>;
}

interface TimelineProps {
  symbol: string;
  interval: string;
}

const AVAILABLE_FACTORS = [
  "sma_5", "sma_10", "sma_20", "sma_60",
  "ema_12", "ema_26",
  "rsi_14",
  "macd_dif", "macd_dea", "macd_hist",
  "boll_mid", "boll_upper", "boll_lower", "boll_pct_b", "boll_width",
  "atr_14",
];

const FACTOR_COLORS = ["#3b82f6", "#f59e0b", "#22c55e", "#ef4444", "#8b5cf6", "#ec4899"];

// ─── Component ───────────────────────────────────────────────────────────────

export function FactorTimeline({ symbol, interval }: TimelineProps) {
  const [selectedFactors, setSelectedFactors] = useState<string[]>(["sma_10", "sma_20"]);
  const [allData, setAllData] = useState<Record<string, SeriesPoint[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchFactorSeries = useCallback(async (factorName: string) => {
    try {
      const res = await fetch(`/api/v1/signals/factors/${symbol}/${factorName}/series?interval=${encodeURIComponent(interval)}&limit=500`);
      if (!res.ok) return [];
      const d = await res.json();
      return (d.data || []) as SeriesPoint[];
    } catch {
      return [];
    }
  }, [symbol, interval]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      const dataMap: Record<string, SeriesPoint[]> = {};
      for (const f of selectedFactors) {
        const pts = await fetchFactorSeries(f);
        if (!cancelled) dataMap[f] = pts;
      }
      if (!cancelled) {
        setAllData(dataMap);
        if (Object.values(dataMap).every((v) => v.length === 0)) {
          setError("暂无因子时序数据，请先运行信号管线生成因子快照");
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, [selectedFactors, fetchFactorSeries]);

  // Merge all selected factors into a single array keyed by timestamp
  const mergedData: Record<string, Record<string, number | string>> = {};
  for (const [factorName, points] of Object.entries(allData)) {
    for (const pt of points) {
      const ts = pt.timestamp?.slice(0, 19) || "";
      if (!mergedData[ts]) mergedData[ts] = { timestamp: ts };
      mergedData[ts][factorName] = pt.value;
    }
  }
  const chartData = Object.values(mergedData).sort(
    (a, b) => String(a.timestamp).localeCompare(String(b.timestamp))
  );

  const toggleFactor = (f: string) => {
    setSelectedFactors((prev) =>
      prev.includes(f) ? prev.filter((x) => x !== f) : [...prev, f].slice(0, 3)
    );
  };

  return (
    <Card className="border-cyan-500/20">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <CardTitle className="text-sm text-foreground flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              因子时间轴
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">
              选择 1-3 个因子叠加对比。横轴=时间，纵轴=因子值
            </p>
          </div>
        </div>
        {/* Factor selector chips */}
        <div className="flex flex-wrap gap-1.5 mt-2">
          {AVAILABLE_FACTORS.map((f) => (
            <Badge
              key={f}
              variant={selectedFactors.includes(f) ? "default" : "outline"}
              className={cn(
                "cursor-pointer text-[10px] transition-colors",
                selectedFactors.includes(f)
                  ? "text-white border-transparent"
                  : "border-border text-muted-foreground hover:text-foreground"
              )}
              style={selectedFactors.includes(f) ? { backgroundColor: FACTOR_COLORS[selectedFactors.indexOf(f) % FACTOR_COLORS.length] } : {}}
              onClick={() => toggleFactor(f)}
            >
              {f}
              {selectedFactors.includes(f) && (
                <X className="w-2.5 h-2.5 ml-0.5" />
              )}
            </Badge>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-[300px] w-full" />
        ) : error ? (
          <div className="py-12 text-center">
            <Info className="w-8 h-8 mx-auto mb-2 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">{error}</p>
          </div>
        ) : chartData.length === 0 ? (
          <div className="py-12 text-center">
            <Activity className="w-8 h-8 mx-auto mb-2 text-muted-foreground/30" />
            <p className="text-xs text-muted-foreground">选择因子后显示折线图</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis
                dataKey="timestamp"
                tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                tickFormatter={(v: string) => v?.slice(5, 16) || ""}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                tickFormatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
                labelFormatter={(l) => (typeof l === "string" ? new Date(l).toLocaleString("zh-CN") : String(l))}
              />
              <Legend />
              {selectedFactors.map((f, i) => (
                <Line
                  key={f}
                  type="monotone"
                  dataKey={f}
                  stroke={FACTOR_COLORS[i % FACTOR_COLORS.length]}
                  dot={false}
                  strokeWidth={1.5}
                  name={f}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
