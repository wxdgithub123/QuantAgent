"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Coins } from "lucide-react";

interface TickerInfo {
  symbol: string;
  price: number;
  change_24h_pct: number;
  volume: number;
  high_24h?: number;
  low_24h?: number;
}

interface TrendingCoinsProps {
  symbols: string[];
  selected: string;
  onSelect: (symbol: string) => void;
}

const COIN_ICONS: Record<string, string> = {
  BTCUSDT: "₿",
  ETHUSDT: "Ξ",
  SOLUSDT: "◎",
  BNBUSDT: "🟡",
  DOGEUSDT: "🐕",
  XRPUSDT: "💧",
};

export function TrendingCoins({ symbols, selected, onSelect }: TrendingCoinsProps) {
  const [tickers, setTickers] = useState<TickerInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const res = await fetch("/api/v1/market/overview");
        const data = await res.json();
        if (!cancelled) {
          setTickers(data.tickers || []);
        }
      } catch {
        if (!cancelled) setTickers([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  // Fill in missing symbols from the list
  const displayTickers = symbols.map((sym) => {
    const found = tickers.find((t) => t.symbol === sym);
    return found || { symbol: sym, price: 0, change_24h_pct: 0, volume: 0 };
  });

  return (
    <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin">
      {loading ? (
        Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="shrink-0 w-[160px] border-border bg-card">
            <CardContent className="p-3 space-y-2">
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-5 w-20" />
              <Skeleton className="h-3 w-16" />
            </CardContent>
          </Card>
        ))
      ) : displayTickers.length === 0 ? (
        <Card className="w-full border-border bg-card">
          <CardContent className="p-4 text-center">
            <Coins className="w-8 h-8 mx-auto mb-2 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">暂无行情数据</p>
          </CardContent>
        </Card>
      ) : (
        displayTickers.map((t) => {
          const isSelected = t.symbol === selected;
          const isUp = t.change_24h_pct >= 0;
          const icon = COIN_ICONS[t.symbol] || t.symbol.charAt(0);

          return (
            <button
              key={t.symbol}
              onClick={() => onSelect(t.symbol)}
              className={cn(
                "shrink-0 w-[160px] text-left rounded-xl border-2 p-3 transition-all cursor-pointer",
                isSelected
                  ? "border-blue-500/50 bg-blue-500/10 shadow-lg shadow-blue-500/5"
                  : "border-border bg-card hover:border-border/70 hover:bg-card/70"
              )}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">{icon}</span>
                <span className="text-sm font-semibold text-foreground">{t.symbol.replace("USDT", "")}</span>
                <span className="text-[10px] text-muted-foreground">/USDT</span>
              </div>
              <div className="text-base font-bold text-foreground font-mono">
                ${t.price > 0 ? t.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
              </div>
              <div className={cn(
                "flex items-center gap-1 text-xs font-medium mt-1",
                isUp ? "text-emerald-400" : "text-red-400"
              )}>
                {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                {t.price > 0 ? `${isUp ? "+" : ""}${t.change_24h_pct.toFixed(2)}%` : "—"}
              </div>
              <div className="text-[10px] text-muted-foreground mt-1">
                Vol: {t.volume > 0 ? (t.volume >= 1000 ? `$${(t.volume / 1000).toFixed(1)}K` : `$${t.volume.toFixed(0)}`) : "—"}
              </div>
            </button>
          );
        })
      )}
    </div>
  );
}
