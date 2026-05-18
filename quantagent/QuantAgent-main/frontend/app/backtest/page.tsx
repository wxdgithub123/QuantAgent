"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { CompositionCompareChart } from "@/components/charts/CompositionCompareChart";
import { WfeCompareChart } from "@/components/charts/WfeCompareChart";
import { ParamStabilityChart } from "@/components/charts/ParamStabilityChart";
import { EquityCurveChart } from "@/components/charts/EquityCurveChart";
import { MarketConfigPanel } from "@/components/backtest/MarketConfigPanel";
import { createChart, LineSeries, createSeriesMarkers, IChartApi, ISeriesApi, Time } from "lightweight-charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  BarChart3, TrendingUp, TrendingDown, Activity, RefreshCw,
  Play, ChevronRight, Info, ArrowLeft, Clock, DollarSign,
  BarChart2, Percent, AlertTriangle, CheckCircle2, Terminal, BookOpen, LayoutDashboard,
  HelpCircle, History, Trash2, X, Layers, Server
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────
interface ParamDef {
  key: string;
  label: string;
  type: "int" | "float";
  default: number;
  min: number;
  max: number;
  step?: number;
  description?: string;
}

interface Template {
  id: string;
  name: string;
  description: string;
  params: ParamDef[];
}

interface BacktestMetrics {
  total_return: number;
  annual_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  total_commission: number;
  initial_capital: number;
  final_capital: number;
}

interface TradeRecord {
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  pnl_pct: number;
}

interface TradeMarker {
  time: string;
  price: number;
  side: "BUY" | "SELL";
  quantity?: number;
  pnl?: number | null;
}

interface BacktestResult {
  id: number | null;
  strategy_type: string;
  symbol: string;
  interval: string;
  params: Record<string, number>;
  metrics: BacktestMetrics;
  equity_curve: { t: string; v: number }[];
  baseline_curve: { t: string; v: number }[];
  markers: TradeMarker[];
  trades: TradeRecord[];
  created_at: string;
}

interface OptimizeResultFull {
  strategy_type: string;
  symbol: string;
  interval: string;
  best_params: Record<string, number>;
  best_sharpe: number;
  best_return: number;
  best_max_drawdown: number;
  best_equity_curve: { t: string; v: number }[];
  best_drawdown_curve: { t: string; v: number }[];
  best_trades: any[];
  total_combos: number;
  algorithm: string;
  target_metric: string;
  results: OptimizeResultItem[];
  warnings: OptimizeWarning[];
  saved_id: number | null;
}

interface OptimizeResultItem {
  params: Record<string, number>;
  sharpe: number;
  total_return: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
}

interface OptimizeWarning {
  type: string;
  severity: "high" | "medium" | "low";
  message: string;
  recommendation: string;
}

// ─── Metric Card ──────────────────────────────────────────────────────────────
function MetricCard({ label, value, positive, sub }: { label: string; value: string; positive?: boolean; sub?: string }) {
  return (
    <div className="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
      <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-xl font-bold ${positive === undefined ? "text-slate-100" : positive ? "text-green-400" : "text-red-400"}`}>
        {value}
      </p>
      {sub && <p className="text-[10px] text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

// ─── Metrics Comparison Table ───────────────────────────────────────────────
const METRIC_LABELS: Record<string, { label: string; format: (v: number) => string; higherBetter: boolean }> = {
  total_return: { label: "总收益率", format: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`, higherBetter: true },
  annual_return: { label: "年化收益", format: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`, higherBetter: true },
  max_drawdown: { label: "最大回撤", format: (v) => `-${v.toFixed(2)}%`, higherBetter: false },
  sharpe_ratio: { label: "夏普比率", format: (v) => v.toFixed(3), higherBetter: true },
  win_rate: { label: "胜率", format: (v) => `${v.toFixed(1)}%`, higherBetter: true },
  profit_factor: { label: "盈亏比", format: (v) => v >= 999 ? "∞" : v.toFixed(2), higherBetter: true },
  total_trades: { label: "交易次数", format: (v) => String(v), higherBetter: true },
};

const COMPOSITION_NAMES: Record<string, string> = { weighted: "加权组合", voting: "投票组合" };

function MetricsComparisonTable({
  comparisons,
  atomicStrategies,
  templates,
}: {
  comparisons: Record<string, { performance: Record<string, number>; error?: string }> | null;
  atomicStrategies: Record<string, Record<string, number>> | null;
  templates: Template[];
}) {
  if (!comparisons && !atomicStrategies) {
    return <div className="text-slate-500 text-xs">暂无数据</div>;
  }

  // Build columns: atomic strategies first, then compositions
  const atomicKeys = Object.keys(atomicStrategies || {});
  const compositionKeys = Object.keys(comparisons || {});
  const allKeys = [...atomicKeys, ...compositionKeys];

  // Get strategy name
  const getName = (key: string) => {
    if (COMPOSITION_NAMES[key]) return COMPOSITION_NAMES[key];
    const tpl = templates.find(t => t.id === key);
    return tpl?.name || key.toUpperCase();
  };

  // Check if a composition strategy has error
  const hasError = (key: string): boolean => {
    if (compositionKeys.includes(key)) {
      return !!(comparisons?.[key]?.error);
    }
    return false;
  };

  // Get performance for a key
  const getPerf = (key: string): Record<string, number> | null => {
    if (compositionKeys.includes(key)) {
      // Return null if there's an error or no performance data
      if (comparisons?.[key]?.error || !comparisons?.[key]?.performance) {
        return null;
      }
      return comparisons[key].performance;
    }
    return atomicStrategies?.[key] || null;
  };

  // Calculate best/worst for each metric (excluding error states)
  const metricsToShow = ["total_return", "annual_return", "max_drawdown", "sharpe_ratio", "win_rate", "total_trades"];

  const getBestWorst = (metric: string) => {
    const values: { key: string; value: number }[] = [];
    for (const key of allKeys) {
      // Skip strategies with errors
      if (hasError(key)) continue;
      const perf = getPerf(key);
      if (perf && perf[metric] !== undefined) {
        values.push({ key, value: perf[metric] });
      }
    }
    if (values.length === 0) return { best: null, worst: null };
    const config = METRIC_LABELS[metric];
    values.sort((a, b) => config.higherBetter ? b.value - a.value : a.value - b.value);
    return { best: values[0]?.key, worst: values[values.length - 1]?.key };
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-700">
            <th className="px-3 py-2 text-left text-slate-400 font-medium sticky left-0 bg-slate-900">指标</th>
            {allKeys.map(key => (
              <th
                key={key}
                className={`px-3 py-2 text-right font-medium ${
                  compositionKeys.includes(key)
                    ? "text-purple-400 bg-purple-500/5"
                    : "text-slate-400"
                }`}
              >
                {getName(key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metricsToShow.map(metric => {
            const config = METRIC_LABELS[metric];
            const { best, worst } = getBestWorst(metric);
            return (
              <tr key={metric} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                <td className="px-3 py-2 text-slate-300 sticky left-0 bg-slate-900">{config.label}</td>
                {allKeys.map(key => {
                  const isError = hasError(key);
                  const perf = getPerf(key);
                  const value = perf?.[metric] ?? 0;
                  const isBest = key === best;
                  const isWorst = key === worst;
                  const isComposition = compositionKeys.includes(key);
                  // Format return metrics with color
                  const isReturn = metric === "total_return" || metric === "annual_return";
                  const isPositive = value >= 0;
                  return (
                    <td
                      key={key}
                      className={`px-3 py-2 text-right font-mono ${
                        isComposition ? "font-bold bg-purple-500/5" : ""
                      } ${
                        isError ? "text-amber-500" :
                        isBest ? "text-green-400 font-bold" :
                        isWorst && allKeys.length > 2 ? "text-slate-500" :
                        isReturn ? (isPositive ? "text-green-400" : "text-red-400") :
                        metric === "max_drawdown" ? "text-red-400" :
                        "text-slate-300"
                      }`}
                    >
                      {isError ? "计算失败" : config.format(value)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ─── Weight Distribution Bars ────────────────────────────────────────────────
const WEIGHT_COLORS = [
  "#3b82f6", "#22c55e", "#f97316", "#a855f7", "#06b6d4", "#ec4899", "#eab308", "#14b8a6"
];

function WeightDistributionBars({
  weightDistribution,
  templates,
}: {
  weightDistribution: Record<string, Record<string, number>>;
  templates: Template[];
}) {
  // Get the first composition type that has weights (usually "weighted")
  const compositionType = Object.keys(weightDistribution)[0];
  const weights = weightDistribution[compositionType] || {};
  const entries = Object.entries(weights).filter(([_, w]) => w > 0);

  if (entries.length === 0) {
    return <div className="text-slate-500 text-xs">暂无权重数据</div>;
  }

  const getName = (key: string) => {
    const tpl = templates.find(t => t.id === key);
    return tpl?.name || key.toUpperCase();
  };

  return (
    <div className="space-y-2">
      {entries.map(([key, weight], index) => {
        const color = WEIGHT_COLORS[index % WEIGHT_COLORS.length];
        const pct = (weight * 100).toFixed(1);
        return (
          <div key={key} className="flex items-center gap-3">
            <span className="text-xs text-slate-400 w-16 truncate">{getName(key)}</span>
            <div className="flex-1 h-6 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${pct}%`,
                  backgroundColor: `${color}99`,
                }}
              />
            </div>
            <span className="text-xs text-slate-300 w-12 text-right font-mono">{pct}%</span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Signal Contribution Card ─────────────────────────────────────────────────
interface StrategySignalStats {
  buy_signals?: number;
  sell_signals?: number;
  signal_rate?: number;
}

interface SignalStatsMeta {
  agreement_rate?: number;
  strategies_count?: number;
}

interface SignalStats {
  [key: string]: StrategySignalStats | SignalStatsMeta | undefined;
}

