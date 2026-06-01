"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle2,
  Database,
  Layers,
  RefreshCw,
  Wifi,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type JsonRecord = Record<string, unknown>;

interface BackfillRow {
  symbol?: string;
  interval?: string;
  status?: string;
  row_count?: number;
  expected_min_rows?: number;
}

interface StatusState {
  health: unknown;
  backfillRows: BackfillRow[];
  checkedAt: string | null;
  error: string;
}

interface CheckItem {
  label: string;
  ok: boolean;
  detail: string;
  note: string;
  icon: typeof Wifi;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null;
}

function readPath(source: unknown, path: string[]) {
  return path.reduce<unknown>((value, key) => (isRecord(value) ? value[key] : undefined), source);
}

function readString(source: unknown, path: string[]) {
  const value = readPath(source, path);
  return typeof value === "string" ? value : undefined;
}

function readNumber(source: unknown, path: string[]) {
  const value = readPath(source, path);
  return typeof value === "number" ? value : undefined;
}

function readBoolean(source: unknown, path: string[]) {
  const value = readPath(source, path);
  return typeof value === "boolean" ? value : undefined;
}

function toBackfillRows(value: unknown): BackfillRow[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((row) => ({
    symbol: typeof row.symbol === "string" ? row.symbol : undefined,
    interval: typeof row.interval === "string" ? row.interval : undefined,
    status: typeof row.status === "string" ? row.status : undefined,
    row_count: typeof row.row_count === "number" ? row.row_count : undefined,
    expected_min_rows: typeof row.expected_min_rows === "number" ? row.expected_min_rows : undefined,
  }));
}

