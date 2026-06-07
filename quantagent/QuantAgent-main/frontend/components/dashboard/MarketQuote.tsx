"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, DollarSign, BarChart3, Info } from "lucide-react";

interface QuoteData {
  symbol: string;
  price: number;
  change_24h_pct: number;
  change_24h?: number;
  volume: number;
  high_24h?: number;
  low_24h?: number;
}

interface MarketQuoteProps {
  symbol: string;
}

export function MarketQuote({ symbol }: MarketQuoteProps) {
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const overviewResponse = await fetch("/api/v1/market/overview");
        const data = await overviewResponse.json();
        if (cancelled) return;
        const tickers = data.tickers || [];
        const found = tickers.find((t: QuoteData) => t.symbol === symbol);
        if (found) {
          setQuote(found);
          return;
        }
        const tickerResponse = await fetch(`/api/v1/market/ticker/${symbol}`);
        const singleData = await tickerResponse.json();
        if (cancelled || !singleData) return;
        if (singleData && singleData.price > 0) {
          setQuote({
            symbol: singleData.symbol || symbol,
            price: singleData.price,
            change_24h_pct: singleData.change_percent || singleData.change_24h_pct || 0,
            change_24h: singleData.change_24h || 0,
            volume: singleData.volume || 0,
            high_24h: singleData.high_24h,
            low_24h: singleData.low_24h,
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
  }, [symbol]);

  const isUp = quote ? quote.change_24h_pct >= 0 : false;

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
            {/* Price */}
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
                  <p className="text-sm font-mono text-foreground">1h</p>
                </div>
              </div>
            </div>

            {/* Source badge */}
            <div className="flex items-center gap-1">
              <Badge variant="outline" className="text-[10px] border-border text-muted-foreground">
                数据来源: 本地行情库
              </Badge>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
