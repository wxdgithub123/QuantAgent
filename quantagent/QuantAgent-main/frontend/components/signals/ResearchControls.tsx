"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { Search, X, RefreshCw } from "lucide-react";

// ─── Props ───────────────────────────────────────────────────────────────────

export interface ResearchControlsProps {
  symbol: string;
  interval: string;
  asOfTime: string;
  appliedAsOf: string;
  replayMode: boolean;
  timeSuggestions?: string[];
  onSymbolChange: (v: string) => void;
  onIntervalChange: (v: string) => void;
  onAsOfTimeChange: (v: string) => void;
  onApply: () => void;
  onClear: () => void;
  onReplayModeChange: (v: boolean) => void;
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"];
const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"];

// ─── Component ───────────────────────────────────────────────────────────────

export function ResearchControls({
  symbol,
  interval,
  asOfTime,
  appliedAsOf,
  replayMode,
  timeSuggestions = [],
  onSymbolChange,
  onIntervalChange,
  onAsOfTimeChange,
  onApply,
  onClear,
  onReplayModeChange,
}: ResearchControlsProps) {
  const [isApplying, setIsApplying] = useState(false);

  const handleApply = () => {
    setIsApplying(true);
    onApply();
    setTimeout(() => setIsApplying(false), 500);
  };

  return (
    <Card className="border-blue-500/20 bg-gradient-to-r from-blue-500/5 to-purple-500/5">
      <CardContent className="p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          {/* Left: description */}
          <div className="shrink-0">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <Badge className="border border-blue-400/25 bg-blue-400/15 text-blue-100 text-[10px]">
                研究条件
              </Badge>
              {appliedAsOf && (
                <Badge variant="outline" className="border-amber-500/40 text-amber-300 text-[10px]">
                  历史回看: {new Date(appliedAsOf).toLocaleString("zh-CN")}
                </Badge>
              )}
              {!appliedAsOf && (
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-300 text-[10px]">
                  当前最新状态
                </Badge>
              )}
              {replayMode && (
                <Badge className="border-purple-500/40 bg-purple-500/15 text-purple-300 text-[10px]">
                  回放模式 🔄
                </Badge>
              )}
            </div>
            <h3 className="text-sm font-semibold text-foreground">选择研究对象</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              留空回看时间表示最新数据；填写时间表示按历史时点回看。
            </p>
          </div>

          {/* Right: controls */}
          <div className="flex flex-wrap items-end gap-3">
            {/* Symbol */}
            <div>
              <label className="mb-1 block text-[11px] text-muted-foreground">交易对</label>
              <Select value={symbol} onValueChange={onSymbolChange}>
                <SelectTrigger className="h-9 w-[130px] border-border bg-secondary text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  {SYMBOLS.map((s) => (
                    <SelectItem key={s} value={s} className="text-xs">{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Interval */}
            <div>
              <label className="mb-1 block text-[11px] text-muted-foreground">周期</label>
              <Select value={interval} onValueChange={onIntervalChange}>
                <SelectTrigger className="h-9 w-[90px] border-border bg-secondary text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  {INTERVALS.map((iv) => (
                    <SelectItem key={iv} value={iv} className="text-xs">{iv}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Replay Mode Toggle */}
            <div>
              <label className="mb-1 block text-[11px] text-muted-foreground">回放模式</label>
              <Button
                variant="outline"
                size="sm"
                onClick={() => onReplayModeChange(!replayMode)}
                className={cn(
                  "h-9 text-xs border-border transition-colors",
                  replayMode
                    ? "bg-purple-500/15 text-purple-400 border-purple-500/30 hover:bg-purple-500/20"
                    : "bg-secondary text-muted-foreground hover:text-foreground"
                )}
              >
                <RefreshCw className={cn("w-3.5 h-3.5 mr-1.5", replayMode && "animate-spin-slow")} />
                {replayMode ? "回放中" : "已关闭"}
              </Button>
            </div>

            {/* As-of-time */}
            <div>
              <label className="mb-1 block text-[11px] text-muted-foreground">回看时间（可选）</label>
              <div className="flex gap-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
                  <input
                    type="text"
                    value={asOfTime}
                    onChange={(e) => onAsOfTimeChange(e.target.value)}
                    placeholder="2026-05-28 09:30"
                    list="asOfTimeSuggestions"
                    className="h-9 w-[180px] pl-8 pr-3 rounded-lg border border-border bg-secondary text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-blue-500/50"
                  />
                  {timeSuggestions.length > 0 && (
                    <datalist id="asOfTimeSuggestions">
                      {timeSuggestions.map((t) => (
                        <option key={t} value={t} />
                      ))}
                    </datalist>
                  )}
                </div>
                <Button
                  size="sm"
                  onClick={handleApply}
                  disabled={isApplying}
                  className={cn(
                    "h-9 border-blue-400/30 bg-blue-500/15 text-blue-300 hover:bg-blue-500/20 text-xs",
                    isApplying && "opacity-50"
                  )}
                >
                  {isApplying ? "应用中..." : "查看快照"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 text-muted-foreground hover:text-foreground text-xs"
                  onClick={onClear}
                >
                  <X className="w-3.5 h-3.5 mr-1" />
                  清除
                </Button>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
