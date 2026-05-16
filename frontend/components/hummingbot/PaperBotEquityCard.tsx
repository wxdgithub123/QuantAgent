"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EquityCurveChart } from "@/components/charts/EquityCurveChart";
import { RefreshCw, TrendingUp, TrendingDown, DollarSign, BarChart3, AlertTriangle } from "lucide-react";

interface EquityCurveData {
  timestamp: string;
  total_equity: number;
  cash_balance: number;
  position_value: number;
  pnl: number;
  pnl_pct: number;
  drawdown: number;
}

interface EquityStatistics {
  total_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  total_trades: number;
}

interface PaperBotEquityCardProps {
  paperBotId: string;
  initialBalance?: number;
  height?: number;
}

type DataInterval = "1h" | "4h" | "1d";

function SkeletonCard() {
  return (
    <div className="animate-pulse space-y-3 px-4 pb-2">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-14 bg-slate-800/50 rounded-lg border border-slate-700/50" />
        ))}
      </div>
      <div className="h-[200px] bg-slate-800/50 rounded-lg border border-slate-700/50" />
    </div>
  );
}

function EmptyState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <BarChart3 className="w-10 h-10 text-slate-600 mb-3" />
      <p className="text-slate-400 text-sm font-medium mb-1">暂无权益数据</p>
      <p className="text-slate-600 text-xs mb-4 text-center">
        Bot 启动后数据将在此展示
      </p>
      <Button variant="outline" size="sm" onClick={onRetry} className="text-xs h-7">
        <RefreshCw className="w-3 h-3 mr-1" />
        刷新
      </Button>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center mb-3">
        <AlertTriangle className="w-5 h-5 text-red-400" />
      </div>
      <p className="text-red-400 text-sm font-medium mb-1">加载失败</p>
      <p className="text-slate-500 text-xs mb-4 text-center max-w-xs">{message}</p>
      <Button variant="outline" size="sm" onClick={onRetry} className="text-xs h-7">
        <RefreshCw className="w-3 h-3 mr-1" />
        重试
      </Button>
    </div>
  );
}

export function PaperBotEquityCard({
  paperBotId,
  initialBalance = 10000,
  height = 260,
}: PaperBotEquityCardProps) {
  const [equityCurve, setEquityCurve] = useState<EquityCurveData[]>([]);
  const [statistics, setStatistics] = useState<EquityStatistics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interval, setInterval] = useState<DataInterval>("1h");

  const fetchEquityCurve = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/hummingbot/paper-bots/${paperBotId}/equity-curve?interval=${interval}`,
        { signal: AbortSignal.timeout(10000) }
      );
      if (res.ok) {
        const json = await res.json();
        setEquityCurve(json.data || []);
        setStatistics(json.statistics || null);
      } else {
        setError(`请求失败 (${res.status})`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "网络错误");
    } finally {
      setLoading(false);
    }
  }, [paperBotId, interval]);

  useEffect(() => {
    fetchEquityCurve();
  }, [fetchEquityCurve]);

  // Convert to chart format
  const chartData = equityCurve.map(d => ({
    t: d.timestamp,
    v: d.total_equity,
  }));

  const isPositive = statistics ? (statistics.total_return_pct ?? 0) >= 0 : true;

  if (loading && equityCurve.length === 0) return (
    <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-indigo-400" />
            权益曲线
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="p-0 pb-2 px-4">
        <SkeletonCard />
      </CardContent>
    </Card>
  );

  if (error && equityCurve.length === 0) return (
    <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-indigo-400" />
            权益曲线
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="p-0 pb-2 px-4">
        <ErrorState message={error} onRetry={fetchEquityCurve} />
      </CardContent>
    </Card>
  );

  if (!loading && equityCurve.length === 0) return (
    <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-indigo-400" />
            权益曲线
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="p-0 pb-2 px-4">
        <EmptyState onRetry={fetchEquityCurve} />
      </CardContent>
    </Card>
  );

  return (
    <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-slate-100 text-sm flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-indigo-400" />
            权益曲线
          </CardTitle>
          <div className="flex items-center gap-2">
            {/* Interval selector */}
            <div className="flex gap-1">
              {(["1h", "4h", "1d"] as const).map(intv => (
                <button
                  key={intv}
                  onClick={() => setInterval(intv)}
                  className={`px-2 py-0.5 text-[10px] rounded border transition-colors ${
                    interval === intv
                      ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/30"
                      : "bg-slate-800 text-slate-400 border-slate-700/50 hover:bg-slate-700"
                  }`}
                >
                  {intv === "1h" ? "1小时" : intv === "4h" ? "4小时" : "1天"}
                </button>
              ))}
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={fetchEquityCurve}
              disabled={loading}
            >
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0 pb-2 px-4">
        {/* Stats row */}
        {statistics && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3">
            <div className="p-2 bg-slate-800/50 rounded-lg border border-slate-700/50">
              <p className="text-[10px] text-slate-500">总收益率</p>
              <p className={`text-sm font-bold font-mono ${isPositive ? "text-green-400" : "text-red-400"}`}>
                {isPositive ? "+" : ""}{statistics.total_return_pct.toFixed(2)}%
              </p>
            </div>
            <div className="p-2 bg-slate-800/50 rounded-lg border border-slate-700/50">
              <p className="text-[10px] text-slate-500">夏普比率</p>
              <p className={`text-sm font-bold font-mono ${statistics.sharpe_ratio >= 1 ? "text-green-400" : statistics.sharpe_ratio >= 0 ? "text-amber-400" : "text-red-400"}`}>
                {statistics.sharpe_ratio.toFixed(2)}
              </p>
            </div>
            <div className="p-2 bg-slate-800/50 rounded-lg border border-slate-700/50">
              <p className="text-[10px] text-slate-500">最大回撤</p>
              <p className="text-sm font-bold font-mono text-red-400">
                -{statistics.max_drawdown_pct.toFixed(2)}%
              </p>
            </div>
            <div className="p-2 bg-slate-800/50 rounded-lg border border-slate-700/50">
              <p className="text-[10px] text-slate-500">胜率</p>
              <p className={`text-sm font-bold font-mono ${statistics.win_rate_pct >= 50 ? "text-green-400" : "text-red-400"}`}>
                {statistics.win_rate_pct.toFixed(1)}%
              </p>
            </div>
            <div className="p-2 bg-slate-800/50 rounded-lg border border-slate-700/50">
              <p className="text-[10px] text-slate-500">累计交易</p>
              <p className="text-sm font-bold font-mono text-slate-300">
                {statistics.total_trades}
              </p>
            </div>
          </div>
        )}

        {/* Chart */}
        <EquityCurveChart
          data={chartData}
          baselineData={[]}
          markers={[]}
          initialCapital={initialBalance}
          height={height}
          showLegend={true}
        />
      </CardContent>
    </Card>
  );
}
