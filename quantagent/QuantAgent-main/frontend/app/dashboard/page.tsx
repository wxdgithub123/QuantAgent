"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import { TrendingCoins } from "@/components/dashboard/TrendingCoins";
import { MarketQuote } from "@/components/dashboard/MarketQuote";
import { NewsList } from "@/components/dashboard/NewsList";
import { MacroCards } from "@/components/dashboard/MacroCards";

// Lazy-load the chart (lightweight-charts requires browser APIs)
const TradingViewChart = dynamic(
  () => import("@/components/charts/TradingViewChart").then((mod) => mod.TradingViewChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);

function ChartSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-card animate-pulse">
      <div className="h-[420px] flex items-center justify-center">
        <p className="text-sm text-muted-foreground">加载图表中...</p>
      </div>
    </div>
  );
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"];
const INTERVALS = [
  { value: "1m", label: "1分" },
  { value: "5m", label: "5分" },
  { value: "15m", label: "15分" },
  { value: "1h", label: "1时" },
  { value: "4h", label: "4时" },
  { value: "1d", label: "1天" },
];

// ─── Page ───────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState("1h");

  return (
    <div className="min-h-screen bg-background">
      {/* ── Top Nav ── */}
      <AppTopNav
        activeSection="overview"
        title="行情总览"
        subtitle="市场全局 → 聚焦币种 → 基本面背景"
      />

      <main className="container mx-auto px-4 py-6 space-y-5">
        {/* ── Section 1: Hot Coins Row ── */}
        <section>
          <h2 className="text-sm font-semibold text-foreground mb-3">热门币种</h2>
          <TrendingCoins
            symbols={SYMBOLS}
            selected={symbol}
            onSelect={setSymbol}
          />
        </section>

        {/* ── Section 2 & 3: Quote + K-line ── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-foreground">
              {symbol.replace("USDT", "")} / USDT
            </h2>
            <div className="flex items-center gap-1 bg-secondary rounded-lg p-0.5 border border-border">
              {INTERVALS.map((iv) => (
                <button
                  key={iv.value}
                  onClick={() => setInterval(iv.value)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    interval === iv.value
                      ? "bg-blue-500/20 text-blue-400 shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {iv.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid lg:grid-cols-3 gap-4">
            <div className="lg:col-span-1">
              <MarketQuote symbol={symbol} />
            </div>
            <div className="lg:col-span-2">
              <TradingViewChart key={`${symbol}-${interval}`} symbol={symbol} interval={interval} />
            </div>
          </div>
        </section>

        {/* ── Section 4 & 5: News + Macro ── */}
        <section>
          <h2 className="text-sm font-semibold text-foreground mb-3">基本面背景</h2>
          <div className="grid lg:grid-cols-5 gap-4">
            <div className="lg:col-span-3">
              <NewsList symbol={symbol} />
            </div>
            <div className="lg:col-span-2">
              <MacroCards />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