function SignalContributionCard({
  signalStats,
  templates,
}: {
  signalStats: SignalStats;
  templates: Template[];
}) {
  // Filter out _meta key and get strategy entries
  const entries = Object.entries(signalStats).filter(([key]) => key !== "_meta") as [string, StrategySignalStats][];
  
  if (entries.length === 0) {
    return null;
  }

  const getName = (key: string) => {
    const tpl = templates.find(t => t.id === key);
    return tpl?.name || key.toUpperCase();
  };

  const meta = signalStats._meta as SignalStatsMeta | undefined;
  const agreementRate = meta?.agreement_rate ?? 0;

  return (
    <Card className="bg-slate-900 border-slate-700/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
          <Activity className="w-4 h-4 text-orange-400" />
          信号贡献度分析
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Signal Activity */}
        <div>
          <p className="text-xs text-slate-400 mb-3">各策略信号活跃度</p>
          <div className="space-y-3">
            {entries.map(([key, stats]) => {
              if (!stats) return null;
              const buyCount = stats.buy_signals ?? 0;
              const sellCount = stats.sell_signals ?? 0;
              const signalRate = stats.signal_rate ?? 0;
              const totalActive = buyCount + sellCount;
              
              // Calculate percentages within the bar
              // Total bar width = signalRate * 100%
              // Green part = (buyCount / totalActive) * signalRate * 100%
              // Red part = (sellCount / totalActive) * signalRate * 100%
              const totalBarWidth = signalRate * 100;
              const buyPct = totalActive > 0 ? (buyCount / totalActive) * totalBarWidth : 0;
              const sellPct = totalActive > 0 ? (sellCount / totalActive) * totalBarWidth : 0;
              
              return (
                <div key={key} className="flex items-center gap-3">
                  <span className="text-xs text-slate-300 w-20 truncate">{getName(key)}</span>
                  <div className="flex-1 h-5 bg-slate-800 rounded-full overflow-hidden relative">
                    {/* Buy signal (green from left) */}
                    <div 
                      className="absolute left-0 top-0 h-full bg-green-500/60 rounded-l-full" 
                      style={{ width: `${buyPct}%` }} 
                    />
                    {/* Sell signal (red following) */}
                    <div 
                      className="absolute top-0 h-full bg-red-500/60" 
                      style={{ left: `${buyPct}%`, width: `${sellPct}%` }} 
                    />
                  </div>
                  <div className="flex items-center gap-2 w-28">
                    <span className="text-[10px] text-green-400">买{buyCount}</span>
                    <span className="text-[10px] text-red-400">卖{sellCount}</span>
                    <span className="text-[10px] text-slate-500">{(signalRate * 100).toFixed(0)}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Strategy Agreement Rate */}
        {meta && (
          <div className="pt-3 border-t border-slate-700/50">
            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-400">策略信号一致率</p>
              <div className="flex items-center gap-2">
                <div className="w-24 h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-amber-500/60 rounded-full" 
                    style={{ width: `${agreementRate * 100}%` }} 
                  />
                </div>
                <span className="text-xs text-amber-400 font-mono">{(agreementRate * 100).toFixed(1)}%</span>
              </div>
            </div>
            <p className="text-[10px] text-slate-500 mt-1">
              {agreementRate > 0.5 
                ? "策略之间信号高度一致，组合效果可能有限" 
                : agreementRate > 0.3 
                  ? "策略信号适度分散，组合具有互补效果"
                  : "策略信号差异较大，组合可能带来良好的分散化效果"}
            </p>
          </div>
        )}

        {/* Legend */}
        <div className="flex items-center gap-4 pt-2">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 bg-green-500/60 rounded" />
            <span className="text-[10px] text-slate-500">买入信号</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 bg-red-500/60 rounded" />
            <span className="text-[10px] text-slate-500">卖出信号</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 bg-slate-700 rounded" />
            <span className="text-[10px] text-slate-500">中性/持仓</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Summary Evaluation Card ──────────────────────────────────────────────────
function SummaryEvaluationCard({
  comparisons,
  atomicStrategies,
}: {
  comparisons: Record<string, { performance: Record<string, number> }> | null;
  atomicStrategies: Record<string, Record<string, number>> | null;
}) {
  // Find best atomic strategy
  const atomicEntries = Object.entries(atomicStrategies || {});
  let bestAtomic: { key: string; total_return: number; max_drawdown: number; sharpe_ratio: number } | null = null;
  for (const [key, perf] of atomicEntries) {
    if (!bestAtomic || (perf.total_return ?? 0) > bestAtomic.total_return) {
      bestAtomic = {
        key,
        total_return: perf.total_return ?? 0,
        max_drawdown: perf.max_drawdown ?? 0,
        sharpe_ratio: perf.sharpe_ratio ?? 0,
      };
    }
  }

  // Get best composition (weighted preferred)
  const compositionEntries = Object.entries(comparisons || {});
  const weightedComp = compositionEntries.find(([k]) => k === "weighted")?.[1]?.performance;
  const votingComp = compositionEntries.find(([k]) => k === "voting")?.[1]?.performance;
  const bestComp = weightedComp || votingComp;

  if (!bestComp || !bestAtomic) {
    return null;
  }

  const returnImprovement = bestComp.total_return - bestAtomic.total_return;
  const drawdownImprovement = bestAtomic.max_drawdown - bestComp.max_drawdown;
  const sharpeImprovement = bestComp.sharpe_ratio - bestAtomic.sharpe_ratio;

  return (
    <Card className="bg-slate-900 border-slate-700/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-green-400" />
          综合评价
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Return Improvement */}
          <div className="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <p className="text-xs text-slate-400 mb-1">组合收益 vs 最佳单策略</p>
            <p className={`text-xl font-bold font-mono ${returnImprovement >= 0 ? "text-green-400" : "text-red-400"}`}>
              {returnImprovement >= 0 ? "+" : ""}{returnImprovement.toFixed(2)}%
            </p>
            <p className="text-[10px] text-slate-500 mt-1">
              组合 {bestComp.total_return.toFixed(2)}% vs 单策略 {bestAtomic.total_return.toFixed(2)}%
            </p>
          </div>

          {/* Drawdown Improvement */}
          <div className="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <p className="text-xs text-slate-400 mb-1">组合回撤 vs 最佳单策略</p>
            <p className={`text-xl font-bold font-mono ${drawdownImprovement >= 0 ? "text-green-400" : "text-red-400"}`}>
              {drawdownImprovement >= 0 ? "改善" : "恶化"} {Math.abs(drawdownImprovement).toFixed(2)}%
            </p>
            <p className="text-[10px] text-slate-500 mt-1">
              组合 -{bestComp.max_drawdown.toFixed(2)}% vs 单策略 -{bestAtomic.max_drawdown.toFixed(2)}%
            </p>
          </div>

          {/* Sharpe Ratio */}
          <div className="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <p className="text-xs text-slate-400 mb-1">夏普比率对比</p>
            <p className="text-xl font-bold font-mono text-slate-100">
              {bestComp.sharpe_ratio.toFixed(3)}
            </p>
            <p className="text-[10px] text-slate-500 mt-1">
              {sharpeImprovement >= 0 ? "优于" : "低于"}最佳单策略 {bestAtomic.sharpe_ratio.toFixed(3)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Launch Paper Bot Dialog ───────────────────────────────────────────────────
function LaunchPaperBotDialog({
  result,
  onConfirm,
  onCancel,
}: {
  result: any;
  onConfirm: (botName: string, paperBalance: number, orderAmount: number) => void;
  onCancel: () => void;
}) {
  const [botName, setBotName] = useState(`paper_${result?.symbol?.toLowerCase() || "bot"}_${Date.now().toString(36)}`);
  const [paperBalance, setPaperBalance] = useState(result?.metrics?.initial_capital || 10000);
  const [orderAmount, setOrderAmount] = useState(100);

  const sharpeRatio = result?.metrics?.sharpe_ratio ?? 0;
  const maxDrawdown = result?.metrics?.max_drawdown ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-md shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-green-500/10 rounded-full flex items-center justify-center">
            <Play className="w-5 h-5 text-green-400" />
          </div>
          <h3 className="text-lg font-bold text-slate-100">启动 Paper Bot</h3>
        </div>

        {/* 回测质量提示 */}
        <div className="bg-slate-800/50 rounded-xl p-3 mb-4 border border-slate-700/50">
          <p className="text-xs text-slate-400 mb-1">将从以下回测结果创建 Paper Bot：</p>
          <div className="flex items-center gap-2 mb-2">
            <Badge variant="outline" className="text-[10px] bg-blue-500/10 text-blue-400 border-blue-500/20">
              {result.strategy_type}
            </Badge>
            <span className="text-sm text-slate-300">{result.symbol} / {result.interval}</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center gap-1">
              <span className="text-slate-500">夏普:</span>
              <span className={sharpeRatio >= 1 ? "text-green-400" : sharpeRatio >= 0.5 ? "text-amber-400" : "text-red-400"}>
                {sharpeRatio.toFixed(3)}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-slate-500">回撤:</span>
              <span className="text-red-400">-{maxDrawdown.toFixed(1)}%</span>
            </div>
          </div>
          {sharpeRatio < 0.5 && (
            <p className="text-[10px] text-amber-400 mt-1">
              警告：夏普比率低于 0.5，建议优化后再创建 Paper Bot
            </p>
          )}
        </div>

        {/* 参数表单 */}
        <div className="space-y-3 mb-5">
          <div>
            <Label className="text-xs text-slate-400 mb-1 block">Bot 名称</Label>
            <Input
              value={botName}
              onChange={e => setBotName(e.target.value)}
              className="bg-slate-800 border-slate-700 text-slate-200 text-xs h-8"
              placeholder="paper_bot_name"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs text-slate-400 mb-1 block">初始资金 (USDT)</Label>
              <Input
                type="number"
                value={paperBalance}
                onChange={e => setPaperBalance(Number(e.target.value))}
                className="bg-slate-800 border-slate-700 text-slate-200 text-xs h-8"
                min={100}
              />
            </div>
            <div>
              <Label className="text-xs text-slate-400 mb-1 block">每笔订单金额</Label>
              <Input
                type="number"
                value={orderAmount}
                onChange={e => setOrderAmount(Number(e.target.value))}
                className="bg-slate-800 border-slate-700 text-slate-200 text-xs h-8"
                min={1}
              />
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <Button
            onClick={onCancel}
            variant="outline"
            className="flex-1 bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700"
          >
            取消
          </Button>
          <Button
            onClick={() => onConfirm(botName, paperBalance, orderAmount)}
            className="flex-1 bg-green-600 hover:bg-green-500 text-white"
          >
            <Play className="w-3 h-3 mr-1" />
            创建并启动
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Delete Confirmation Dialog ─────────────────────────────────────────────
function DeleteConfirmDialog({
  record,
  onConfirm,
  onCancel,
}: {
  record: any;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-red-500/10 rounded-full flex items-center justify-center">
            <Trash2 className="w-5 h-5 text-red-400" />
          </div>
          <h3 className="text-lg font-bold text-slate-100">确认删除</h3>
        </div>
        <p className="text-sm text-slate-400 mb-1">确定要删除以下回测记录吗？</p>
        <div className="bg-slate-800/50 rounded-xl p-3 mb-5 border border-slate-700/50">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px] bg-blue-500/10 text-blue-400 border-blue-500/20">
              {record.strategy_type}
            </Badge>
            <span className="text-sm text-slate-300">{record.symbol} / {record.interval}</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            {new Date(record.created_at).toLocaleString()} · {(record.metrics?.total_trades ?? record.trades?.length ?? 0)} 笔交易
          </p>
        </div>
        <p className="text-xs text-slate-500 mb-5">此操作无法撤销</p>
        <div className="flex gap-3">
          <Button
            onClick={onCancel}
            variant="outline"
            className="flex-1 bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700"
          >
            取消
          </Button>
          <Button
            onClick={onConfirm}
            className="flex-1 bg-red-600 hover:bg-red-500 text-white"
          >
            删除
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function BacktestPage() {
  // Templates
  const [templates, setTemplates]       = useState<Template[]>([]);
  const [selectedType, setSelectedType] = useState<string>("ma");
  const [paramValues, setParamValues]   = useState<Record<string, number>>({});

  // Config
  const [symbol, setSymbol]                 = useState("BTCUSDT");
  const [interval, setIntervalVal]          = useState("1d");
  const [limit, setLimit]                   = useState(500);
  const [initialCapital, setInitialCapital] = useState(10000);

  // Date range (optional)
  const [startTime, setStartTime] = useState<string>('');
  const [endTime, setEndTime] = useState<string>('');

  // Run state
  const [running, setRunning]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [result, setResult]     = useState<BacktestResult | null>(null);

  // History
  const [history, setHistory]   = useState<any[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<any>(null); // Record to delete

  // Composition Mode
  const [backtestMode, setBacktestMode] = useState<"single" | "composition" | "wfa" | "optimize">("single");
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([]);
  const [compositionType, setCompositionType] = useState<"weighted" | "voting">("weighted");
  const [compositionRunning, setCompositionRunning] = useState(false);
  const [compositionError, setCompositionError] = useState<string | null>(null);
  const [compositionResult, setCompositionResult] = useState<any>(null);

  // WFA Mode
  const [wfaRunning, setWfaRunning] = useState(false);
  const [wfaError, setWfaError] = useState<string | null>(null);
  const [wfaResult, setWfaResult] = useState<any>(null);
  const [wfaTrainRatio, setWfaTrainRatio] = useState<number>(0.7);
  const [wfaWindowsCount, setWfaWindowsCount] = useState<number>(5);

  // ── Parameter Optimization Mode ──────────────────────────────────────────
  const [optRunning, setOptRunning] = useState(false);
  const [optError, setOptError] = useState<string | null>(null);
  const [optResult, setOptResult] = useState<OptimizeResultFull | null>(null);
  const [optAlgorithm, setOptAlgorithm] = useState<"grid" | "optuna">("grid");
  const [optNTrials, setOptNTrials] = useState(50);
  const [optTargetMetric, setOptTargetMetric] = useState<string>("sharpe");
  const [optCommission, setOptCommission] = useState(0.001);
  const [optSlippage, setOptSlippage] = useState(0.0005);
  // param ranges: { [key]: { min, max, step, values[] } }
  const [optParamRanges, setOptParamRanges] = useState<Record<string, { min: number; max: number; step: number; values: number[] }>>({});
  const [optHistory, setOptHistory] = useState<any[]>([]);
  const [optSaveDialogOpen, setOptSaveDialogOpen] = useState(false);
  const [optApplyDialogOpen, setOptApplyDialogOpen] = useState(false);
  const [optSelectedParams, setOptSelectedParams] = useState<Record<string, number> | null>(null);
  const [optSelectedRank, setOptSelectedRank] = useState<number>(0);

  // ── Build param_ranges from optParamRanges config ─────────────────────────
  const buildParamRanges = (): Record<string, number[]> => {
    const ranges: Record<string, number[]> = {};
    for (const [key, cfg] of Object.entries(optParamRanges)) {
      if (!cfg.values || cfg.values.length === 0) {
        // Generate from min/max/step
        const vals: number[] = [];
        for (let v = cfg.min; v <= cfg.max; v += cfg.step) {
          vals.push(Math.round(v * 1000) / 1000);
        }
        ranges[key] = vals;
      } else {
        ranges[key] = cfg.values;
      }
    }
    return ranges;
  };

  // ── Auto-initialize param ranges when strategy/template changes ────────────
  const initParamRanges = useCallback(() => {
    const tpl = templates.find(t => t.id === selectedType);
    if (!tpl || !tpl.params || tpl.params.length === 0) return;
    const newRanges: Record<string, { min: number; max: number; step: number; values: number[] }> = {};
    for (const p of tpl.params) {
      const step = p.step || Math.max(1, Math.round((p.max - p.min) / 5));
      const defaultValues: number[] = [];
      for (let v = p.default; v >= p.min; v -= step) {
        defaultValues.unshift(v);
      }
      for (let v = p.default + step; v <= p.max; v += step) {
        defaultValues.push(v);
      }
      newRanges[p.key] = { min: p.min, max: p.max, step, values: defaultValues };
    }
    setOptParamRanges(newRanges);
  }, [selectedType, templates]);

  useEffect(() => {
    if (backtestMode === "optimize" && selectedType) {
      initParamRanges();
    }
  }, [backtestMode, selectedType, initParamRanges]);

  const handleOptRun = async () => {
    const ranges = buildParamRanges();
    if (Object.keys(ranges).length === 0) {
      setOptError("请至少配置一个参数的优化范围");
      return;
    }
    setOptRunning(true);
    setOptError(null);
    setOptResult(null);
    try {
      const res = await fetch("/api/v1/strategy/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_type: selectedType,
          symbol,
          interval,
          limit,
          initial_capital: initialCapital,
          commission: optCommission,
          slippage: optSlippage,
          param_ranges: ranges,
          max_combos: 5000,
          algorithm: optAlgorithm,
          n_trials: optNTrials,
          target_metric: optTargetMetric,
          use_numba: false,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "参数优化失败");
      setOptResult(data as OptimizeResultFull);
    } catch (err: any) {
      setOptError(err.message);
    } finally {
      setOptRunning(false);
    }
  };

  const handleOptApplyToBacktest = () => {
    if (!optResult) return;
    // Switch to single mode and set the best params
    setSelectedType(optResult.strategy_type);
    const tpl = templates.find(t => t.id === optResult.strategy_type);
    if (tpl) {
      const newParams: Record<string, number> = {};
      for (const p of tpl.params) {
        newParams[p.key] = optResult.best_params[p.key] ?? p.default;
      }
      setParamValues(newParams);
    }
    setBacktestMode("single");
  };

  const handleOptSaveTemplate = async () => {
    if (!optResult) return;
    try {
      const res = await fetch(`/api/v1/strategy/templates/${optResult.strategy_type}/params`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          params: optSelectedParams || optResult.best_params,
          updated_by: "optimization",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "保存失败");
      // Refresh templates
      const tRes = await fetch("/api/v1/strategy/templates");
      const tData = await tRes.json();
      setTemplates(tData.templates || []);
      setOptSaveDialogOpen(false);
    } catch (err: any) {
      setOptError(err.message);
    }
  };

  const handleOptGeneratePaperBot = async () => {
    if (!optResult) return;
    const params = optSelectedParams || optResult.best_params;
    try {
      const res = await fetch("/api/v1/strategy/optimize/create-paper-bot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_type: optResult.strategy_type,
          symbol: optResult.symbol,
          interval: optResult.interval,
          params,
          initial_capital: initialCapital,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "创建 Paper Bot 失败");
      window.open("/hummingbot", "_blank");
    } catch (err: any) {
      setOptError(err.message);
    }
  };

  const handleOptGenerateTestnetBot = async () => {
    if (!optResult) return;
    const params = optSelectedParams || optResult.best_params;
    try {
      const res = await fetch("/api/v1/strategy/optimize/create-testnet-bot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_type: optResult.strategy_type,
          symbol: optResult.symbol,
          interval: optResult.interval,
          params,
          initial_capital: initialCapital,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "创建 Testnet Bot 失败");
      window.open("/hummingbot-testnet", "_blank");
    } catch (err: any) {
      setOptError(err.message);
    }
  };

  const handleOptRunWFA = () => {
    if (!optResult) return;
    const params = optSelectedParams || optResult.best_params;
    // Switch to WFA mode with selected params pre-set
    setSelectedType(optResult.strategy_type);
    const tpl = templates.find(t => t.id === optResult.strategy_type);
    if (tpl) {
      const newParams: Record<string, number> = {};
      for (const p of tpl.params) {
        newParams[p.key] = params[p.key] ?? p.default;
      }
      setParamValues(newParams);
    }
    setBacktestMode("wfa");
  };

  const handleOptSelectRank = (item: OptimizeResultItem, rank: number) => {
    setOptSelectedParams(item.params);
    setOptSelectedRank(rank);
  };

  const handleWfaRun = async () => {
    setWfaRunning(true);
    setWfaError(null);
    try {
      // 1. 根据当前配置推算 WFA 需要的时间和天数参数
      let start_time = startTime ? new Date(startTime) : new Date(Date.now() - limit * 24 * 3600 * 1000);
      let end_time = endTime ? new Date(endTime) : new Date();

      const totalMs = end_time.getTime() - start_time.getTime();
      const totalDays = Math.max(30, Math.floor(totalMs / (24 * 3600 * 1000)));

      // 计算 is_days, oos_days
      const ratioFactor = wfaTrainRatio / (1 - wfaTrainRatio);
      const oos_days = Math.floor(totalDays / (ratioFactor + wfaWindowsCount)) || 1;
      const is_days = Math.floor(oos_days * ratioFactor) || 1;

      const requestBody: Record<string, any> = {
        strategy_type: selectedType,
        symbol,
        interval,
        is_days: is_days,
        oos_days: oos_days,
        step_days: oos_days,
        start_time: start_time.toISOString(),
        end_time: end_time.toISOString(),
        initial_capital: initialCapital,
        n_trials: 20,
        use_numba: false,
        embargo_days: 0
      };

      const res = await fetch("/api/v1/walk-forward/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      const data = await res.json();
      if (!res.ok) {
        setWfaError(data.detail || data.message || "WFA 分析失败");
        setWfaRunning(false);
        return;
      }

      const sessionId = data.session_id;

      // 2. 轮询状态
      const pollSession = async () => {
        try {
          const sessionRes = await fetch(`/api/v1/walk-forward/sessions/${sessionId}`);
          if (!sessionRes.ok) throw new Error("获取会话状态失败");
          const sessionData = await sessionRes.json();
          
          if (sessionData.status === "failed") {
            setWfaError(sessionData.error_message || "WFA 运行失败");
            setWfaRunning(false);
          } else if (sessionData.status === "completed") {
            const windowsRes = await fetch(`/api/v1/walk-forward/sessions/${sessionId}/windows`);
            const windowsData = await windowsRes.json();
            
            const resultObj = {
              overall_wfe: sessionData.metrics?.overall_wfe ?? sessionData.metrics?.stability_analysis?.average_wfe ?? 0,
              average_test_annual_return: sessionData.metrics?.avg_oos_annual_return ?? sessionData.metrics?.total_oos_return ?? 0,
              total_test_trades: sessionData.metrics?.total_oos_trades || 0,
              oos_equity_curve: sessionData.equity_curve || [],
              windows: windowsData.map((w: any) => ({
                window_index: w.window_index,
                train_start: w.is_start_time,
                train_end: w.is_end_time,
                test_start: w.oos_start_time,
                test_end: w.oos_end_time,
                train_metrics: {
                  annual_return: w.is_metrics?.return ?? w.is_metrics?.annual_return ?? 0,
                  ...w.is_metrics
                },
                test_metrics: {
                  annual_return: w.oos_metrics?.return ?? 0,
                  win_rate: w.oos_metrics?.win_rate ?? 50,
                  ...w.oos_metrics
                },
                wfe: w.wfe,
                best_params: w.best_params
              }))
            };
            
            // Fallback: calculate average from windows if not provided by backend
            if (!resultObj.average_test_annual_return && windowsData.length > 0) {
              const annualReturns = windowsData
                .filter((w: any) => w.oos_metrics?.annual_return)
                .map((w: any) => w.oos_metrics.annual_return);
              if (annualReturns.length > 0) {
                resultObj.average_test_annual_return = annualReturns.reduce((a: number, b: number) => a + b, 0) / annualReturns.length;
              } else {
                // Last resort: use simple return average
                const totalRet = windowsData.reduce((acc: number, w: any) => acc + (w.oos_metrics?.return || 0), 0);
                resultObj.average_test_annual_return = totalRet / windowsData.length;
              }
            }
            
            // Fallback: sum trades from windows if not provided
            if (!resultObj.total_test_trades && windowsData.length > 0) {
              resultObj.total_test_trades = windowsData.reduce((acc: number, w: any) => acc + (w.oos_metrics?.trades || 0), 0);
            }
            
            setWfaResult(resultObj);
            setWfaRunning(false);
          } else {
            // pending or running
            setTimeout(pollSession, 2000);
          }
        } catch (e) {
          setWfaError("轮询状态时发生网络错误: " + String(e));
          setWfaRunning(false);
        }
      };
      
      setTimeout(pollSession, 2000);
    } catch (e) {
      setWfaError("网络错误: " + String(e));
      setWfaRunning(false);
    }
  };

  const symbols = [
    { value: "BTCUSDT", label: "BTC/USDT" }, { value: "ETHUSDT", label: "ETH/USDT" },
    { value: "SOLUSDT", label: "SOL/USDT" }, { value: "BNBUSDT", label: "BNB/USDT" },
    { value: "DOGEUSDT", label: "DOGE/USDT" }, { value: "XRPUSDT", label: "XRP/USDT" },
  ];
  const intervals = [
    { value: "15m", label: "15分钟" }, { value: "1h", label: "1小时" },
    { value: "4h", label: "4小时" }, { value: "1d", label: "1天" },
    { value: "1w", label: "1周" },   { value: "1M", label: "1月" },
  ];
  const limitOptions = [
    { value: 200, label: "200 根" }, { value: 500, label: "500 根" },
    { value: 1000, label: "1000 根" }, { value: 2000, label: "2000 根" },
  ];

  // Fetch templates
  useEffect(() => {
    fetch("/api/v1/strategy/templates").then(r => r.json()).then(d => {
      setTemplates(d.templates || []);
      if (d.templates?.length) {
        const first = d.templates[0];
        setSelectedType(first.id);
        const defaults: Record<string, number> = {};
        first.params.forEach((p: ParamDef) => { defaults[p.key] = p.default; });
        setParamValues(defaults);
      }
    }).catch(() => {});
  }, []);

  // Update defaults when template changes
  useEffect(() => {
    const tpl = templates.find(t => t.id === selectedType);
    if (!tpl) return;
    const defaults: Record<string, number> = {};
    tpl.params.forEach(p => { defaults[p.key] = p.default; });
    setParamValues(defaults);
  }, [selectedType, templates]);

  // Fetch history
  const fetchHistory = useCallback(() => {
    fetch("/api/v1/strategy/backtest/history?limit=50").then(r => r.json()).then(d => {
      setHistory(d.history || []);
    }).catch(() => {});
  }, []);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  // Launch Paper Bot state
  const [launchTarget, setLaunchTarget] = useState<any>(null);
  const [launchDialogOpen, setLaunchDialogOpen] = useState(false);
  const [launchLoading, setLaunchLoading] = useState(false);
  const [launchResult, setLaunchResult] = useState<any>(null);

  // Launch Paper Bot handler
  const handleLaunchPaperBot = useCallback((backtestResult: any) => {
    setLaunchTarget(backtestResult);
    setLaunchResult(null);
    setLaunchDialogOpen(true);
  }, []);

  const handleLaunchConfirm = useCallback(async (botName: string, paperBalance: number, orderAmount: number) => {
    if (!launchTarget?.id) return;
    setLaunchLoading(true);
    try {
      const params = new URLSearchParams({
        bot_name: botName,
        paper_initial_balance: String(paperBalance),
        order_amount: String(orderAmount),
      });
      const res = await fetch(
        `/api/v1/analytics/backtest/${launchTarget.id}/create-paper-bot?${params}`,
        { method: "POST" }
      );
      const data = await res.json();
      setLaunchResult(data);
      if (data.data?.paper_bot_id) {
        setTimeout(() => {
          setLaunchDialogOpen(false);
          window.location.href = "/hummingbot";
        }, 2000);
      }
    } catch (e) {
      setLaunchResult({ error: "网络错误，创建失败" });
    } finally {
      setLaunchLoading(false);
    }
  }, [launchTarget]);

  // Delete handler
  const handleDeleteRecord = useCallback(async (record: any) => {
    if (!record.id) return;
    try {
      const res = await fetch(`/api/v1/strategy/backtest/history/${record.id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        // Remove from history list
        const newHistory = history.filter(h => h.id !== record.id);
        setHistory(newHistory);
        // Clear current result if it was showing the deleted record
        if (result?.id === record.id) {
          setResult(null);
        }
        // 如果删除后历史列表为空，也清理当前显示
        if (newHistory.length === 0) {
          setResult(null);
        }
      } else {
        const data = await res.json();
        setError(data.detail || "删除失败");
      }
    } catch (e) {
      setError("网络错误，删除失败");
    } finally {
      setDeleteTarget(null);
    }
  }, [result?.id, history]);

  const currentTemplate = templates.find(t => t.id === selectedType);

  // Auto-save params after successful backtest
  const autoSaveParams = async (strategyType: string, params: Record<string, number>) => {
    try {
      await fetch(`/api/v1/strategy/templates/${strategyType}/params`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          params,
          updated_by: "manual_backtest"
        }),
      });
      // Also refresh templates to reflect new defaults
      fetch("/api/v1/strategy/templates")
        .then(r => r.json())
        .then(d => {
          if (Array.isArray(d)) setTemplates(d);
          else if (Array.isArray(d?.templates)) setTemplates(d.templates);
        })
        .catch(() => {});
    } catch (e) {
      console.error("Failed to auto-save params:", e);
    }
  };

  const handleRun = async () => {
    setRunning(true); setError(null);
    try {
      const requestBody: Record<string, any> = {
        strategy_type:   selectedType,
        symbol,
        interval,
        limit,
        initial_capital: initialCapital,
        params:          paramValues,
      };
      // Add date range if both are specified
      if (startTime && endTime) {
        requestBody.start_time = new Date(startTime).toISOString();
        requestBody.end_time = new Date(endTime).toISOString();
      }
      const res = await fetch("/api/v1/strategy/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "回测失败"); return; }
      setResult(data);
      fetchHistory();
      
      // Auto-save params to database for sync across pages
      autoSaveParams(selectedType, paramValues);
    } catch (e) {
      setError("网络错误，请检查后端连接");
    } finally {
      setRunning(false);
    }
  };

  // Composition backtest handler
  const handleCompositionRun = async () => {
    // Input validation: require at least 2 strategies
    if (selectedStrategies.length < 2) {
      setCompositionError("请至少选择 2 个策略进行组合对比");
      return;
    }
    
    setCompositionRunning(true);
    setCompositionError(null);
    try {
      const res = await fetch("/api/v1/strategy/composition/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          atomic_strategies: selectedStrategies,
          symbol,
          interval,
          data_limit: limit,
          initial_capital: initialCapital,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        // Extract detailed error message from response
        const errorMsg = data.detail || data.message || data.error || `请求失败 (${res.status}: ${res.statusText})`;
        setCompositionError(errorMsg);
        return;
      }
      setCompositionResult(data);
    } catch (e) {
      // Log detailed error for debugging
      const errorMessage = e instanceof Error ? e.message : String(e);
      console.error("Composition run error:", errorMessage);
      setCompositionError(`网络错误: ${errorMessage}`);
    } finally {
      setCompositionRunning(false);
    }
  };

  const m = result?.metrics;

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-40">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-slate-100">QuantAgent OS</h1>
                <p className="text-[10px] text-slate-400">策略回测可视化</p>
              </div>
            </div>
            <nav className="hidden md:flex items-center gap-1">
              <Link href="/dashboard" className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-all flex items-center gap-1.5">
                <LayoutDashboard className="w-4 h-4" /> 仪表盘
              </Link>
              <span className="px-3 py-1.5 text-sm text-blue-400 bg-blue-500/10 rounded-lg border border-blue-500/20 font-medium flex items-center gap-1.5">
                <BarChart2 className="w-4 h-4" /> 回测
              </span>
              <Link href="/replay" className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-all flex items-center gap-1.5">
                <History className="w-4 h-4" /> 历史回放
              </Link>
              <Link href="/strategies" className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-all flex items-center gap-1.5">
                <BookOpen className="w-4 h-4" /> 策略库
              </Link>
              <Link href="/terminal" className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-all flex items-center gap-1.5">
                <Terminal className="w-4 h-4" /> 终端
              </Link>
              <Link href="/hummingbot" className="px-3 py-1.5 text-sm text-cyan-400 hover:text-cyan-100 hover:bg-cyan-500/10 rounded-lg transition-all flex items-center gap-1.5">
                <Server className="w-4 h-4" /> Hummingbot
              </Link>
            </nav>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6">
        {/* Mode Switcher Tab */}
        <div className="flex items-center gap-1 bg-slate-800/50 p-1 rounded-xl border border-slate-700/50 mb-6">
          <button
            onClick={() => setBacktestMode("single")}
            className={`px-4 py-2 text-sm rounded-lg transition-all ${
              backtestMode === "single"
                ? "bg-blue-600/20 text-blue-400 border border-blue-500/30 font-medium"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4" />
              单一策略
            </div>
          </button>
          <button
            onClick={() => setBacktestMode("composition")}
            className={`px-4 py-2 text-sm rounded-lg transition-all ${
              backtestMode === "composition"
                ? "bg-purple-600/20 text-purple-400 border border-purple-500/30 font-medium"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4" />
              策略组合
            </div>
          </button>
          <button
            onClick={() => { setBacktestMode("wfa"); }}
            className={`px-4 py-2 text-sm rounded-lg transition-all ${
              backtestMode === "wfa"
                ? "bg-orange-600/20 text-orange-400 border border-orange-500/30 font-medium"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center gap-2">
              <RefreshCw className="w-4 h-4" />
              推进分析 (WFA)
            </div>
          </button>
          <button
            onClick={() => { setBacktestMode("optimize"); }}
            className={`px-4 py-2 text-sm rounded-lg transition-all ${
              backtestMode === "optimize"
                ? "bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 font-medium"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              参数优化
            </div>
          </button>
        </div>

        {/* Single Strategy Mode */}
        {backtestMode === "single" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* ── Left: Config Panel ── */}
            <div className="lg:col-span-1 space-y-4">
            {/* Strategy Selection */}
            <Card className="bg-slate-900 border-slate-700/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                  <div className="w-6 h-6 bg-blue-500/10 rounded flex items-center justify-center border border-blue-500/20">
                    <Activity className="w-3.5 h-3.5 text-blue-400" />
                  </div>
                  选择策略
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-2">
                  {templates.map(t => (
                    <button
                      key={t.id}
                      onClick={() => setSelectedType(t.id)}
                      className={`w-full text-left p-3 rounded-xl border transition-all ${
                        selectedType === t.id
                          ? "bg-blue-600/20 border-blue-500/50 text-blue-300"
                          : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-slate-200 hover:border-slate-600"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <p className="font-medium text-sm">{t.name}</p>
                        {selectedType === t.id && <CheckCircle2 className="w-4 h-4 text-blue-400" />}
                      </div>
                      <p className="text-[11px] mt-0.5 opacity-70">{(t.description || '').slice(0, 40)}…</p>
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Strategy Parameters */}
            {currentTemplate && currentTemplate.params.length > 0 && (
              <Card className="bg-slate-900 border-slate-700/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                    <div className="w-6 h-6 bg-purple-500/10 rounded flex items-center justify-center border border-purple-500/20">
                      <Activity className="w-3.5 h-3.5 text-purple-400" />
                    </div>
                    策略参数
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {currentTemplate.params.map(p => (
                    <div key={p.key}>
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-1.5">
                          <label className="text-xs text-slate-300">{p.label}</label>
                          {p.description && (
                            <div className="group relative">
                              <HelpCircle className="w-3.5 h-3.5 text-slate-500 hover:text-blue-400 cursor-help transition-colors" />
                              <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 w-56 p-2.5 bg-slate-800 border border-slate-600 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                                <p className="text-[11px] text-slate-300 leading-relaxed">{p.description}</p>
                                <div className="absolute left-1/2 -translate-x-1/2 top-full -mt-1 border-4 border-transparent border-t-slate-600" />
                              </div>
                            </div>
                          )}
                        </div>
                        <span className="text-xs font-mono text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded">
                          {paramValues[p.key] ?? p.default}
                        </span>
                      </div>
                      <input
                        type="range"
                        min={p.min}
                        max={p.max}
                        step={p.step ?? (p.type === "int" ? 1 : 0.5)}
                        value={paramValues[p.key] ?? p.default}
                        onChange={e => setParamValues(prev => ({
                          ...prev,
                          [p.key]: p.type === "int" ? parseInt(e.target.value) : parseFloat(e.target.value),
                        }))}
                        className="w-full h-1.5 bg-slate-700 rounded-full appearance-none cursor-pointer accent-blue-500"
                      />
                      <div className="flex justify-between mt-0.5">
                        <span className="text-[9px] text-slate-600">{p.min}</span>
                        <span className="text-[9px] text-slate-600">{p.max}</span>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Market Config */}
            <MarketConfigPanel
              symbol={symbol} setSymbol={setSymbol}
              interval={interval} setIntervalVal={setIntervalVal}
              limit={limit} setLimit={setLimit}
              startTime={startTime} setStartTime={setStartTime}
              endTime={endTime} setEndTime={setEndTime}
              initialCapital={initialCapital} setInitialCapital={setInitialCapital}
              symbols={symbols} intervals={intervals} limitOptions={limitOptions}
              accentColor="blue"
            />

            {/* Run Button */}
            <Button
              onClick={handleRun}
              disabled={running}
              className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-xl text-sm"
            >
              {running
                ? <><RefreshCw className="w-4 h-4 animate-spin mr-2" />回测运行中...</>
                : <><Play className="w-4 h-4 mr-2" />运行回测</>}
            </Button>

            {error && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-xs flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                {error}
              </div>
            )}
          </div>

          {/* ── Right: Results ── */}
          <div className="lg:col-span-2 space-y-6">
            {!result ? (
              <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-500 space-y-4">
                <div className="w-20 h-20 bg-slate-800/50 rounded-2xl flex items-center justify-center border border-slate-700/50">
                  <BarChart2 className="w-10 h-10 opacity-30" />
                </div>
                <div className="text-center">
                  <p className="text-base font-medium text-slate-400">选择策略并运行回测</p>
                  <p className="text-sm text-slate-600 mt-1">结果将在此处显示，包含资产曲线和详细指标</p>
                </div>
              </div>
            ) : (
              <>
                {/* Result Header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/20 text-xs">
                      {result.strategy_type.toUpperCase()}
                    </Badge>
                    <Badge variant="outline" className="bg-slate-700 text-slate-300 border-slate-600 text-xs">
                      {result.symbol} / {result.interval}
                    </Badge>
                    <span className="text-xs text-slate-500">{(result.metrics?.total_trades ?? result.trades?.length ?? 0)} 笔交易</span>
                  </div>
                  <span className="text-xs text-slate-500">{new Date(result.created_at).toLocaleString()}</span>
                </div>

                {/* Metrics Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <MetricCard
                    label="总收益率"
                    value={`${(m!.total_return ?? 0) >= 0 ? "+" : ""}${(m!.total_return ?? 0).toFixed(2)}%`}
                    positive={(m!.total_return ?? 0) >= 0}
                  />
                  <MetricCard
                    label="年化收益率"
                    value={`${(m!.annual_return ?? 0) >= 0 ? "+" : ""}${(m!.annual_return ?? 0).toFixed(2)}%`}
                    positive={(m!.annual_return ?? 0) >= 0}
                  />
                  <MetricCard
                    label="最大回撤"
                    value={`-${(m!.max_drawdown ?? 0).toFixed(2)}%`}
                    positive={false}
                    sub="越小越好"
                  />
                  <MetricCard
                    label="夏普比率"
                    value={(m!.sharpe_ratio ?? 0).toFixed(3)}
                    positive={(m!.sharpe_ratio ?? 0) >= 1}
                    sub={(m!.sharpe_ratio ?? 0) >= 2 ? "优秀" : (m!.sharpe_ratio ?? 0) >= 1 ? "良好" : (m!.sharpe_ratio ?? 0) >= 0.5 ? "一般" : "较差"}
                  />
                  <MetricCard label="胜率" value={`${(m!.win_rate ?? 0).toFixed(1)}%`} positive={(m!.win_rate ?? 0) >= 50} />
                  <MetricCard label="盈亏比" value={(m!.profit_factor ?? 0) >= 999 ? "∞" : (m!.profit_factor ?? 0).toFixed(2)} positive={(m!.profit_factor ?? 0) >= 1.5} />
                  <MetricCard label="总交易次数" value={String(m!.total_trades ?? 0)} />
                  <MetricCard
                    label="最终资金"
                    value={`$${(m!.final_capital ?? m!.initial_capital ?? 10000).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
                    positive={(m!.final_capital ?? m!.initial_capital ?? 10000) >= (m!.initial_capital ?? 10000)}
                    sub={`初始 $${(m!.initial_capital ?? 10000).toLocaleString()}`}
                  />
                </div>

                {/* Equity Curve */}
                <Card className="bg-slate-900 border-slate-700/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-blue-400" />
                      资产曲线
                      <span className="text-xs font-normal text-slate-400 ml-1">({(result.equity_curve || []).length} 个数据点)</span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0 pb-2">
                    <EquityCurveChart
                      data={result.equity_curve || []}
                      baselineData={result.baseline_curve ?? []}
                      markers={result.markers ?? []}
                      initialCapital={m!.initial_capital}
                    />
                  </CardContent>
                </Card>

                {/* Launch Paper Bot Button */}
                <div className="flex items-center justify-end gap-2">
                  <Button
                    onClick={() => handleLaunchPaperBot(result)}
                    className="h-8 text-xs bg-green-600 hover:bg-green-500 text-white"
                  >
                    <Play className="w-3 h-3 mr-1" />
                    启动 Paper Bot 验证
                  </Button>
                </div>

                {/* Trade List */}
                {(result.trades || []).length > 0 && (
                  <Card className="bg-slate-900 border-slate-700/50">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                        <Clock className="w-4 h-4 text-purple-400" />
                        交易记录
                        <span className="text-xs font-normal text-slate-400">（前 {Math.min((result.trades || []).length, 20)} 笔，共 {(result.trades || []).length} 笔）</span>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0 pb-2">
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-slate-800">
                              {["建仓时间", "平仓时间", "建仓价", "平仓价", "数量", "盈亏", "盈亏%"].map(h => (
                                <th key={h} className="px-3 py-2 text-left text-slate-400 font-medium">{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {(result.trades || []).slice(0, 20).map((t, i) => (
                              <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                                <td className="px-3 py-2 text-slate-400 font-mono">{t.entry_time.slice(0, 16)}</td>
                                <td className="px-3 py-2 text-slate-400 font-mono">{t.exit_time.slice(0, 16)}</td>
                                <td className="px-3 py-2 text-slate-300 font-mono">${Number(t.entry_price).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                                <td className="px-3 py-2 text-slate-300 font-mono">${Number(t.exit_price).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                                <td className="px-3 py-2 text-slate-400 font-mono">{Number(t.quantity).toFixed(6)}</td>
                                <td className={`px-3 py-2 font-mono font-bold ${t.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                                  {t.pnl >= 0 ? "+" : ""}${Number(t.pnl).toFixed(2)}
                                </td>
                                <td className={`px-3 py-2 font-mono ${t.pnl_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                                  {t.pnl_pct >= 0 ? "+" : ""}{Number(t.pnl_pct).toFixed(2)}%
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            )}

            {/* History */}
            {history.length > 0 && (
              <Card className="bg-slate-900 border-slate-700/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                    <Clock className="w-4 h-4 text-slate-400" />
                    历史回测记录
                    <span className="text-xs text-slate-500 font-normal">（{history.length} 条）</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                  {history.map((h, i) => {
                    const ret = h.metrics?.total_return ?? 0;
                    return (
                      <div key={i} className="flex items-center justify-between p-3 bg-slate-800/50 rounded-xl border border-slate-700/50 hover:border-slate-600/50 transition-colors group">
                        <div className="flex items-center gap-3 flex-1 cursor-pointer" onClick={() => setResult(h as any)}>
                          <Badge variant="outline" className="text-[10px] bg-blue-500/10 text-blue-400 border-blue-500/20">
                            {h.strategy_type}
                          </Badge>
                          <span className="text-sm text-slate-300">{h.symbol} / {h.interval}</span>
                          <span className="text-xs text-slate-500">{(h.metrics?.total_trades ?? h.trades?.length ?? 0)} 笔</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`text-sm font-bold ${ret >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {ret >= 0 ? "+" : ""}{ret.toFixed(2)}%
                          </span>
                          <span className="text-[10px] text-slate-500">{new Date(h.created_at).toLocaleDateString()}</span>
                          <button
                            onClick={(e) => { e.stopPropagation(); setDeleteTarget(h); }}
                            className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100"
                            title="删除记录"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                          <ChevronRight className="w-4 h-4 text-slate-600" />
                        </div>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
        )}

        {/* Composition Mode */}
        {backtestMode === "composition" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* ── Left: Composition Config Panel ── */}
          <div className="lg:col-span-1 space-y-4">
            {/* Strategy Multi-Select */}
            <Card className="bg-slate-900 border-slate-700/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                  <div className="w-6 h-6 bg-purple-500/10 rounded flex items-center justify-center border border-purple-500/20">
                    <Layers className="w-3.5 h-3.5 text-purple-400" />
                  </div>
                  选择策略（多选）
                  <Badge variant="outline" className="text-[10px] bg-purple-500/10 text-purple-400 border-purple-500/20 ml-auto">
                    已选 {selectedStrategies.length} 个
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {templates
                  .filter(t => !["smart_beta", "basis"].includes(t.id))
                  .map(t => (
                    <label
                      key={t.id}
                      className={`flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer transition-all ${
                        selectedStrategies.includes(t.id)
                          ? "border-purple-500/50 bg-purple-500/10"
                          : "border-slate-700/50 hover:border-slate-600/50"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedStrategies.includes(t.id)}
                        onChange={e => {
                          if (e.target.checked) {
                            setSelectedStrategies(prev => [...prev, t.id]);
                          } else {
                            setSelectedStrategies(prev => prev.filter(s => s !== t.id));
                          }
                        }}
                        className="accent-purple-500 w-4 h-4"
                      />
                      <div className="flex-1">
                        <p className="text-sm text-slate-200">{t.name}</p>
                        <p className="text-[10px] text-slate-500">{(t.description || "").slice(0, 50)}</p>
                      </div>
                    </label>
                  ))}
                {selectedStrategies.length < 2 && (
                  <p className="text-[11px] text-amber-400 mt-2 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    请至少选择 2 个策略
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Composition Type */}
            <Card className="bg-slate-900 border-slate-700/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-slate-100 text-sm">组合方式</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {[
                  { value: "weighted", label: "加权组合", desc: "对各策略信号加权求和" },
                  { value: "voting", label: "投票组合", desc: "多数投票决策机制" }
                ].map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => setCompositionType(opt.value as "weighted" | "voting")}
                    className={`w-full text-left p-3 rounded-xl border transition-all ${
                      compositionType === opt.value
                        ? "bg-purple-600/20 border-purple-500/50 text-purple-300"
                        : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <p className="font-medium text-sm">{opt.label}</p>
                    <p className="text-[10px] mt-0.5 opacity-70">{opt.desc}</p>
                  </button>
                ))}
              </CardContent>
            </Card>

            {/* Market Config (reused) */}
            <MarketConfigPanel
              symbol={symbol} setSymbol={setSymbol}
              interval={interval} setIntervalVal={setIntervalVal}
              limit={limit} setLimit={setLimit}
              startTime={startTime} setStartTime={setStartTime}
              endTime={endTime} setEndTime={setEndTime}
              initialCapital={initialCapital} setInitialCapital={setInitialCapital}
              symbols={symbols} intervals={intervals} limitOptions={limitOptions}
              accentColor="purple"
            />

            {/* Run Button */}
            <Button
              onClick={handleCompositionRun}
              disabled={compositionRunning || selectedStrategies.length < 2}
              className="w-full bg-purple-600 hover:bg-purple-500 text-white font-bold py-3 rounded-xl text-sm"
            >
              {compositionRunning
                ? <><RefreshCw className="w-4 h-4 animate-spin mr-2" />组合对比运行中...</>
                : <><Play className="w-4 h-4 mr-2" />运行组合对比</>}
            </Button>

            {compositionError && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-xs flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                {compositionError}
              </div>
            )}
          </div>

          {/* ── Right: Composition Results ── */}
          <div className="lg:col-span-2 space-y-6">
            {!compositionResult ? (
              <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-500 space-y-4">
                <div className="w-20 h-20 bg-slate-800/50 rounded-2xl flex items-center justify-center border border-slate-700/50">
                  <Layers className="w-10 h-10 opacity-30" />
                </div>
                <div className="text-center">
                  <p className="text-base font-medium text-slate-400">选择策略组合并运行对比</p>
                  <p className="text-sm text-slate-600 mt-1">选择至少 2 个策略，运行后查看组合与单策略的对比结果</p>
                </div>
              </div>
            ) : compositionResult.success === false ? (
              <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-500 space-y-4">
                <div className="w-20 h-20 bg-red-500/10 rounded-2xl flex items-center justify-center border border-red-500/20">
                  <AlertTriangle className="w-10 h-10 text-red-400" />
                </div>
                <div className="text-center">
                  <p className="text-base font-medium text-red-400">组合对比运行失败</p>
                  <p className="text-sm text-slate-500 mt-1">{compositionResult.message || "请检查策略参数或数据后重试"}</p>
                </div>
              </div>
            ) : !compositionResult.comparisons || Object.keys(compositionResult.comparisons || {}).length === 0 ? (
              <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-500 space-y-4">
                <div className="w-20 h-20 bg-amber-500/10 rounded-2xl flex items-center justify-center border border-amber-500/20">
                  <Info className="w-10 h-10 text-amber-400" />
                </div>
                <div className="text-center">
                  <p className="text-base font-medium text-amber-400">无有效对比数据</p>
                  <p className="text-sm text-slate-500 mt-1">运行完成但未生成有效结果，请检查数据源或策略配置</p>
                </div>
              </div>
            ) : (
              <>
                {/* Result Title Bar */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Badge className="bg-purple-500/10 text-purple-400 border-purple-500/20">策略组合对比</Badge>
                    <Badge variant="outline" className="bg-slate-700 text-slate-300 border-slate-600 text-xs">
                      {symbol} / {interval}
                    </Badge>
                    <span className="text-xs text-slate-500">{selectedStrategies.length} 个策略</span>
                  </div>
                  <span className="text-xs text-slate-500">
                    {compositionResult.comparison_time ? new Date(compositionResult.comparison_time).toLocaleString() : ""}
                  </span>
                </div>

                {/* Equity Curve Comparison Chart */}
                <Card className="bg-slate-900 border-slate-700/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-purple-400" />
                      权益曲线对比
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0 pb-2">
                    <CompositionCompareChart
                      equityCurves={Object.fromEntries(
                        Object.entries(compositionResult.equity_curves || {}).filter(
                          ([, v]) => v && Array.isArray(v) && v.length > 0
                        )
                      ) as Record<string, { t: string; v: number }[]>}
                      initialCapital={initialCapital}
                      height={360}
                    />
                  </CardContent>
                </Card>

                {/* Metrics Comparison Table */}
                <Card className="bg-slate-900 border-slate-700/50">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                      <BarChart2 className="w-4 h-4 text-blue-400" />
                      指标对比
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <MetricsComparisonTable
                      comparisons={compositionResult.comparisons}
                      atomicStrategies={compositionResult.atomic_strategies}
                      templates={templates}
                    />
                  </CardContent>
                </Card>

                {/* Weight Distribution */}
                {compositionResult.weight_distribution && (
                  <Card className="bg-slate-900 border-slate-700/50">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                        <Layers className="w-4 h-4 text-green-400" />
                        权重分布
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <WeightDistributionBars
                        weightDistribution={compositionResult.weight_distribution}
                        templates={templates}
                      />
                    </CardContent>
                  </Card>
                )}

                {/* Summary Evaluation Card */}
                <SummaryEvaluationCard
                  comparisons={compositionResult.comparisons}
                  atomicStrategies={compositionResult.atomic_strategies}
                />

                {/* Signal Contribution Analysis */}
                {compositionResult?.signal_stats && Object.keys(compositionResult.signal_stats).length > 0 && (
                  <SignalContributionCard
                    signalStats={compositionResult.signal_stats}
                    templates={templates}
                  />
                )}
              </>
            )}
          </div>
        </div>
        )}

        {/* WFA Mode */}
        {backtestMode === "wfa" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              {/* Strategy Selection */}
              <Card className="bg-slate-900 border-slate-700/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                    <div className="w-6 h-6 bg-orange-500/10 rounded flex items-center justify-center border border-orange-500/20">
                      <RefreshCw className="w-3.5 h-3.5 text-orange-400" />
                    </div>
                    策略选择
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Select value={selectedType} onValueChange={setSelectedType}>
                    <SelectTrigger className="bg-slate-800 border-slate-700 text-slate-200">
                      <SelectValue placeholder="选择策略" />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-800 border-slate-700">
                      {templates.map(t => (
                        <SelectItem key={t.id} value={t.id} className="text-slate-200 focus:bg-slate-700">
                          {t.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </CardContent>
              </Card>

              {/* WFA Specific Config */}
              <Card className="bg-slate-900 border-slate-700/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                    <div className="w-6 h-6 bg-orange-500/10 rounded flex items-center justify-center border border-orange-500/20">
                      <Layers className="w-3.5 h-3.5 text-orange-400" />
                    </div>
                    WFA 参数
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <div className="flex justify-between text-xs text-slate-300 mb-1">
                      <label>训练集比例 (Train Ratio)</label>
                      <span>{(wfaTrainRatio * 100).toFixed(0)}%</span>
                    </div>
                    <input
                      type="range"
                      min={0.3} max={0.9} step={0.05}
                      value={wfaTrainRatio}
                      onChange={e => setWfaTrainRatio(parseFloat(e.target.value))}
                      className="w-full h-1.5 bg-slate-700 rounded-full appearance-none cursor-pointer accent-orange-500"
                    />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs text-slate-300 mb-1">
                      <label>窗口数量 (Windows)</label>
                      <span>{wfaWindowsCount}</span>
                    </div>
                    <input
                      type="range"
                      min={3} max={20} step={1}
                      value={wfaWindowsCount}
                      onChange={e => setWfaWindowsCount(parseInt(e.target.value))}
                      className="w-full h-1.5 bg-slate-700 rounded-full appearance-none cursor-pointer accent-orange-500"
                    />
                  </div>
                </CardContent>
              </Card>

              <MarketConfigPanel
                symbol={symbol} setSymbol={setSymbol}
                interval={interval} setIntervalVal={setIntervalVal}
                limit={limit} setLimit={setLimit}
                startTime={startTime} setStartTime={setStartTime}
                endTime={endTime} setEndTime={setEndTime}
                initialCapital={initialCapital} setInitialCapital={setInitialCapital}
                symbols={symbols} intervals={intervals} limitOptions={limitOptions}
                accentColor="orange"
              />

              {/* Run Button */}
              <Button
                onClick={handleWfaRun}
                disabled={wfaRunning}
                className="w-full bg-orange-600 hover:bg-orange-500 text-white font-bold py-3 rounded-xl text-sm"
              >
                {wfaRunning
                  ? <><RefreshCw className="w-4 h-4 animate-spin mr-2" />WFA 分析中...</>
                  : <><Play className="w-4 h-4 mr-2" />运行 WFA</>}
              </Button>

              {wfaError && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-xs flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  {wfaError}
                </div>
              )}
            </div>

            <div className="lg:col-span-2 space-y-6">
              {!wfaResult ? (
                <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-500 space-y-4">
                  <div className="w-20 h-20 bg-slate-800/50 rounded-2xl flex items-center justify-center border border-slate-700/50">
                    <RefreshCw className="w-10 h-10 opacity-30" />
                  </div>
                  <div className="text-center">
                    <p className="text-base font-medium text-slate-400">运行推进分析 (Walk-Forward Analysis)</p>
                    <p className="text-sm text-slate-600 mt-1">通过滚动窗口回测验证策略参数的稳定性和鲁棒性</p>
                  </div>
                </div>
              ) : (
                <>
                  {/* WFA Result Header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Badge className="bg-orange-500/10 text-orange-400 border-orange-500/20">WFA 结果</Badge>
                      <Badge variant="outline" className="bg-slate-700 text-slate-300 border-slate-600 text-xs">
                        {symbol} / {interval}
                      </Badge>
                      <span className="text-xs text-slate-500">{wfaResult.windows?.length || 0} 个窗口</span>
                    </div>
                  </div>

                  {/* Overview Metrics */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <MetricCard
                      label="整体 WFE"
                      value={`${(wfaResult.overall_wfe * 100).toFixed(2)}%`}
                      positive={wfaResult.overall_wfe >= 0.5}
                      sub={wfaResult.overall_wfe >= 0.5 ? "参数具有一致性" : "存在过拟合风险"}
                    />
                    <MetricCard
                      label="平均样本外年化"
                      value={`${(wfaResult.average_test_annual_return * 100).toFixed(2)}%`}
                      positive={wfaResult.average_test_annual_return >= 0}
                    />
                    <MetricCard
                      label="平均胜率"
                      value={`${((wfaResult.windows?.reduce((acc: number, w: any) => acc + (w.test_metrics?.win_rate || 0), 0) / (wfaResult.windows?.length || 1))).toFixed(1)}%`}
                      positive={true}
                    />
                    <MetricCard
                      label="测试集样本数"
                      value={String(wfaResult.total_test_trades || 0)}
                    />
                  </div>

                  {/* Equity Curve with Window Boundaries */}
                  <Card className="bg-slate-900 border-slate-700/50 overflow-hidden relative z-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-orange-400" />
                        样本外拼接净值曲线 (OOS Equity Curve)
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0 pb-2">
                      <EquityCurveChart
                        data={wfaResult.oos_equity_curve || []}
                        initialCapital={initialCapital}
                        windowBoundaries={wfaResult.windows?.map((w: any) => ({
                          time: w.test_start,
                          label: `W${w.window_index}`,
                          color: "#f59e0b"
                        }))}
                      />
                    </CardContent>
                  </Card>

                  {/* WFE and Param Stability Charts */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <Card className="bg-slate-900 border-slate-700/50">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                          <BarChart3 className="w-4 h-4 text-orange-400" />
                          各窗口 WFE 对比
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <WfeCompareChart data={wfaResult.windows || []} height={250} />
                      </CardContent>
                    </Card>

                    <Card className="bg-slate-900 border-slate-700/50">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                          <Activity className="w-4 h-4 text-orange-400" />
                          最优参数演变
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ParamStabilityChart data={wfaResult.windows || []} height={250} />
                      </CardContent>
                    </Card>
                  </div>

                  {/* Window Details Table */}
                  <Card className="bg-slate-900 border-slate-700/50">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                        <Layers className="w-4 h-4 text-slate-400" />
                        滚动窗口详情
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-slate-800 bg-slate-900">
                              <th className="px-3 py-2 text-left text-slate-400 font-medium">窗口</th>
                              <th className="px-3 py-2 text-left text-slate-400 font-medium">训练集周期</th>
                              <th className="px-3 py-2 text-left text-slate-400 font-medium">测试集周期</th>
                              <th className="px-3 py-2 text-right text-slate-400 font-medium">IS 年化</th>
                              <th className="px-3 py-2 text-right text-slate-400 font-medium">OOS 年化</th>
                              <th className="px-3 py-2 text-right text-slate-400 font-medium">WFE</th>
                              <th className="px-3 py-2 text-left text-slate-400 font-medium">最优参数</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(wfaResult.windows || []).map((w: any, i: number) => {
                              const wfe = w.wfe || 0;
                              const isReturn = w.train_metrics?.annual_return || 0;
                              const oosReturn = w.test_metrics?.annual_return || 0;
                              return (
                                <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                                  <td className="px-3 py-2 text-slate-300 font-medium">W{w.window_index}</td>
                                  <td className="px-3 py-2 text-slate-500 font-mono text-[10px]">
                                    {new Date(w.train_start).toLocaleDateString()} - {new Date(w.train_end).toLocaleDateString()}
                                  </td>
                                  <td className="px-3 py-2 text-slate-500 font-mono text-[10px]">
                                    {new Date(w.test_start).toLocaleDateString()} - {new Date(w.test_end).toLocaleDateString()}
                                  </td>
                                  <td className={`px-3 py-2 text-right font-mono ${isReturn >= 0 ? "text-green-400" : "text-red-400"}`}>
                                    {(isReturn * 100).toFixed(2)}%
                                  </td>
                                  <td className={`px-3 py-2 text-right font-mono ${oosReturn >= 0 ? "text-green-400" : "text-red-400"}`}>
                                    {(oosReturn * 100).toFixed(2)}%
                                  </td>
                                  <td className={`px-3 py-2 text-right font-mono font-bold ${wfe >= 0.5 ? "text-green-400" : wfe > 0 ? "text-amber-400" : "text-red-400"}`}>
                                    {(wfe * 100).toFixed(2)}%
                                  </td>
                                  <td className="px-3 py-2">
                                    <div className="flex flex-wrap gap-1">
                                      {Object.entries(w.best_params || {}).map(([k, v]) => (
                                        <Badge key={k} variant="outline" className="text-[9px] px-1 py-0 bg-slate-800 border-slate-700 text-slate-400">
                                          {k}: {String(v)}
                                        </Badge>
                                      ))}
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  </Card>
                </>
              )}
            </div>
          </div>
        )}

        {backtestMode === "optimize" && (
          <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
            {/* ── Left Config Panel ── */}
            <div className="xl:col-span-1 space-y-4">
              {/* Strategy Selection */}
              <Card className="bg-slate-900 border-slate-700/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                    <div className="w-6 h-6 bg-emerald-500/10 rounded flex items-center justify-center border border-emerald-500/20">
                      <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                    </div>
                    策略选择
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Select value={selectedType} onValueChange={setSelectedType}>
                    <SelectTrigger className="bg-slate-800 border-slate-700 text-slate-200">
                      <SelectValue placeholder="选择策略" />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-800 border-slate-700">
                      {templates.map(t => (
                        <SelectItem key={t.id} value={t.id} className="text-slate-200 focus:bg-slate-700">
                          {t.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <MarketConfigPanel
                    symbol={symbol} setSymbol={setSymbol}
                    interval={interval} setIntervalVal={setIntervalVal}
                    limit={limit} setLimit={setLimit}
                    startTime={startTime} setStartTime={setStartTime}
                    endTime={endTime} setEndTime={setEndTime}
                    initialCapital={initialCapital} setInitialCapital={setInitialCapital}
                    symbols={[
                      { value: "BTCUSDT", label: "BTC/USDT" },
                      { value: "ETHUSDT", label: "ETH/USDT" },
                      { value: "SOLUSDT", label: "SOL/USDT" },
                    ]}
                    intervals={[
                      { value: "15m", label: "15 分钟" },
                      { value: "1h", label: "1 小时" },
                      { value: "4h", label: "4 小时" },
                      { value: "1d", label: "1 天" },
                    ]}
                    limitOptions={[
                      { value: 300, label: "300 根" },
                      { value: 500, label: "500 根" },
                      { value: 1000, label: "1000 根" },
                      { value: 2000, label: "2000 根" },
                    ]}
                    accentColor="green"
                  />
                </CardContent>
              </Card>

              {/* Algorithm & Optimization Config */}
              <Card className="bg-slate-900 border-slate-700/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                    <div className="w-6 h-6 bg-emerald-500/10 rounded flex items-center justify-center border border-emerald-500/20">
                      <BarChart3 className="w-3.5 h-3.5 text-emerald-400" />
                    </div>
                    优化配置
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Algorithm Select */}
                  <div>
                    <label className="text-xs text-slate-400 mb-1.5 block">优化算法</label>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setOptAlgorithm("grid")}
                        className={`flex-1 py-2 text-xs rounded-lg border transition-all ${
                          optAlgorithm === "grid"
                            ? "bg-emerald-600/20 border-emerald-500/50 text-emerald-400 font-medium"
                            : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        Grid Search
                      </button>
                      <button
                        onClick={() => setOptAlgorithm("optuna")}
                        className={`flex-1 py-2 text-xs rounded-lg border transition-all ${
                          optAlgorithm === "optuna"
                            ? "bg-emerald-600/20 border-emerald-500/50 text-emerald-400 font-medium"
                            : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        Optuna
                      </button>
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1">
                      {optAlgorithm === "grid" ? "穷举所有参数组合，精确但耗时" : "贝叶斯优化，效率高但有随机性"}
                    </p>
                  </div>

                  {/* Target Metric */}
                  <div>
                    <label className="text-xs text-slate-400 mb-1.5 block">目标指标</label>
                    <div className="grid grid-cols-3 gap-1">
                      {[
                        { value: "sharpe", label: "Sharpe" },
                        { value: "return", label: "收益率" },
                        { value: "return_per_dd", label: "收益/回撤" },
                      ].map(m => (
                        <button
                          key={m.value}
                          onClick={() => setOptTargetMetric(m.value)}
                          className={`py-1.5 text-[10px] rounded-lg border transition-all ${
                            optTargetMetric === m.value
                              ? "bg-emerald-600/20 border-emerald-500/50 text-emerald-400 font-medium"
                              : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200"
                          }`}
                        >
                          {m.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Optuna Trials */}
                  {optAlgorithm === "optuna" && (
                    <div>
                      <div className="flex justify-between text-xs text-slate-300 mb-1">
                        <label>搜索次数</label>
                        <span className="font-mono text-emerald-400">{optNTrials}</span>
                      </div>
                      <input
                        type="range"
                        min={10}
                        max={200}
                        step={10}
                        value={optNTrials}
                        onChange={e => setOptNTrials(Number(e.target.value))}
                        className="w-full accent-emerald-500"
                      />
                    </div>
                  )}

                  {/* Commission */}
                  <div>
                    <label className="text-xs text-slate-400 mb-1.5 block">
                      手续费率 (%)
                      <span className="ml-1 font-mono text-slate-500">{optCommission > 0 ? (optCommission * 100).toFixed(3) : "默认 0.1%"}</span>
                    </label>
                    <input
                      type="number"
                      step="0.0001"
                      min="0"
                      max="0.01"
                      value={optCommission}
                      onChange={e => setOptCommission(Math.max(0, parseFloat(e.target.value) || 0))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    />
                  </div>

                  {/* Slippage */}
                  <div>
                    <label className="text-xs text-slate-400 mb-1.5 block">
                      滑点率 (%)
                      <span className="ml-1 font-mono text-slate-500">{optSlippage > 0 ? (optSlippage * 100).toFixed(3) : "默认 0.05%"}</span>
                    </label>
                    <input
                      type="number"
                      step="0.0001"
                      min="0"
                      max="0.01"
                      value={optSlippage}
                      onChange={e => setOptSlippage(Math.max(0, parseFloat(e.target.value) || 0))}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    />
                  </div>
                </CardContent>
              </Card>

              {/* Parameter Ranges Config */}
              <Card className="bg-slate-900 border-slate-700/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                    <div className="w-6 h-6 bg-purple-500/10 rounded flex items-center justify-center border border-purple-500/20">
                      <Activity className="w-3.5 h-3.5 text-purple-400" />
                    </div>
                    参数范围配置
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {Object.keys(optParamRanges).length === 0 ? (
                    <p className="text-xs text-slate-500 text-center py-4">
                      选择策略后自动加载参数范围
                    </p>
                  ) : (
                    Object.entries(optParamRanges).map(([key, cfg]) => {
                      const tplParam = templates.find(t => t.id === selectedType)?.params.find(p => p.key === key);
                      return (
                        <div key={key} className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-slate-300 font-medium">
                              {tplParam?.label || key}
                            </span>
                            <span className="text-[10px] text-slate-500 font-mono">
                              {cfg.values.length > 0
                                ? `${cfg.values.length} 个值`
                                : `步长 ${cfg.step}`}
                            </span>
                          </div>
                          <div className="grid grid-cols-3 gap-2">
                            <div>
                              <label className="text-[10px] text-slate-500 block mb-0.5">最小</label>
                              <input
                                type="number"
                                value={cfg.min}
                                onChange={e => setOptParamRanges(prev => ({
                                  ...prev,
                                  [key]: { ...cfg, min: parseFloat(e.target.value) || 0, values: [] }
                                }))}
                                className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-[11px] text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                              />
                            </div>
                            <div>
                              <label className="text-[10px] text-slate-500 block mb-0.5">最大</label>
                              <input
                                type="number"
                                value={cfg.max}
                                onChange={e => setOptParamRanges(prev => ({
                                  ...prev,
                                  [key]: { ...cfg, max: parseFloat(e.target.value) || 0, values: [] }
                                }))}
                                className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-[11px] text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                              />
                            </div>
                            <div>
                              <label className="text-[10px] text-slate-500 block mb-0.5">步长</label>
                              <input
                                type="number"
                                step="1"
                                value={cfg.step}
                                onChange={e => setOptParamRanges(prev => ({
                                  ...prev,
                                  [key]: { ...cfg, step: Math.max(0.001, parseFloat(e.target.value) || 1), values: [] }
                                }))}
                                className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-[11px] text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                              />
                            </div>
                          </div>
                          {/* Preview values */}
                          <div className="flex flex-wrap gap-1">
                            {(cfg.values.length > 0 ? cfg.values : Array.from(
                              { length: Math.min(6, Math.ceil((cfg.max - cfg.min) / cfg.step) + 1) },
                              (_, i) => Math.round((cfg.min + i * cfg.step) * 1000) / 1000
                            )).slice(0, 8).map((v, i) => (
                              <Badge key={i} variant="outline" className="text-[9px] px-1 py-0 bg-slate-700 border-slate-600 text-slate-400">
                                {typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(2)) : v}
                              </Badge>
                            ))}
                            {cfg.values.length > 8 && (
                              <Badge variant="outline" className="text-[9px] px-1 py-0 bg-slate-700 border-slate-600 text-slate-500">
                                +{cfg.values.length - 8}
                              </Badge>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                  {/* Combo count estimate */}
                  {Object.keys(optParamRanges).length > 0 && (
                    <div className="pt-2 border-t border-slate-700/50">
                      <p className="text-[10px] text-slate-500">
                        预估组合数: ~{Object.values(optParamRanges).reduce((acc, cfg) => {
                          const count = cfg.values.length > 0
                            ? cfg.values.length
                            : Math.max(1, Math.ceil((cfg.max - cfg.min) / cfg.step) + 1);
                          return acc * count;
                        }, 1).toLocaleString()}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Run Button */}
              <Button
                onClick={handleOptRun}
                disabled={optRunning || Object.keys(optParamRanges).length === 0}
                className={`w-full gap-2 ${
                  optRunning
                    ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                    : "bg-emerald-600 hover:bg-emerald-500 text-white"
                }`}
              >
                {optRunning ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    优化中...
                  </>
                ) : (
                  <>
                    <TrendingUp className="w-4 h-4" />
                    开始参数优化
                  </>
                )}
              </Button>

              {/* Error */}
              {optError && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-xs text-red-400">
                  {optError}
                </div>
              )}
            </div>

            {/* ── Right Results Panel ── */}
            <div className="xl:col-span-3 space-y-4">
              {!optResult ? (
                <div className="flex flex-col items-center justify-center h-96 text-slate-500 border border-slate-800 rounded-2xl">
                  <TrendingUp className="w-16 h-16 mb-4 opacity-30" />
                  <p className="text-lg font-medium">等待参数优化结果</p>
                  <p className="text-sm mt-1">配置策略和参数范围后点击「开始参数优化」</p>
                  <p className="text-[10px] mt-3 text-slate-600">支持 Grid Search / Optuna 算法 · 实时防过拟合预警</p>
                </div>
              ) : (
                <>
                  {/* Warnings Banner */}
                  {optResult.warnings && optResult.warnings.length > 0 && (
                    <div className="space-y-2">
                      {optResult.warnings.map((w, i) => (
                        <div
                          key={i}
                          className={`flex items-start gap-3 p-3 rounded-xl border text-sm ${
                            w.severity === "high"
                              ? "bg-red-500/10 border-red-500/20 text-red-400"
                              : "bg-amber-500/10 border-amber-500/20 text-amber-400"
                          }`}
                        >
                          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                          <div className="flex-1">
                            <p className="font-medium text-xs">{w.message}</p>
                            <p className="text-[10px] opacity-75 mt-0.5">{w.recommendation}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Result Header */}
                  <div className="flex items-center gap-3">
                    <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-xs px-2 py-1">
                      ✓ 优化完成
                    </Badge>
                    <Badge variant="outline" className="bg-slate-800 text-slate-300 border-slate-600 text-xs">
                      {optResult.symbol} / {optResult.interval} / {optResult.algorithm === "grid" ? "Grid" : "Optuna"}
                    </Badge>
                    <Badge variant="outline" className="bg-slate-800 text-slate-300 border-slate-600 text-xs">
                      共 {optResult.total_combos.toLocaleString()} 个组合
                    </Badge>
                    <span className="text-[10px] text-slate-500 ml-auto">
                      {optResult.target_metric === "sharpe" ? "目标: Sharpe" : optResult.target_metric === "return" ? "目标: 收益率" : "目标: 收益/回撤"}
                    </span>
                  </div>

                  {/* Best Params Metrics */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <MetricCard
                      label="最优 Sharpe"
                      value={optResult.best_sharpe.toFixed(3)}
                      positive={optResult.best_sharpe >= 1}
                      sub={`收益率 ${optResult.best_return >= 0 ? "+" : ""}${optResult.best_return.toFixed(2)}%`}
                    />
                    <MetricCard
                      label="最优收益率"
                      value={`${optResult.best_return >= 0 ? "+" : ""}${optResult.best_return.toFixed(2)}%`}
                      positive={optResult.best_return >= 0}
                      sub={`Sharpe ${optResult.best_sharpe.toFixed(3)}`}
                    />
                    <MetricCard
                      label="最大回撤"
                      value={`-${optResult.best_max_drawdown.toFixed(2)}%`}
                      positive={optResult.best_max_drawdown < 15}
                      sub={`年化 ${(optResult.best_return / Math.max(0.01, optResult.best_max_drawdown)).toFixed(2)}x`}
                    />
                    <div className="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
                      <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">最优参数</p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {Object.entries(optResult.best_params).map(([k, v]) => (
                          <Badge key={k} variant="outline" className="text-[10px] px-1.5 py-0 bg-slate-700 border-slate-600 text-slate-300">
                            {k}: {typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(3)) : v}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      onClick={handleOptApplyToBacktest}
                      className="gap-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs h-8"
                    >
                      <Play className="w-3 h-3" /> 应用到回测
                    </Button>
                    <Button
                      onClick={() => { setOptSaveDialogOpen(true); setOptSelectedParams(optResult.best_params); }}
                      className="gap-1.5 bg-purple-600 hover:bg-purple-500 text-white text-xs h-8"
                    >
                      <CheckCircle2 className="w-3 h-3" /> 保存为策略模板
                    </Button>
                    <Button
                      onClick={handleOptGeneratePaperBot}
                      className="gap-1.5 bg-green-600 hover:bg-green-500 text-white text-xs h-8"
                    >
                      <Activity className="w-3 h-3" /> 生成 Paper Bot
                    </Button>
                    <Button
                      onClick={handleOptGenerateTestnetBot}
                      className="gap-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-xs h-8"
                    >
                      <Server className="w-3 h-3" /> 生成 Testnet Bot
                    </Button>
                    <Button
                      onClick={handleOptRunWFA}
                      className="gap-1.5 bg-orange-600 hover:bg-orange-500 text-white text-xs h-8"
                    >
                      <RefreshCw className="w-3 h-3" /> 进入 WFA 验证
                    </Button>
                  </div>

                  {/* Charts: Equity + Drawdown */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <Card className="bg-slate-900 border-slate-700/50 overflow-hidden">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                          <TrendingUp className="w-4 h-4 text-emerald-400" />
                          最优参数权益曲线
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="p-0">
                        <EquityCurveChart
                          data={optResult.best_equity_curve || []}
                          initialCapital={initialCapital}
                          height={280}
                        />
                      </CardContent>
                    </Card>
                    <Card className="bg-slate-900 border-slate-700/50 overflow-hidden">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                          <TrendingDown className="w-4 h-4 text-red-400" />
                          回撤曲线
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="p-0">
                        <DrawdownCurveChart
                          data={optResult.best_drawdown_curve || []}
                          height={280}
                        />
                      </CardContent>
                    </Card>
                  </div>

                  {/* Top N Leaderboard */}
                  <Card className="bg-slate-900 border-slate-700/50">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
                        <BarChart3 className="w-4 h-4 text-purple-400" />
                        参数排行榜 Top 20
                        {optSelectedRank > 0 && (
                          <Badge variant="outline" className="ml-2 text-[10px] bg-amber-500/10 border-amber-500/20 text-amber-400">
                            已选 #{optSelectedRank + 1}
                          </Badge>
                        )}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-slate-800 bg-slate-900">
                              <th className="px-3 py-2 text-left text-slate-400 font-medium">#</th>
                              <th className="px-3 py-2 text-right text-slate-400 font-medium">Sharpe</th>
                              <th className="px-3 py-2 text-right text-slate-400 font-medium">收益率</th>
                              <th className="px-3 py-2 text-right text-slate-400 font-medium">最大回撤</th>
                              <th className="px-3 py-2 text-right text-slate-400 font-medium">胜率</th>
                              <th className="px-3 py-2 text-right text-slate-400 font-medium">交易数</th>
                              <th className="px-3 py-2 text-left text-slate-400 font-medium">参数</th>
                              <th className="px-3 py-2 text-center text-slate-400 font-medium">操作</th>
                            </tr>
                          </thead>
                          <tbody>
                            {optResult.results.slice(0, 20).map((item, i) => {
                              const isSelected = optSelectedRank === i;
                              const isBest = i === 0;
                              return (
                                <tr
                                  key={i}
                                  className={`border-b border-slate-800/50 transition-colors cursor-pointer ${
                                    isSelected
                                      ? "bg-emerald-500/10"
                                      : "hover:bg-slate-800/30"
                                  } ${isBest ? "bg-yellow-500/5" : ""}`}
                                  onClick={() => handleOptSelectRank(item, i)}
                                >
                                  <td className="px-3 py-2">
                                    <span className={`font-bold font-mono ${
                                      isBest ? "text-yellow-400" : isSelected ? "text-emerald-400" : "text-slate-400"
                                    }`}>
                                      {i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : i + 1}
                                    </span>
                                  </td>
                                  <td className={`px-3 py-2 text-right font-mono font-medium ${
                                    item.sharpe >= 1 ? "text-green-400" : item.sharpe >= 0 ? "text-slate-100" : "text-red-400"
                                  }`}>
                                    {item.sharpe.toFixed(3)}
                                  </td>
                                  <td className={`px-3 py-2 text-right font-mono ${
                                    item.total_return >= 0 ? "text-green-400" : "text-red-400"
                                  }`}>
                                    {item.total_return >= 0 ? "+" : ""}{item.total_return.toFixed(2)}%
                                  </td>
                                  <td className={`px-3 py-2 text-right font-mono ${
                                    item.max_drawdown < 10 ? "text-green-400" : item.max_drawdown < 20 ? "text-amber-400" : "text-red-400"
                                  }`}>
                                    -{item.max_drawdown.toFixed(2)}%
                                  </td>
                                  <td className="px-3 py-2 text-right font-mono text-slate-300">
                                    {item.win_rate.toFixed(1)}%
                                  </td>
                                  <td className="px-3 py-2 text-right font-mono text-slate-400">
                                    {item.total_trades}
                                  </td>
                                  <td className="px-3 py-2">
                                    <div className="flex flex-wrap gap-1">
                                      {Object.entries(item.params).map(([k, v]) => (
                                        <Badge key={k} variant="outline" className="text-[9px] px-1 py-0 bg-slate-800 border-slate-700 text-slate-400 whitespace-nowrap">
                                          {k}: {typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(2)) : v}
                                        </Badge>
                                      ))}
                                    </div>
                                  </td>
                                  <td className="px-3 py-2 text-center">
                                    <div className="flex items-center justify-center gap-1">
                                      <button
                                        onClick={(e) => { e.stopPropagation(); handleOptApplyToBacktest(); setOptSelectedParams(item.params); setOptSelectedRank(i); }}
                                        className="p-1 rounded hover:bg-slate-700 text-slate-500 hover:text-blue-400 transition-colors"
                                        title="应用到回测"
                                      >
                                        <Play className="w-3 h-3" />
                                      </button>
                                      <button
                                        onClick={(e) => { e.stopPropagation(); setOptSaveDialogOpen(true); setOptSelectedParams(item.params); setOptSelectedRank(i); }}
                                        className="p-1 rounded hover:bg-slate-700 text-slate-500 hover:text-purple-400 transition-colors"
                                        title="保存为模板"
                                      >
                                        <CheckCircle2 className="w-3 h-3" />
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Heatmap Section */}
                  {optResult.results.length > 1 && (
                    <HeatmapSection results={optResult.results} paramRanges={optParamRanges} />
                  )}

                  {/* Stability Score */}
                  {optResult.results.length >= 5 && (
                    <ParamStabilityScoreCard results={optResult.results} />
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Delete Confirmation Dialog */}
      {deleteTarget && (
        <DeleteConfirmDialog
          record={deleteTarget}
          onConfirm={() => handleDeleteRecord(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {/* Launch Paper Bot Dialog */}
      {launchDialogOpen && launchTarget && (
        <LaunchPaperBotDialog
          result={launchTarget}
          onConfirm={handleLaunchConfirm}
          onCancel={() => setLaunchDialogOpen(false)}
        />
      )}

      {/* Save Template Dialog */}
      {optSaveDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-purple-500/10 rounded-full flex items-center justify-center">
                <CheckCircle2 className="w-5 h-5 text-purple-400" />
              </div>
              <h3 className="text-lg font-bold text-slate-100">保存为策略模板</h3>
            </div>
            <p className="text-sm text-slate-400 mb-4">
              将以下参数保存为 <span className="text-slate-200 font-medium">{optResult?.strategy_type}</span> 的新默认参数：
            </p>
            <div className="bg-slate-800/50 rounded-xl p-3 mb-4 border border-slate-700/50">
              <div className="flex flex-wrap gap-2">
                {Object.entries(optSelectedParams || optResult?.best_params || {}).map(([k, v]) => (
                  <Badge key={k} variant="outline" className="text-xs bg-slate-700 border-slate-600 text-slate-200">
                    {k}: {typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(3)) : v}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="flex gap-3">
              <Button
                onClick={() => setOptSaveDialogOpen(false)}
                className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300"
              >
                取消
              </Button>
              <Button
                onClick={handleOptSaveTemplate}
                className="flex-1 bg-purple-600 hover:bg-purple-500 text-white"
              >
                确认保存
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── DrawdownCurveChart ───────────────────────────────────────────────────────
interface DrawdownCurveChartProps {
  data: { t: string; v: number }[];
  height?: number;
}

function DrawdownCurveChart({ data, height = 280 }: DrawdownCurveChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const seriesRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "transparent" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      rightPriceScale: {
        borderColor: "#334155",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: "#334155",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScale: false,
      handleScroll: false,
    });

    const lineSeries = chart.addSeries(LineSeries, {
      color: "#ef4444",
      lineWidth: 2,
      title: "回撤",
    });

    chartRef.current = chart;
    seriesRef.current = lineSeries;

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);
    handleResize();

    return () => {
      window.removeEventListener("resize", handleResize);
      try {
        if (chartRef.current && containerRef.current && document.body.contains(containerRef.current)) {
          chartRef.current.remove();
        }
      } catch {}
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !data || data.length === 0) return;
    const points = data
      .map(d => ({ time: (new Date(d.t).getTime() / 1000) as Time, value: Math.abs(d.v) }))
      .filter((p, i, arr) => i === 0 || arr[i - 1].time !== p.time)
      .sort((a, b) => a.time - b.time);
    seriesRef.current.setData(points);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  const maxDD = data.length > 0 ? Math.max(...data.map(d => Math.abs(d.v))) : 0;

  return (
    <div className="relative overflow-hidden">
      <div ref={containerRef} className="w-full" style={{ height: `${height}px` }} />
      <div className="absolute top-2 left-3 text-[10px] text-slate-400">最大回撤: <span className="text-red-400 font-mono">-{maxDD.toFixed(2)}%</span></div>
    </div>
  );
}

// ─── HeatmapSection ──────────────────────────────────────────────────────────
interface HeatmapSectionProps {
  results: OptimizeResultItem[];
  paramRanges: Record<string, { min: number; max: number; step: number; values: number[] }>;
}

function HeatmapSection({ results, paramRanges }: HeatmapSectionProps) {
  const paramKeys = Object.keys(paramRanges);
  if (paramKeys.length < 2 || paramKeys.length > 3 || results.length < 4) {
    return null;
  }

  const primaryKey = paramKeys[0];
  const secondaryKey = paramKeys[1];
  const primaryVals = [...new Set(results.map(r => r.params[primaryKey]))].sort((a, b) => a - b);
  const secondaryVals = [...new Set(results.map(r => r.params[secondaryKey]))].sort((a, b) => a - b);

  // Build heatmap matrix (metric: sharpe, return, or max_drawdown)
  const metricOptions = [
    { key: "sharpe", label: "Sharpe", format: (v: number) => v.toFixed(2), higherBetter: true },
    { key: "return", label: "收益率", format: (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`, higherBetter: true },
    { key: "max_drawdown", label: "最大回撤", format: (v: number) => `-${v.toFixed(1)}%`, higherBetter: false },
  ];
  const [selectedMetric, setSelectedMetric] = useState("sharpe");

  const getCellValue = (pv: number, sv: number): number | null => {
    const r = results.find(r => r.params[primaryKey] === pv && r.params[secondaryKey] === sv);
    return r ? (r as any)[selectedMetric] : null;
  };

  const allValues = results.map(r => (r as any)[selectedMetric] as number);
  const minVal = Math.min(...allValues);
  const maxVal = Math.max(...allValues);
  const metricCfg = metricOptions.find(m => m.key === selectedMetric)!;

  const getColor = (val: number): string => {
    const norm = maxVal === minVal ? 0.5 : (val - minVal) / (maxVal - minVal);
    if (metricCfg.higherBetter) {
      if (norm < 0.33) return "bg-red-900/60";
      if (norm < 0.66) return "bg-yellow-900/60";
      return "bg-green-900/60";
    } else {
      if (norm < 0.33) return "bg-green-900/60";
      if (norm < 0.66) return "bg-yellow-900/60";
      return "bg-red-900/60";
    }
  };

  return (
    <Card className="bg-slate-900 border-slate-700/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-purple-400" />
          参数热力图
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Metric Selector */}
        <div className="flex gap-2 mb-4">
          {metricOptions.map(m => (
            <button
              key={m.key}
              onClick={() => setSelectedMetric(m.key)}
              className={`px-3 py-1.5 text-xs rounded-lg border transition-all ${
                selectedMetric === m.key
                  ? "bg-emerald-600/20 border-emerald-500/50 text-emerald-400 font-medium"
                  : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="border-collapse">
            <thead>
              <tr>
                <th className="p-1 text-[10px] text-slate-500 font-normal"></th>
                {secondaryVals.map(sv => (
                  <th key={sv} className="p-1 text-[10px] text-slate-400 font-normal text-center min-w-[60px]">
                    {sv}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {primaryVals.map(pv => (
                <tr key={pv}>
                  <td className="p-1 text-[10px] text-slate-400 font-normal text-right pr-2">{pv}</td>
                  {secondaryVals.map(sv => {
                    const val = getCellValue(pv, sv);
                    const hasData = val !== null;
                    return (
                      <td key={sv} className="p-0.5">
                        <div
                          className={`rounded text-center text-[10px] font-mono px-2 py-1 min-w-[60px] ${
                            hasData ? getColor(val) + " text-slate-200" : "bg-slate-800 text-slate-600"
                          }`}
                          title={hasData ? `${metricCfg.label}: ${metricCfg.format(val)}` : "无数据"}
                        >
                          {hasData ? metricCfg.format(val) : "—"}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Color legend */}
        <div className="flex items-center gap-2 mt-3 text-[10px] text-slate-500">
          <span>{metricCfg.higherBetter ? "低" : "高"}</span>
          <div className="flex gap-0.5">
            <div className="w-6 h-3 rounded bg-red-900/60" />
            <div className="w-6 h-3 rounded bg-yellow-900/60" />
            <div className="w-6 h-3 rounded bg-green-900/60" />
          </div>
          <span>{metricCfg.higherBetter ? "高" : "低"}</span>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── ParamStabilityScoreCard ─────────────────────────────────────────────────
interface ParamStabilityScoreCardProps {
  results: OptimizeResultItem[];
}

function ParamStabilityScoreCard({ results }: ParamStabilityScoreCardProps) {
  if (results.length < 5) return null;

  const metric = "sharpe";
  const values = results.map(r => r[metric]);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length;
  const std = Math.sqrt(variance);
  const cv = std / Math.abs(mean) || 0; // coefficient of variation

  const sharpeValues = values;
  const sorted = [...sharpeValues].sort((a, b) => a - b);
  const q1 = sorted[Math.floor(sorted.length * 0.25)];
  const q3 = sorted[Math.floor(sorted.length * 0.75)];
  const iqr = q3 - q1;

  // Stability score: lower CV = more stable, capped 0-100
  const stabilityScore = Math.max(0, Math.min(100, Math.round((1 - Math.min(cv, 2)) * 100)));
  const scoreColor = stabilityScore >= 70 ? "text-green-400" : stabilityScore >= 40 ? "text-amber-400" : "text-red-400";
  const scoreBg = stabilityScore >= 70 ? "bg-green-500/10 border-green-500/20" : stabilityScore >= 40 ? "bg-amber-500/10 border-amber-500/20" : "bg-red-500/10 border-red-500/20";

  return (
    <Card className="bg-slate-900 border-slate-700/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
          <Activity className="w-4 h-4 text-purple-400" />
          参数稳定性评估
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className={`p-4 rounded-xl border text-center ${scoreBg}`}>
            <p className="text-xs text-slate-400 mb-1">稳定性评分</p>
            <p className={`text-3xl font-bold font-mono ${scoreColor}`}>{stabilityScore}</p>
            <p className="text-[10px] text-slate-500 mt-1">/ 100</p>
          </div>
          <div className="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <p className="text-xs text-slate-400 mb-1">Sharpe 标准差</p>
            <p className="text-xl font-bold font-mono text-slate-200">{std.toFixed(3)}</p>
            <p className="text-[10px] text-slate-500 mt-1">离散程度</p>
          </div>
          <div className="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <p className="text-xs text-slate-400 mb-1">变异系数 (CV)</p>
            <p className={`text-xl font-bold font-mono ${cv < 0.3 ? "text-green-400" : cv < 0.6 ? "text-amber-400" : "text-red-400"}`}>
              {cv.toFixed(3)}
            </p>
            <p className="text-[10px] text-slate-500 mt-1">CV 越低越稳定</p>
          </div>
          <div className="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <p className="text-xs text-slate-400 mb-1">IQR</p>
            <p className="text-xl font-bold font-mono text-slate-200">{iqr.toFixed(3)}</p>
            <p className="text-[10px] text-slate-500 mt-1">四分位距</p>
          </div>
        </div>
        <p className="text-xs text-slate-500 mt-3">
          {stabilityScore >= 70
            ? "✓ 参数稳定性良好，不同参数组合的收益表现较为一致，过拟合风险较低"
            : stabilityScore >= 40
            ? "⚠ 参数稳定性一般，建议关注排名靠前且稳定的参数组合"
            : "✗ 参数稳定性差，最优参数可能存在过拟合，建议通过 WFA 验证"}
        </p>
      </CardContent>
    </Card>
  );
}