function shortBaseUrl(value?: string) {
  if (!value) return "未配置";
  try {
    return new URL(value).host;
  } catch {
    return value.replace(/^https?:\/\//, "");
  }
}

function buildChecks(state: StatusState): CheckItem[] {
  const health = state.health;
  const failedBackfills = state.backfillRows.filter((row) => row.status !== "ok");
  const openbbDetail = readString(health, ["layers", "L1_data_source", "openbb", "detail"]);
  const openbbProvider = readString(health, ["layers", "L1_data_source", "openbb", "provider"]);
  const ccxtExchanges = readPath(health, ["layers", "L1_data_source", "ccxt", "exchanges"]);
  const l5FactorCount = readNumber(health, ["layers", "L5_factors_signals", "counts", "factor_snapshots"]) ?? 0;
  const l5SignalCount = readNumber(health, ["layers", "L5_factors_signals", "counts", "signal_events"]) ?? 0;
  const l5Latest = readString(health, ["layers", "L5_factors_signals", "counts", "latest_signal_timestamp"]);
  const tradingEnabled = readBoolean(health, ["layers", "L6_decision", "tradingagents_service", "enabled"]);
  const llmProvider = readString(health, ["layers", "L6_decision", "tradingagents_service", "detail", "detail", "llm_provider"]);
  const llmModel = readString(health, ["layers", "L6_decision", "tradingagents_service", "detail", "detail", "openai_model"]);
  const llmBaseUrl = readString(health, ["layers", "L6_decision", "tradingagents_service", "detail", "detail", "openai_base_url"]);
  const openaiConfigured = readBoolean(health, ["layers", "L6_decision", "tradingagents_service", "detail", "detail", "openai_configured"]);
  const exchangeCount = Array.isArray(ccxtExchanges) ? ccxtExchanges.length : 0;

  return [
    {
      label: "数据入口 OpenBB",
      ok: readString(health, ["layers", "L1_data_source", "openbb", "status"]) === "ok",
      detail: openbbDetail || `默认 provider: ${openbbProvider || "未识别"}`,
      note: "统一数据入口已加载；加密行情当前仍会优先看缓存和可用 provider。",
      icon: Wifi,
    },
    {
      label: "交易所接口 CCXT",
      ok: readString(health, ["layers", "L1_data_source", "ccxt", "status"]) === "ok",
      detail: exchangeCount ? `已加载 ${exchangeCount} 个交易所连接器` : "连接器注册状态未知",
      note: "这是连接器可用，不等于所有交易所都已经实测连通。",
      icon: Activity,
    },
    {
      label: "宏观数据 FRED",
      ok: readString(health, ["layers", "L1_data_source", "fred", "status"]) === "ok",
      detail: readString(health, ["layers", "L1_data_source", "fred", "detail"]) || "通过 OpenBB 获取宏观数据",
      note: "作为加密决策的宏观背景，不是 K 线行情来源。",
      icon: Database,
    },
    {
      label: "行情缓存状态",
      ok: state.backfillRows.length > 0 && failedBackfills.length === 0,
      detail: state.backfillRows.length === 0
        ? "等待补数检查"
        : failedBackfills.length === 0
        ? `${state.backfillRows.length} 个标的/周期正常`
        : `${failedBackfills.length} 个标的/周期缺失或过期`,
      note: "检查系统里是否有足够的历史 K 线可用于分析。",
      icon: Activity,
    },
    {
      label: "因子与策略信号",
      ok: readString(health, ["layers", "L5_factors_signals", "pipeline", "status"]) === "ok"
        && readString(health, ["layers", "L5_factors_signals", "counts", "status"]) === "ok",
      detail: `${l5FactorCount.toLocaleString()} 个技术因子 / ${l5SignalCount.toLocaleString()} 条策略信号`,
      note: l5Latest ? `最新信号时间: ${new Date(l5Latest).toLocaleString()}` : "系统会用这些材料生成交易建议。",
      icon: Layers,
    },
    {
      label: "智能决策模型",
      ok: readString(health, ["layers", "L6_decision", "tradingagents_service", "status"]) === "ok",
      detail: tradingEnabled
        ? `TradingAgents 已启用 · ${llmProvider || "LLM"} · ${llmModel || "模型未识别"}`
        : "TradingAgents 可用但未设为默认",
      note: openaiConfigured
        ? `模型通道: ${shortBaseUrl(llmBaseUrl)}`
        : "尚未配置可用的大模型 API Key。",
      icon: Brain,
    },
  ];
}

export function Prd104StatusPanel({ className }: { className?: string }) {
  const [state, setState] = useState<StatusState>({
    health: null,
    backfillRows: [],
    checkedAt: null,
    error: "",
  });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [healthRes, backfillRes] = await Promise.all([
        fetch("/api/v1/system/health", { cache: "no-store" }),
        fetch("/api/v1/market/backfill/status", { cache: "no-store" }),
      ]);
      if (!healthRes.ok) throw new Error(`health ${healthRes.status}`);
      if (!backfillRes.ok) throw new Error(`backfill ${backfillRes.status}`);
      const [health, backfill] = await Promise.all([
        healthRes.json() as Promise<unknown>,
        backfillRes.json() as Promise<unknown>,
      ]);
      setState({
        health,
        backfillRows: toBackfillRows(readPath(backfill, ["intervals"])),
        checkedAt: readString(backfill, ["checked_at"]) || new Date().toISOString(),
        error: "",
      });
    } catch (error) {
      setState((current) => ({
        ...current,
        checkedAt: new Date().toISOString(),
        error: error instanceof Error ? error.message : String(error),
      }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const checks = buildChecks(state);
  const checked = state.checkedAt !== null || Boolean(state.error);
  const allOk = checked && checks.every((check) => check.ok);
  const badgeLabel = !checked && loading ? "检查中" : allOk ? "运行正常" : "有提醒";

  return (
    <Card
      data-testid="prd104-status-panel"
      className={cn(
        "overflow-hidden rounded-[26px] border-cyan-400/20 bg-[radial-gradient(circle_at_top_right,rgba(16,185,129,0.16),transparent_32%),linear-gradient(135deg,rgba(8,47,73,0.75),rgba(15,23,42,0.92))] shadow-xl shadow-cyan-950/20",
        className
      )}
    >
      <CardContent className="p-5">
        <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              {!checked && loading ? (
                <RefreshCw className="h-4 w-4 animate-spin text-cyan-300" />
              ) : allOk ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-300" />
              ) : (
                <AlertTriangle className="h-4 w-4 text-amber-300" />
              )}
              <h2 className="text-base font-semibold text-white">数据与服务状态</h2>
              <Badge
                className={cn(
                  "border text-[11px]",
                  !checked && loading
                    ? "border-cyan-300/30 bg-cyan-400/10 text-cyan-200"
                    : allOk
                    ? "border-emerald-300/30 bg-emerald-400/10 text-emerald-200"
                    : "border-amber-300/30 bg-amber-400/10 text-amber-200"
                )}
              >
                {badgeLabel}
              </Badge>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">
              这里展示系统生成交易建议前会用到的数据和服务状态：
              行情、交易所接口、宏观数据、因子信号和智能决策模型。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-slate-400">
              {state.checkedAt ? `检查时间 ${new Date(state.checkedAt).toLocaleTimeString()}` : "尚未检查"}
            </span>
            <Button size="sm" variant="outline" className="h-8 border-white/10 text-xs text-slate-100" onClick={refresh} disabled={loading}>
              <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", loading && "animate-spin")} />
              刷新
            </Button>
          </div>
        </div>

        {state.error && (
          <div className="mb-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            状态检查失败：{state.error}
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {checks.map((check) => {
            const Icon = check.icon;
            return (
              <div
                key={check.label}
                className={cn(
                  "rounded-2xl border bg-slate-950/35 p-4",
                  check.ok ? "border-emerald-400/20" : "border-amber-400/30"
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Icon className={cn("h-4 w-4", check.ok ? "text-emerald-300" : "text-amber-300")} />
                    <span className="text-sm font-semibold text-white">{check.label}</span>
                  </div>
                  <span className={cn("mt-1 h-2.5 w-2.5 rounded-full", check.ok ? "bg-emerald-300" : "bg-amber-300")} />
                </div>
                <p className="mt-3 text-sm leading-5 text-slate-200">{check.detail}</p>
                <p className="mt-2 text-[11px] leading-5 text-slate-500">{check.note}</p>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
