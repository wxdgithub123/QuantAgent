"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  HistogramData,
  LineData,
  Time,
} from "lightweight-charts";
import { Activity, Database, HardDrive, RefreshCw, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface TradingViewChartProps {
  symbol?: string;
  interval?: string;
  asOfTime?: string | null;
}

interface KlineItem {
  timestamp: string;
  event_time?: string;
  ts?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  vwap?: number;
}

interface KlineMetadata {
  active_source?: string;
  cache?: string;
  provider?: string;
  exchange?: string;
  updated_at?: string | null;
  pit_rule?: string;
  as_of_time?: string | null;
  count?: number;
}

/** 判断 K 线是否过期 */
function isStale(lastTs: string | null, interval: string): boolean {
  if (!lastTs) return false;
  const barMs = new Date(lastTs).getTime();
  if (Number.isNaN(barMs)) return false;
  const intervalMs: Record<string, number> = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
  };
  const threshold = (intervalMs[interval] || 3_600_000) * 2;
  return Date.now() - barMs > threshold;
}

function formatSourceLabel(metadata: KlineMetadata | null) {
  if (!metadata) return "数据源待确认";
  if (metadata.provider && metadata.exchange) return `${metadata.provider}:${metadata.exchange}`;
  return metadata.active_source || "market_data_gateway";
}

