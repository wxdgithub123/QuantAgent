"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Target, TrendingUp, Activity, BarChart3, Zap, Settings } from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────────────────

interface StrategyAsset {
  strategyId: string;
  strategyName: string;
  strategyType: string;
  description?: string;
  usedFactors: string[];
  triggerSignals: string[];
  riskRules: string[];
  supportedExecutionModes: string[];
  signalCount?: number;
  recentBacktestCount?: number;
  bestBacktestReturn?: number | null;
  maxDrawdown?: number | null;
  latestBacktestAt?: string | null;
}

const CATEGORY_FILTERS = [
  { key: "all", label: "全部", icon: Target },
  { key: "趋势跟踪", label: "趋势", icon: TrendingUp },
  { key: "均值回归", label: "反转", icon: Activity },
  { key: "波动率趋势", label: "波动", icon: BarChart3 },
  { key: "突破趋势", label: "突破", icon: Zap },
] as const;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatPct(v?: number | null) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  return `${pct.toFixed(2)}%`;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function StrategySystem() {
  const [loading, setLoading] = useState(true);
  const [strategies, setStrategies] = useState<StrategyAsset[]>([]);
  const [categoryFilter, setCategoryFilter] = useState("all");

  // ── 策略配置 Dialog ──
  const [configStrategy, setConfigStrategy] = useState<StrategyAsset | null>(null);
  const [configParams, setConfigParams] = useState<Record<string, string>>({});
  const [isSavingConfig, setIsSavingConfig] = useState(false);

  const handleConfigOpen = (s: StrategyAsset) => {
    setConfigStrategy(s);
    // 从 localStorage 加载已保存的配置，或使用默认值
    const saved = loadStrategyConfig(s.strategyId);
    setConfigParams(saved);
  };

  const handleSaveConfig = async () => {
    if (!configStrategy) return;
    setIsSavingConfig(true);
    try {
      // TODO: 后端接口就绪后调用 PUT /api/v1/signals/strategies/{id}
      const res = await fetch(`/api/v1/signals/strategies/${configStrategy.strategyId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ params: configParams }),
      });
      if (res.ok) {
        toast.success(`${configStrategy.strategyName} 配置已保存`);
      } else {
        throw new Error("API 返回错误");
      }
    } catch {
      // 后端未就绪：存入 localStorage
      const all = JSON.parse(localStorage.getItem("quantagent_strategy_configs") || "{}");
      all[configStrategy.strategyId] = configParams;
      localStorage.setItem("quantagent_strategy_configs", JSON.stringify(all));
      toast.success(`${configStrategy.strategyName} 配置已保存到本地（后端未就绪，TODO 接入）`);
    } finally {
      setIsSavingConfig(false);
      setConfigStrategy(null);
    }
  };

  function loadStrategyConfig(strategyId: string): Record<string, string> {
    try {
      const all = JSON.parse(localStorage.getItem("quantagent_strategy_configs") || "{}");
      if (all[strategyId]) return all[strategyId];
    } catch { /* silent */ }
    // 默认配置参数
    return {
      "RSI 超卖线": "30",
      "RSI 超买线": "70",
      "MACD 快线": "12",
      "MACD 慢线": "26",
      "MACD 信号线": "9",
      "布林带周期": "20",
      "布林带标准差倍数": "2.0",
      "ATR 周期": "14",
      "ATR 倍数": "2.0",
    };
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const res = await fetch("/api/v1/signals/strategies");
        const data = await res.json();
        if (!cancelled) {
          setStrategies((data.data || []).filter(Boolean));
        }
      } catch {
        /* silent */
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const filtered = categoryFilter === "all"
    ? strategies
    : strategies.filter((s) => s.strategyType === categoryFilter);

  // Derive type counts
  const typeCounts = strategies.reduce<Record<string, number>>((acc, s) => {
    acc[s.strategyType] = (acc[s.strategyType] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {/* Category filter buttons */}
      <div className="flex flex-wrap items-center gap-1.5">
        {CATEGORY_FILTERS.map((cat) => {
          const Icon = cat.icon;
          const count = cat.key === "all" ? strategies.length : (typeCounts[cat.key] || 0);
          return (
            <button
              key={cat.key}
              onClick={() => setCategoryFilter(cat.key)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-colors",
                categoryFilter === cat.key
                  ? "bg-orange-500/15 text-orange-400 border-orange-500/30"
                  : "bg-secondary text-muted-foreground border-border hover:text-foreground"
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {cat.label}
              <span className="text-[10px] opacity-50">({count})</span>
            </button>
          );
        })}
      </div>

      {/* Strategy cards */}
      {loading ? (
        <div className="grid gap-3 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="bg-card border-border">
              <CardContent className="p-4 space-y-3">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-3/4" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="py-12 text-center">
            <Target className="w-10 h-10 mx-auto mb-3 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">暂无策略模板数据</p>
            <p className="text-xs text-muted-foreground/60 mt-1">策略模板在首次运行信号管线后自动注册</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {filtered.map((s) => (
            <Card key={s.strategyId} className="bg-card border-border/70 hover:border-orange-500/20 transition-colors">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-sm font-semibold text-foreground">{s.strategyName}</h4>
                      <Badge className="bg-orange-500/10 text-orange-300 border-orange-500/20 text-[10px]">
                        {s.strategyType}
                      </Badge>
                    </div>
                    <p className="mt-0.5 font-mono text-[11px] text-orange-300/60">{s.strategyId}</p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-[10px] border-border text-muted-foreground hover:text-foreground"
                      onClick={(e) => { e.stopPropagation(); handleConfigOpen(s); }}
                    >
                      <Settings className="w-3 h-3" />
                    </Button>
                    <Badge variant="outline" className="text-[10px] border-border text-muted-foreground">
                      {s.recentBacktestCount ?? 0} 次回测
                    </Badge>
                  </div>
                </div>

                {s.description && (
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">{s.description}</p>
                )}

                {/* Factor & Signal columns */}
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  <div className="rounded-lg border border-border/50 bg-secondary/30 p-2.5">
                    <p className="text-[10px] text-muted-foreground mb-1.5">使用因子</p>
                    <div className="flex flex-wrap gap-1">
                      {s.usedFactors.length > 0
                        ? s.usedFactors.slice(0, 8).map((f) => (
                            <Badge key={f} className="bg-blue-500/10 text-blue-300 border-blue-500/20 text-[10px] px-1.5 py-0">
                              {f}
                            </Badge>
                          ))
                        : <span className="text-[10px] text-muted-foreground">暂无</span>}
                      {s.usedFactors.length > 8 && (
                        <span className="text-[10px] text-muted-foreground">+{s.usedFactors.length - 8}</span>
                      )}
                    </div>
                  </div>
                  <div className="rounded-lg border border-border/50 bg-secondary/30 p-2.5">
                    <p className="text-[10px] text-muted-foreground mb-1.5">触发信号</p>
                    <div className="flex flex-wrap gap-1">
                      {s.triggerSignals.length > 0
                        ? s.triggerSignals.map((sig) => (
                            <Badge
                              key={sig}
                              className={cn(
                                "text-[10px] px-1.5 py-0",
                                sig === "BUY" ? "bg-green-500/15 text-green-400 border-green-500/25" :
                                sig === "SELL" ? "bg-red-500/15 text-red-400 border-red-500/25" :
                                "bg-muted text-muted-foreground border-border"
                              )}
                            >
                              {sig}
                            </Badge>
                          ))
                        : <span className="text-[10px] text-muted-foreground">暂无</span>}
                    </div>
                  </div>
                </div>

                {/* Risk rules */}
                <div className="mt-2">
                  <p className="text-[10px] text-muted-foreground mb-1">风控规则</p>
                  <div className="flex flex-wrap gap-1">
                    {s.riskRules.map((r) => (
                      <Badge key={r} variant="outline" className="text-[10px] px-1.5 py-0 border-border text-muted-foreground">
                        {r}
                      </Badge>
                    ))}
                  </div>
                </div>

                {/* Stats row */}
                <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                  <div className="rounded-md bg-secondary/50 p-1.5">
                    <p className="text-[10px] text-muted-foreground">信号</p>
                    <p className="font-mono text-xs text-foreground">{s.signalCount ?? 0}</p>
                  </div>
                  <div className="rounded-md bg-secondary/50 p-1.5">
                    <p className="text-[10px] text-muted-foreground">收益</p>
                    <p className="font-mono text-xs text-emerald-400">{formatPct(s.bestBacktestReturn)}</p>
                  </div>
                  <div className="rounded-md bg-secondary/50 p-1.5">
                    <p className="text-[10px] text-muted-foreground">回撤</p>
                    <p className="font-mono text-xs text-red-400">{formatPct(s.maxDrawdown)}</p>
                  </div>
                  <div className="rounded-md bg-secondary/50 p-1.5">
                    <p className="text-[10px] text-muted-foreground">最近</p>
                    <p className="text-[10px] text-muted-foreground">{s.latestBacktestAt ? "有记录" : "暂无"}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <p className="text-[10px] text-muted-foreground/50">
        共 {filtered.length} 个策略模板
        {categoryFilter !== "all" && `（已筛选：${categoryFilter}）`}
      </p>

      {/* ── 策略配置 Dialog ── */}
      <Dialog open={!!configStrategy} onOpenChange={(o) => { if (!o) setConfigStrategy(null); }}>
        <DialogContent className="bg-card border-border sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-foreground">策略配置: {configStrategy?.strategyName || ""}</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              修改策略阈值参数。后端接口就绪后会提交到数据库，当前保存到本地。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-3 max-h-[400px] overflow-y-auto">
            {Object.entries(configParams).map(([key, val]) => (
              <div key={key}>
                <Label className="text-xs text-muted-foreground">{key}</Label>
                <Input
                  value={val}
                  onChange={(e) => setConfigParams({ ...configParams, [key]: e.target.value })}
                  className="h-9 bg-secondary border-border text-xs mt-1 font-mono"
                />
              </div>
            ))}
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="outline" size="sm" className="text-xs border-border" onClick={() => setConfigStrategy(null)}>
              取消
            </Button>
            <Button size="sm" className="text-xs bg-orange-500/15 text-orange-400 hover:bg-orange-500/20" onClick={handleSaveConfig} disabled={isSavingConfig}>
              {isSavingConfig ? "保存中..." : "保存配置"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
