"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Database, GitBranch, Layers, RefreshCw, Workflow } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type JsonRecord = Record<string, unknown>;

interface PrdStage {
  id: string;
  label: string;
  status: string;
  detail: string;
}

interface PrdFlowState {
  overallStatus: string;
  stages: PrdStage[];
  counts: Record<string, number>;
  checkedAt: string | null;
  error: string;
}

const stageIcons = [Database, GitBranch, Layers, Workflow, Activity, CheckCircle2];

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null;
}

function readPath(source: unknown, path: string[]) {
  return path.reduce<unknown>((value, key) => (isRecord(value) ? value[key] : undefined), source);
}

function readString(source: unknown, path: string[], fallback = "") {
  const value = readPath(source, path);
  return typeof value === "string" ? value : fallback;
}

function readNumberMap(source: unknown): Record<string, number> {
  if (!isRecord(source)) return {};
  return Object.fromEntries(
    Object.entries(source).filter((entry): entry is [string, number] => typeof entry[1] === "number")
  );
}

function toStages(value: unknown): PrdStage[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((stage) => ({
    id: typeof stage.id === "string" ? stage.id : crypto.randomUUID(),
    label: typeof stage.label === "string" ? stage.label : "PRD stage",
    status: typeof stage.status === "string" ? stage.status : "check",
    detail: typeof stage.detail === "string" ? stage.detail : "No detail available",
  }));
}

export function PrdV1FlowPanel({ className }: { className?: string }) {
  const [state, setState] = useState<PrdFlowState>({
    overallStatus: "checking",
    stages: [],
    counts: {},
    checkedAt: null,
    error: "",
  });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/v1/system/prd-flow", { cache: "no-store" });
      if (!response.ok) throw new Error(`prd-flow ${response.status}`);
      const payload = (await response.json()) as unknown;
      setState({
        overallStatus: readString(payload, ["overall_status"], "check"),
        stages: toStages(readPath(payload, ["stages"])),
        counts: readNumberMap(readPath(payload, ["counts"])),
        checkedAt: new Date().toISOString(),
        error: "",
      });
    } catch (error) {
      setState((current) => ({
        ...current,
        overallStatus: "check",
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

  const complete = state.overallStatus === "ok" && state.stages.length > 0;
  const countItems = [
    ["Factors", state.counts.factor_snapshots],
    ["Signals", state.counts.signal_events],
    ["Decisions", state.counts.coordination_history],
    ["Backtests", state.counts.backtest_results],
    ["Replays", state.counts.replay_sessions],
  ].filter(([, value]) => typeof value === "number");

  return (
    <Card
      data-testid="prd-v1-flow-panel"
      className={cn("overflow-hidden border-sky-500/20 bg-gradient-to-br from-sky-500/10 via-card to-lime-500/10", className)}
    >
      <CardContent className="p-4">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              {loading ? (
                <RefreshCw className="h-4 w-4 animate-spin text-sky-400" />
              ) : complete ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              ) : (
                <AlertTriangle className="h-4 w-4 text-amber-400" />
              )}
              <h2 className="text-sm font-semibold text-foreground">PRD v1 Full Flow</h2>
              <Badge className={cn("text-[10px]", complete ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300")}>
                {loading ? "CHECKING" : complete ? "COMPLETE" : "CHECK"}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Data ingestion, storage, factors, TradingAgents, audit/replay/backtest, and frontend/API visibility.
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
            PRD flow check failed: {state.error}
          </div>
        )}

        <div className="mb-4 flex flex-wrap gap-2">
          {countItems.map(([label, value]) => (
            <Badge key={label} variant="outline" className="border-border bg-background/60 text-[10px] text-muted-foreground">
              {label}: <span className="ml-1 text-foreground">{value}</span>
            </Badge>
          ))}
        </div>

        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          {state.stages.map((stage, index) => {
            const Icon = stageIcons[index % stageIcons.length];
            const ok = stage.status === "ok";
            return (
              <div
                key={stage.id}
                className={cn(
                  "rounded-xl border bg-background/55 p-3",
                  ok ? "border-emerald-500/20" : "border-amber-500/25"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <Icon className={cn("mt-0.5 h-4 w-4", ok ? "text-emerald-400" : "text-amber-400")} />
                  <span className={cn("h-2 w-2 rounded-full", ok ? "bg-emerald-400" : "bg-amber-400")} />
                </div>
                <h3 className="mt-2 text-xs font-semibold leading-snug text-foreground">{stage.label}</h3>
                <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed text-muted-foreground">{stage.detail}</p>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
