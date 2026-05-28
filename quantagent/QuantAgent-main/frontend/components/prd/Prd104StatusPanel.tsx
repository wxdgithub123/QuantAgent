"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, AlertTriangle, Brain, CheckCircle2, Database, Layers, RefreshCw, Wifi } from "lucide-react";

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

function buildChecks(state: StatusState): CheckItem[] {
  const health = state.health;
  const failedBackfills = state.backfillRows.filter((row) => row.status !== "ok");
  const openbbDetail = readString(health, ["layers", "L1_data_source", "openbb", "detail"]);
  const openbbProvider = readString(health, ["layers", "L1_data_source", "openbb", "provider"]);
  const l5FactorCount = readNumber(health, ["layers", "L5_factors_signals", "counts", "factor_snapshots"]) ?? 0;
  const l5SignalCount = readNumber(health, ["layers", "L5_factors_signals", "counts", "signal_events"]) ?? 0;

  return [
    {
      label: "OpenBB",
      ok: readString(health, ["layers", "L1_data_source", "openbb", "status"]) === "ok",
      detail: openbbDetail || openbbProvider || "Unified data entry",
      icon: Wifi,
    },
    {
      label: "FRED",
      ok: readString(health, ["layers", "L1_data_source", "fred", "status"]) === "ok",
      detail: readString(health, ["layers", "L1_data_source", "fred", "detail"]) || "Macro data via OpenBB",
      icon: Database,
    },
    {
      label: "Backfill",
      ok: state.backfillRows.length > 0 && failedBackfills.length === 0,
      detail: state.backfillRows.length === 0
        ? "Waiting for backfill status"
        : failedBackfills.length === 0
        ? `${state.backfillRows.length} symbol/interval checks ok`
        : `${failedBackfills.length} stale or missing`,
      icon: Activity,
    },
    {
      label: "L5 Signals",
      ok: readString(health, ["layers", "L5_factors_signals", "pipeline", "status"]) === "ok"
        && readString(health, ["layers", "L5_factors_signals", "counts", "status"]) === "ok",
      detail: `${l5FactorCount} factors / ${l5SignalCount} signals`,
      icon: Layers,
    },
    {
      label: "TradingAgents",
      ok: readString(health, ["layers", "L6_decision", "tradingagents_service", "status"]) === "ok",
      detail: readBoolean(health, ["layers", "L6_decision", "tradingagents_service", "enabled"])
        ? "Enabled by default"
        : "Ready, opt-in route",
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
  const badgeLabel = !checked && loading ? "CHECKING" : allOk ? "READY" : "CHECK";

  return (
    <Card
      data-testid="prd104-status-panel"
      className={cn("overflow-hidden border-cyan-500/20 bg-gradient-to-r from-cyan-500/10 via-card to-emerald-500/10", className)}
    >
      <CardContent className="p-4">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              {!checked && loading ? (
                <RefreshCw className="h-4 w-4 animate-spin text-cyan-400" />
              ) : allOk ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              ) : (
                <AlertTriangle className="h-4 w-4 text-amber-400" />
              )}
              <h2 className="text-sm font-semibold text-foreground">PRD 10.4 Status</h2>
              <Badge
                className={cn(
                  "text-[10px]",
                  !checked && loading
                    ? "bg-cyan-500/15 text-cyan-300"
                    : allOk
                    ? "bg-emerald-500/15 text-emerald-300"
                    : "bg-amber-500/15 text-amber-300"
                )}
              >
                {badgeLabel}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              OpenBB/FRED data entry, market backfill, L5 signals, and isolated TradingAgents route.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground">
              {state.checkedAt ? `Checked ${new Date(state.checkedAt).toLocaleTimeString()}` : "Not checked"}
            </span>
            <Button size="sm" variant="outline" className="h-8 border-border text-xs" onClick={refresh} disabled={loading}>
              <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", loading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>

        {state.error && (
          <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            Status check failed: {state.error}
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-5">
          {checks.map((check) => {
            const Icon = check.icon;
            return (
              <div
                key={check.label}
                className={cn(
                  "rounded-xl border bg-background/55 p-3",
                  check.ok ? "border-emerald-500/20" : "border-amber-500/25"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Icon className={cn("h-4 w-4", check.ok ? "text-emerald-400" : "text-amber-400")} />
                    <span className="text-xs font-semibold text-foreground">{check.label}</span>
                  </div>
                  <span className={cn("h-2 w-2 rounded-full", check.ok ? "bg-emerald-400" : "bg-amber-400")} />
                </div>
                <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">{check.detail}</p>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
