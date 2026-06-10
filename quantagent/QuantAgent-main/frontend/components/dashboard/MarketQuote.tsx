"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, DollarSign, BarChart3, Info, AlertTriangle, Clock } from "lucide-react";

interface QuoteData {
  symbol: string;
  price: number;
  change_24h_pct: number;
  change_24h?: number;
  volume: number;
  high_24h?: number;
  low_24h?: number;
  provider?: string;
  updated_at?: string | null;
  bar_time?: string | null;
  stale?: boolean;
}

interface MarketQuoteProps {
  symbol: string;
  interval?: string;
}

/** 判断 K 线是否过期：最新 bar 距当前时间超过 interval 的 2 倍 */
function isStale(barTime: string | null | undefined, interval: string): boolean {
  if (!barTime) return false;
  const barMs = new Date(barTime).getTime();
  if (Number.isNaN(barMs)) return false;
  const nowMs = Date.now();
  const intervalMs: Record<string, number> = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
  };
  const threshold = (intervalMs[interval] || 3_600_000) * 2;
  return nowMs - barMs > threshold;
}

function formatProvider(provider?: string): string {
  if (!provider) return "未记录";
  const map: Record<string, string> = {
    "openbb:yfinance": "YFinance (OpenBB)",
    "openbb:fred": "FRED (OpenBB)",
    "ccxt:binance": "Binance (CCXT)",
    "ccxt:okx": "OKX (CCXT)",
    "binance": "Binance",
  };
  return map[provider] || provider;
}

export function MarketQuote({ symbol, interval = "1h" }: MarketQuoteProps) {
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        // TODO: 切换到数据平台 API /api/v1/quotes/latest?symbols={symbol}
        const overviewResponse = await fetch("/api/v1/market/overview");
        const data = await overviewResponse.json();
        if (cancelled) return;
        const tickers: QuoteData[] = data.tickers || [];
        const found = tickers.find((t: QuoteData) => t.symbol === symbol);
        const singleData = found || await fetch(`/api/v1/market/ticker/${symbol}`).then((r) => r.json());
        if (cancelled || !singleData) return;
        if (singleData.price > 0) {
          setQuote({
            symbol: singleData.symbol || symbol,
            price: singleData.price,
            change_24h_pct: singleData.change_percent || singleData.change_24h_pct || 0,
            change_24h: singleData.change_24h || 0,
            volume: singleData.volume || 0,
            high_24h: singleData.high_24h,
            low_24h: singleData.low_24h,
            provider: singleData.provider || "",
            updated_at: singleData.updated_at || singleData.timestamp || null,
            bar_time: singleData.timestamp || null,
            stale: isStale(singleData.timestamp || singleData.bar_time, interval),
          });
        } else {
          setError("暂无行情");
        }
      } catch {
        if (!cancelled) setError("加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [symbol, interval]);

  const isUp = quote ? quote.change_24h_pct >= 0 : false;
  const stale = quote?.stale || isStale(quote?.bar_time, interval);

  return (
    <Card className="border-border bg-card h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-foreground flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-blue-400" />
          行情总览
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-8 w-32" />
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-20" />
            <div className="grid grid-cols-2 gap-2 mt-3">
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
            </div>
          </div>
        ) : error ? (
          <div className="py-8 text-center">
            <Info className="w-8 h-8 mx-auto mb-2 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">{error}</p>
          </div>
        ) : quote ? (
          <div className="space-y-3">
            {/* Price — large font */}
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                {symbol.replace("USDT", "")} / USDT
              </p>
              <p className="text-2xl font-bold text-foreground font-mono mt-0.5">
                ${quote.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>

            {/* 24h Change */}
            <div className={cn(
              "flex items-center gap-1.5 text-sm font-semibold",
              isUp ? "text-emerald-400" : "text-red-400"
            )}>
              {isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
              {isUp ? "+" : ""}{quote.change_24h_pct.toFixed(2)}%
              {quote.change_24h ? (
                <span className="font-mono text-xs ml-1">
                  ({isUp ? "+" : ""}${Math.abs(quote.change_24h).toFixed(2)})
                </span>
              ) : null}
            </div>

            {/* Details grid */}
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg bg-secondary/50 p-2.5">
                <p className="text-[10px] text-muted-foreground">24H 最高</p>
                <p className="text-sm font-mono text-foreground mt-0.5">
                  ${quote.high_24h?.toLocaleString(undefined, { maximumFractionDigits: 2 }) || "—"}
                </p>
              </div>
              <div className="rounded-lg bg-secondary/50 p-2.5">
                <p className="text-[10px] text-muted-foreground">24H 最低</p>
                <p className="text-sm font-mono text-foreground mt-0.5">
                  ${quote.low_24h?.toLocaleString(undefined, { maximumFractionDigits: 2 }) || "—"}
                </p>
              </div>
              <div className="rounded-lg bg-secondary/50 p-2.5">
                <p className="text-[10px] text-muted-foreground">24H 成交量</p>
                <p className="text-sm font-mono text-foreground mt-0.5">
                  {quote.volume >= 1_000_000
                    ? `$${(quote.volume / 1_000_000).toFixed(2)}M`
                    : quote.volume >= 1_000
                      ? `$${(quote.volume / 1_000).toFixed(1)}K`
                      : `$${quote.volume.toFixed(0)}`}
                </p>
              </div>
              <div className="rounded-lg bg-secondary/50 p-2.5">
                <p className="text-[10px] text-muted-foreground">当前周期</p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <BarChart3 className="w-3.5 h-3.5 text-blue-400" />
                  <p className="text-sm font-mono text-foreground">{interval}</p>
                </div>
              </div>
            </div>

            {/* Provider + Bar time */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-1">
                <Badge variant="outline" className="text-[10px] border-border text-muted-foreground">
                  数据来源: {formatProvider(quote.provider)}
                </Badge>
              </div>
              {quote.bar_time && (
                <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Clock className="w-3 h-3" />
                  最新 Bar: {new Date(quote.bar_time).toLocaleString("zh-CN")}
                </div>
              )}
            </div>

            {/* Stale data warning */}
            {stale && (
              <div className="flex items-center gap-1.5 rounded-md bg-amber-500/10 border border-amber-500/20 px-2.5 py-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-[11px] text-amber-400">⚠️ 数据可能过期</span>
              </div>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