function formatUpdatedAt(value?: string | null) {
  if (!value) return "未同步";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function TradingViewChart({ symbol = "BTCUSDT", interval = "1h", asOfTime = null }: TradingViewChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const vwapSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [metadata, setMetadata] = useState<KlineMetadata | null>(null);
  const [lastBarTime, setLastBarTime] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [hasVwap, setHasVwap] = useState(false);

  // Reset chart data when symbol changes
  useEffect(() => {
    if (candleSeriesRef.current) candleSeriesRef.current.setData([]);
    if (volumeSeriesRef.current) volumeSeriesRef.current.setData([]);
    if (vwapSeriesRef.current) vwapSeriesRef.current.setData([]);
  }, [symbol]);

  // Create chart
  useEffect(() => {
    if (!chartContainerRef.current) return;
    const container = chartContainerRef.current;

    const chart = createChart(container, {
      layout: { background: { color: "#0f172a" }, textColor: "#e2e8f0" },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: { borderColor: "#334155", timeVisible: true },
      autoSize: false,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });

    // Volume histogram (bottom pane)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
      visible: false,
    });

    // VWAP line series
    const vwapSeries = chart.addSeries(LineSeries, {
      color: "#f59e0b",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    vwapSeriesRef.current = vwapSeries;

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current && document.body.contains(chartContainerRef.current)) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      try { chart.remove(); } catch { /* ignore */ }
      chartRef.current = null; candleSeriesRef.current = null;
      volumeSeriesRef.current = null; vwapSeriesRef.current = null;
    };
  }, []);

  // Fetch data
  useEffect(() => {
    if (!candleSeriesRef.current || !chartRef.current) return;

    const fetchData = async () => {
      setIsLoading(true);
      setErrorMessage("");
      try {
        const endpoint = asOfTime
          ? `/api/v1/bars/as-of?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=200&as_of_time=${encodeURIComponent(asOfTime)}`
          : `/api/v1/market/klines/${symbol}?interval=${interval}&limit=200`;
        const response = await fetch(endpoint);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const result = (await response.json()) as { data: KlineItem[]; metadata?: KlineMetadata; meta?: KlineMetadata };
        setMetadata(result.metadata ?? result.meta ?? null);

        if (!chartRef.current || !candleSeriesRef.current) return;

        const candleData: CandlestickData<Time>[] = [];
        const volData: HistogramData<Time>[] = [];
        const vwapData: LineData<Time>[] = [];
        let hasAnyVwap = false;

        for (const item of result.data) {
          const t = (new Date(item.timestamp || item.event_time || item.ts || "").getTime() / 1000) as Time;
          candleData.push({ time: t, open: item.open, high: item.high, low: item.low, close: item.close });
          volData.push({
            time: t,
            value: item.volume || 0,
            color: (item.close >= item.open) ? "rgba(34,197,94,0.4)" : "rgba(239,68,68,0.4)",
          });
          if (item.vwap && item.vwap > 0) {
            vwapData.push({ time: t, value: item.vwap });
            hasAnyVwap = true;
          }
        }

        candleData.sort((a, b) => (a.time as number) - (b.time as number));
        volData.sort((a, b) => (a.time as number) - (b.time as number));

        candleSeriesRef.current.setData(candleData);
        volumeSeriesRef.current?.setData(volData);
        if (hasAnyVwap) {
          vwapSeriesRef.current?.setData(vwapData);
          setHasVwap(true);
        } else {
          vwapSeriesRef.current?.setData([]);
          setHasVwap(false);
        }
        chartRef.current?.timeScale().fitContent();

        // Last bar time + stale check
        if (candleData.length > 0) {
          const lastTs = new Date((candleData[candleData.length - 1].time as number) * 1000).toISOString();
          setLastBarTime(lastTs);
          setStale(isStale(lastTs, interval));
        }
        if (candleData.length === 0) setErrorMessage("暂无 K 线数据");
      } catch {
        if (candleSeriesRef.current) candleSeriesRef.current.setData([]);
        if (volumeSeriesRef.current) volumeSeriesRef.current.setData([]);
        if (vwapSeriesRef.current) vwapSeriesRef.current.setData([]);
        setMetadata(null); setErrorMessage("K 线数据暂不可用");
      } finally { setIsLoading(false); }
    };

    fetchData();
  }, [symbol, interval, asOfTime]);

  return (
    <Card className="w-full h-full bg-slate-900 border-slate-800">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-slate-100 flex items-center gap-2">
            <span className="text-xl font-bold">{symbol}</span>
            <span className="text-sm font-normal text-slate-400">永续合约</span>
            {asOfTime && (
              <span className="rounded border border-cyan-500/25 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-normal text-cyan-200">
                as-of
              </span>
            )}
            {hasVwap && <span className="text-[10px] text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded">VWAP</span>}
          </CardTitle>
          <div className="flex flex-wrap items-center justify-end gap-2 text-[11px] text-slate-300">
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-1 text-emerald-200">
              <Activity className="h-3 w-3" /> K线: {formatSourceLabel(metadata)}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full border border-sky-500/25 bg-sky-500/10 px-2 py-1 text-sky-200">
              <HardDrive className="h-3 w-3" /> 缓存: {metadata?.cache || "本地缓存"}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full border border-slate-600 bg-slate-800/80 px-2 py-1 text-slate-300">
              <RefreshCw className="h-3 w-3" /> {formatUpdatedAt(metadata?.updated_at)}
            </span>
          </div>
        </div>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-500 flex-wrap">
          <Database className="h-3 w-3" />
          实际 K线来源 | 成交量柱形图 | VWAP 线（如有）
          {lastBarTime && (
            <span className="ml-1">· 最新 Bar: {new Date(lastBarTime).toLocaleString("zh-CN")}</span>
          )}
          {asOfTime ? " 当前图表按 available_time <= as_of_time 回看。" : ""}
        </div>
        {stale && (
          <div className="mt-2 flex items-center gap-1.5 rounded-md bg-amber-500/10 border border-amber-500/20 px-2.5 py-1.5 w-fit">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-[11px] text-amber-400">⚠️ 数据可能过期 — 最新 Bar 距当前时间超过一个周期</span>
          </div>
        )}
        {errorMessage && <div className="text-xs text-amber-300 mt-2">{errorMessage}</div>}
      </CardHeader>
      <CardContent className="p-0">
        <div className="relative">
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-900/50 z-10">
              <div className="text-slate-400">加载中...</div>
            </div>
          )}
          <div ref={chartContainerRef} className="w-full h-[500px]" />
        </div>
      </CardContent>
    </Card>
  );
}
