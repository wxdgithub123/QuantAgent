"use client";

import { Suspense, useState, useCallback, useEffect, useMemo, useRef } from "react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import { TrendingCoins } from "@/components/dashboard/TrendingCoins";
import { MarketQuote } from "@/components/dashboard/MarketQuote";
import { NewsList } from "@/components/dashboard/NewsList";
import { MacroCards } from "@/components/dashboard/MacroCards";
import { DashboardResearchCards } from "@/components/dashboard/DashboardResearchCards";
import { WorkbenchLinkBar } from "@/components/linkage/WorkbenchLinkBar";
import { ResearchControls } from "@/components/signals/ResearchControls";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Plus, Loader2, Bell, ExternalLink } from "lucide-react";

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

// 从 localStorage 加载已保存的币种
function loadSavedSymbols(): string[] {
  try {
    const raw = localStorage.getItem("quantagent_custom_symbols");
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}
function saveSymbols(symbols: string[]) {
  try { localStorage.setItem("quantagent_custom_symbols", JSON.stringify(symbols)); } catch { /* silent */ }
}

const DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"];
const INTERVALS = [
  { value: "1m", label: "1分" }, { value: "5m", label: "5分" },
  { value: "15m", label: "15分" }, { value: "1h", label: "1时" },
  { value: "4h", label: "4时" }, { value: "1d", label: "1天" },
];

// ─── Page ───────────────────────────────────────────────────────────────────

function DashboardContent() {
  const searchParams = useSearchParams();
  const urlSymbol = searchParams.get("symbol")?.toUpperCase();
  const urlInterval = searchParams.get("interval");
  const urlAsOf = searchParams.get("as_of_time") || searchParams.get("asOfTime") || "";
  const initialInterval = urlInterval && INTERVALS.some((item) => item.value === urlInterval) ? urlInterval : "1h";

  const [symbol, setSymbol] = useState(urlSymbol || "BTCUSDT");
  const [interval, setIntervalStr] = useState(initialInterval);
  const [asOfTime, setAsOfTime] = useState(urlAsOf);
  const [appliedAsOf, setAppliedAsOf] = useState(urlAsOf);
  const [replayMode, setReplayMode] = useState(Boolean(urlAsOf));
  const [researchExpanded, setResearchExpanded] = useState(true);
  const [timeSuggestions, setTimeSuggestions] = useState<string[]>([]);

  // ── Custom symbols ──
  const [customSymbols, setCustomSymbols] = useState<string[]>([]);
  const [newSymbolInput, setNewSymbolInput] = useState("");
  const [isAddingSymbol, setIsAddingSymbol] = useState(false);
  const addRef = useRef<HTMLInputElement>(null);

  // 合并默认 + 自定义币种（去重）
  const allSymbols = useMemo(() => [...new Set([...DEFAULT_SYMBOLS, ...customSymbols])], [customSymbols]);

  // 初始化：从 localStorage 加载已保存币种
  useEffect(() => {
    setCustomSymbols(loadSavedSymbols());
  }, []);

  // ── Fetch as_of_time suggestions ──
  useEffect(() => {
    fetch("/api/v1/signals/events?symbol=BTCUSDT&interval=1h&limit=10")
      .then((r) => r.ok ? r.json() : null)
      .then((d) => {
        if (!d?.data) return;
        const times: string[] = d.data
          .map((e: { timestamp?: string }) => e.timestamp)
          .filter(Boolean)
          .slice(0, 8);
        setTimeSuggestions(times);
      })
      .catch(() => {});
  }, []);

  // ── Handlers ──
  const handleSymbolChange = useCallback((newSymbol: string) => setSymbol(newSymbol), []);

  const handleIntervalChange = useCallback((newInterval: string) => setIntervalStr(newInterval), []);

  const handleApply = useCallback(() => {
    if (!asOfTime.trim()) { setAppliedAsOf(""); return; }
    const raw = asOfTime.trim();
    const candidate = raw.includes("T") ? raw : raw.replace(" ", "T");
    const d = new Date(candidate);
    if (Number.isNaN(d.getTime())) { setAppliedAsOf(""); return; }
    setAppliedAsOf(d.toISOString());
  }, [asOfTime]);

  const handleClear = useCallback(() => {
    setAsOfTime(""); setAppliedAsOf(""); setReplayMode(false);
  }, []);

  // ── 添加研究标的 ──
  const handleAddSymbol = useCallback(async () => {
    const input = newSymbolInput.trim().toUpperCase();
    if (!input || !/^[A-Z0-9]+$/.test(input)) {
      toast.error("请输入有效的交易对代码（如 ETHUSDT）");
      return;
    }
    if (allSymbols.includes(input)) {
      setSymbol(input);
      toast.info(`${input} 已在列表中，已切换到此标的`);
      return;
    }

    setIsAddingSymbol(true);
    try {
      // a. 拉取 K线数据
      // TODO: 切换到数据平台 API /api/v1/bars?symbol={input}&interval=1h&limit=200
      await fetch(`/api/v1/market/klines/${input}?interval=1h&limit=200&fallback_exchange=binance&allow_ccxt_fallback=true`);

      // b. 触发 L5 管线
      await fetch("/api/v1/signals/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: input, interval: "1h", limit: 200,
          strategies: ["ma", "rsi", "boll", "macd"],
          include_wait_signals: true, persist_fetched_bars: true, include_context: false,
        }),
      });

      // c. 持久化到 localStorage
      const updated = [...customSymbols, input];
      setCustomSymbols(updated);
      saveSymbols(updated);

      // d. 切换到新标的
      setSymbol(input);
      setNewSymbolInput("");

      // e. 获取最新信号
      const sigRes = await fetch(`/api/v1/signals/events?symbol=${input}&limit=5`);
      const sigData = await sigRes.json();
      const events = sigData?.data || [];

      // f. 强信号 Toast 通知
      const strongSignals = events.filter(
        (e: { signal_type?: string; confidence?: number }) =>
          (e.signal_type === "BUY" || e.signal_type === "SELL") && (e.confidence || 0) > 0.6
      );
      if (strongSignals.length > 0) {
        for (const sig of strongSignals) {
          const label = sig.signal_type === "BUY" ? "买入" : "卖出";
          toast(
            <div className="flex items-center gap-2">
              <Bell className="w-4 h-4 text-amber-400" />
              <span>
                <strong>{input}</strong> 触发 <strong>{label}</strong> 信号，置信度 {(sig.confidence * 100).toFixed(0)}%
              </span>
            </div>,
            {
              duration: 6000,
              action: {
                label: <span className="flex items-center gap-1"><ExternalLink className="w-3 h-3" />查看</span>,
                onClick: () => window.open(`/signals?symbol=${input}`, "_self"),
              },
            }
          );
        }
      } else {
        toast.success(`${input} 已添加，K线和信号数据拉取完成`);
      }
    } catch (err) {
      toast.error(`添加 ${input} 失败: ${err instanceof Error ? err.message : "网络错误"}`);
    } finally {
      setIsAddingSymbol(false);
    }
  }, [newSymbolInput, customSymbols, allSymbols]);

  return (
    <div className="min-h-screen bg-background">
      <AppTopNav
        activeSection="overview"
        title="行情总览 / 研究台"
        subtitle="市场全局 → 聚焦币种 → 回看分析 → 基本面背景"
      />

      <main className="container mx-auto px-4 py-6 space-y-5">
        <WorkbenchLinkBar source="research" symbol={symbol} interval={interval} asOfTime={appliedAsOf || null} />

        {/* ════════════════════════════════════════════════════
            Section 1: Hot Coins + Add Symbol
            ════════════════════════════════════════════════════ */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-foreground">热门币种</h2>
            {/* 手动添加标的功能区 */}
            <div className="flex items-center gap-2">
              <Input
                ref={addRef}
                value={newSymbolInput}
                onChange={(e) => setNewSymbolInput(e.target.value.toUpperCase())}
                onKeyDown={(e) => { if (e.key === "Enter") handleAddSymbol(); }}
                placeholder="添加标的（如 ETHUSDT）"
                className="h-8 w-[180px] bg-secondary border-border text-xs placeholder:text-muted-foreground"
              />
              <Button
                size="sm"
                onClick={handleAddSymbol}
                disabled={isAddingSymbol}
                className="h-8 bg-blue-500/15 text-blue-400 border border-blue-500/25 hover:bg-blue-500/20 text-xs"
              >
                {isAddingSymbol ? (
                  <><Loader2 className="w-3 h-3 mr-1 animate-spin" />拉取中</>
                ) : (
                  <><Plus className="w-3 h-3 mr-1" />添加</>
                )}
              </Button>
              {customSymbols.length > 0 && (
                <Badge className="bg-purple-500/10 text-purple-300 border-purple-500/20 text-[10px]">
                  已添加 {customSymbols.length} 个自定义标的
                </Badge>
              )}
            </div>
          </div>
          <TrendingCoins
            symbols={allSymbols}
            selected={symbol}
            onSelect={handleSymbolChange}
          />
        </section>

        {/* ════════════════════════════════════════════════════
            Section 2: Research Controls
            ════════════════════════════════════════════════════ */}
        <section>
          <ResearchControls
            symbol={symbol}
            interval={interval}
            asOfTime={asOfTime}
            appliedAsOf={appliedAsOf}
            replayMode={replayMode}
            timeSuggestions={timeSuggestions}
            onSymbolChange={handleSymbolChange}
            onIntervalChange={handleIntervalChange}
            onAsOfTimeChange={setAsOfTime}
            onApply={handleApply}
            onClear={handleClear}
            onReplayModeChange={setReplayMode}
          />
        </section>

        {/* ════════════════════════════════════════════════════
            Section 3: K-line (60%) + Market Quote (40%)
            ════════════════════════════════════════════════════ */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-foreground">
              {symbol.replace("USDT", "")} / USDT
            </h2>
            <div className="flex items-center gap-1 bg-secondary rounded-lg p-0.5 border border-border">
              {INTERVALS.map((iv) => (
                <button
                  key={iv.value}
                  onClick={() => setIntervalStr(iv.value)}
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
              <MarketQuote symbol={symbol} interval={interval} />
            </div>
            <div className="lg:col-span-2">
              {/* TODO: 切换到数据平台 API /api/v1/bars */}
              <TradingViewChart
                key={`${symbol}-${interval}-${appliedAsOf || "latest"}`}
                symbol={symbol}
                interval={interval}
                asOfTime={appliedAsOf || null}
              />
            </div>
          </div>
        </section>

        {/* ════════════════════════════════════════════════════
            Section 3b: Research Summary Cards (collapsible)
            ════════════════════════════════════════════════════ */}
        <section>
          <div
            className="flex items-center gap-2 mb-3 cursor-pointer select-none"
            onClick={() => setResearchExpanded(!researchExpanded)}
          >
            <h2 className="text-sm font-semibold text-foreground">深度研究摘要</h2>
            <span className="text-[10px] text-muted-foreground">
              {researchExpanded ? "▼ 收起" : "▶ 展开"}
            </span>
            {appliedAsOf && (
              <span className="text-[10px] text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full">
                回看: {new Date(appliedAsOf).toLocaleString("zh-CN")}
              </span>
            )}
          </div>
          {researchExpanded && (
            <DashboardResearchCards
              symbol={symbol}
              interval={interval}
              appliedAsOf={appliedAsOf}
            />
          )}
        </section>

        {/* ════════════════════════════════════════════════════
            Section 4: News + Macro
            ════════════════════════════════════════════════════ */}
        <section>
          <h2 className="text-sm font-semibold text-foreground mb-3">基本面背景</h2>
          <div className="grid lg:grid-cols-5 gap-4">
            <div className="lg:col-span-3">
              {/* TODO: 切换到数据平台 API /api/v1/news */}
              <NewsList symbol={symbol} />
            </div>
            <div className="lg:col-span-2">
              {/* TODO: 切换到数据平台 API /api/v1/macro/indicators */}
              <MacroCards />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center text-muted-foreground">加载研究台...</div>}>
      <DashboardContent />
    </Suspense>
  );
}
