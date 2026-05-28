"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, Archive, ArrowLeft, CheckCircle2, Database, RefreshCw, Server, Wifi } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PrdV1FlowPanel } from "@/components/prd/PrdV1FlowPanel";
import { cn } from "@/lib/utils";

type JsonRecord = Record<string, unknown>;

interface BackfillRow {
  symbol?: string;
  interval?: string;
  status?: string;
  row_count?: number;
}

interface EquityTicker {
  symbol: string;
  price: number;
  change_percent: number;
}

interface ActionState {
  loading: boolean;
  message: string;
  error: string;
}

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

function readNumber(source: unknown, path: string[], fallback = 0) {
  const value = readPath(source, path);
  return typeof value === "number" ? value : fallback;
}

function toBackfillRows(value: unknown): BackfillRow[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((row) => ({
    symbol: typeof row.symbol === "string" ? row.symbol : undefined,
    interval: typeof row.interval === "string" ? row.interval : undefined,
    status: typeof row.status === "string" ? row.status : undefined,
    row_count: typeof row.row_count === "number" ? row.row_count : undefined,
  }));
}

function toEquityTicker(value: unknown): EquityTicker | null {
  if (!isRecord(value)) return null;
  if (typeof value.symbol !== "string" || typeof value.price !== "number") return null;
  return {
    symbol: value.symbol,
    price: value.price,
    change_percent: typeof value.change_percent === "number" ? value.change_percent : 0,
  };
}

export default function DataSourcesPage() {
  const [health, setHealth] = useState<unknown>(null);
  const [backfillRows, setBackfillRows] = useState<BackfillRow[]>([]);
  const [equity, setEquity] = useState<EquityTicker | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<ActionState>({ loading: false, message: "", error: "" });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [healthRes, backfillRes, equityRes] = await Promise.all([
        fetch("/api/v1/system/health", { cache: "no-store" }),
        fetch("/api/v1/market/backfill/status", { cache: "no-store" }),
        fetch("/api/v1/market/equity/ticker/SPY?provider=yfinance", { cache: "no-store" }),
      ]);
      const [healthPayload, backfillPayload, equityPayload] = await Promise.all([
        healthRes.ok ? (healthRes.json() as Promise<unknown>) : Promise.resolve(null),
        backfillRes.ok ? (backfillRes.json() as Promise<unknown>) : Promise.resolve(null),
        equityRes.ok ? (equityRes.json() as Promise<unknown>) : Promise.resolve(null),
      ]);
      setHealth(healthPayload);
      setBackfillRows(toBackfillRows(readPath(backfillPayload, ["intervals"])));
      setEquity(toEquityTicker(equityPayload));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const runAction = useCallback(async (kind: "backfill" | "archive") => {
    setAction({ loading: true, message: "", error: "" });
    try {
      const response = await fetch(
        kind === "backfill" ? "/api/v1/market/backfill" : "/api/v1/market/archive/parquet",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            kind === "backfill"
              ? { symbol: "BTCUSDT", interval: "1h", mode: "sync" }
              : { symbols: ["BTCUSDT"], intervals: ["1h"], limit: 360 }
          ),
        }
      );
      const payload = (await response.json().catch(() => ({}))) as unknown;
      if (!response.ok) {
        throw new Error(readString(payload, ["detail"], `${kind} failed with ${response.status}`));
      }
      setAction({
        loading: false,
        message: kind === "backfill"
          ? "Scoped BTCUSDT/1h backfill started."
          : `Archived ${readNumber(payload, ["total_written"])} BTCUSDT/1h rows to Parquet.`,
        error: "",
      });
      await refresh();
    } catch (error) {
      setAction({
        loading: false,
        message: "",
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }, [refresh]);

  const openbbOk = readString(health, ["layers", "L1_data_source", "openbb", "status"]) === "ok";
  const fredOk = readString(health, ["layers", "L1_data_source", "fred", "status"]) === "ok";
  const equityOk = readString(health, ["layers", "L1_data_source", "equity", "status"]) === "ok";
  const clickhouseOk = readString(health, ["layers", "L4_storage", "clickhouse", "status"]) === "ok";
  const parquetFiles = readNumber(health, ["layers", "L4_storage", "parquet", "files"]);
  const okBackfills = backfillRows.filter((row) => row.status === "ok").length;

  const cards = [
    { label: "OpenBB", ok: openbbOk, detail: readString(health, ["layers", "L1_data_source", "openbb", "detail"], "Unified data entry"), icon: Wifi },
    { label: "FRED", ok: fredOk, detail: readString(health, ["layers", "L1_data_source", "fred", "detail"], "Macro via OpenBB"), icon: Database },
    { label: "Equity", ok: equityOk && Boolean(equity), detail: equity ? `${equity.symbol} $${equity.price.toFixed(2)}` : "SPY ticker unavailable", icon: Activity },
    { label: "ClickHouse", ok: clickhouseOk, detail: readString(health, ["layers", "L4_storage", "clickhouse", "detail"], "Time-series storage"), icon: Server },
    { label: "Parquet", ok: parquetFiles > 0, detail: `${parquetFiles} archive files`, icon: Archive },
    { label: "Backfill", ok: backfillRows.length > 0 && okBackfills === backfillRows.length, detail: `${okBackfills}/${backfillRows.length} symbol/interval ok`, icon: CheckCircle2 },
  ];

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="container mx-auto flex items-center justify-between px-4 py-4">
          <div>
            <Link href="/dashboard" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to dashboard
            </Link>
            <h1 className="text-xl font-bold text-foreground">Data Source Management</h1>
            <p className="text-xs text-muted-foreground">
              OpenBB/FRED/equity health, ClickHouse storage, Parquet archive, and scoped backfill controls.
            </p>
          </div>
          <Button size="sm" variant="outline" className="border-border" onClick={refresh} disabled={loading}>
            <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </header>

      <main className="container mx-auto space-y-6 px-4 py-6">
        <PrdV1FlowPanel />

        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
          {cards.map((card) => {
            const Icon = card.icon;
            return (
              <Card key={card.label} className="border-border bg-card">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <Icon className={cn("h-4 w-4", card.ok ? "text-emerald-400" : "text-amber-400")} />
                    <Badge className={cn("text-[10px]", card.ok ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300")}>
                      {card.ok ? "OK" : "CHECK"}
                    </Badge>
                  </div>
                  <h2 className="mt-3 text-sm font-semibold text-foreground">{card.label}</h2>
                  <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">{card.detail}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <Card className="border-sky-500/20 bg-gradient-to-r from-sky-500/10 via-card to-emerald-500/10">
          <CardHeader>
            <CardTitle className="text-sm text-foreground">Scoped Maintenance Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col gap-3 md:flex-row">
              <Button disabled={action.loading} onClick={() => void runAction("backfill")} className="bg-blue-600 text-white hover:bg-blue-500">
                {action.loading ? <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Database className="mr-1.5 h-3.5 w-3.5" />}
                Sync BTCUSDT 1h
              </Button>
              <Button disabled={action.loading} variant="outline" className="border-border" onClick={() => void runAction("archive")}>
                {action.loading ? <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Archive className="mr-1.5 h-3.5 w-3.5" />}
                Archive BTCUSDT 1h to Parquet
              </Button>
            </div>
            {action.message && <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{action.message}</div>}
            {action.error && <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-300">{action.error}</div>}
            <p className="text-[11px] text-muted-foreground">
              Actions are scoped to BTCUSDT/1h so they are safe for smoke validation and do not launch a full historical reload.
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
