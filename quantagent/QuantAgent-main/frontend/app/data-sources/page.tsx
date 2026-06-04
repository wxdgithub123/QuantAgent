"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import {
  Activity,
  Archive,
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  Database,
  Globe2,
  LineChart,
  Newspaper,
  RefreshCw,
  Server,
  Wifi,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PrdV1FlowPanel } from "@/components/prd/PrdV1FlowPanel";
import { cn } from "@/lib/utils";

type JsonRecord = Record<string, unknown>;

const SAMPLE_SYMBOL = "BTCUSDT";
const SAMPLE_INTERVAL = "1h";

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

interface SourceCoverageRow {
  symbol: string;
  interval: string;
  provider: string;
  exchange: string;
  min_time?: string | null;
  max_time?: string | null;
  row_count: number;
}

interface KlineMetadata {
  active_source?: string;
  cache?: string;
  provider?: string;
  exchange?: string;
  updated_at?: string | null;
  symbol?: string;
  interval?: string;
}

interface ActionState {
  loading: boolean;
  message: string;
  error: string;
}

interface PipelineStats {
  macro_stored: number;
  news_stored: number;
  running: boolean;
  store_available?: boolean;
}

interface IngestionRequirement {
  key: string;
  title: string;
  status: string;
  primary: string;
  fallback: string;
  api: string;
  evidence?: JsonRecord;
}

interface IngestionOverview {
  requirements: IngestionRequirement[];
  provider_totals: Record<string, number>;
  source_groups: number;
  notes: string[];
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

async function fetchJson(url: string): Promise<unknown> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal });
    if (!response.ok) return null;
    return (await response.json()) as unknown;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function friendlyDataError() {
  return "数据暂不可用，已展示缓存数据 / 暂无数据。";
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

function toSourceCoverageRows(value: unknown): SourceCoverageRow[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isRecord)
    .map((row) => ({
      symbol: typeof row.symbol === "string" ? row.symbol : "unknown",
      interval: typeof row.interval === "string" ? row.interval : "unknown",
      provider: typeof row.provider === "string" ? row.provider : "unknown",
      exchange: typeof row.exchange === "string" ? row.exchange : "unknown",
      min_time: typeof row.min_time === "string" ? row.min_time : null,
      max_time: typeof row.max_time === "string" ? row.max_time : null,
      row_count: typeof row.row_count === "number" ? row.row_count : 0,
    }));
}

function toKlineMetadata(value: unknown): KlineMetadata | null {
  if (!isRecord(value)) return null;
  return {
    active_source: typeof value.active_source === "string" ? value.active_source : undefined,
    cache: typeof value.cache === "string" ? value.cache : undefined,
    provider: typeof value.provider === "string" ? value.provider : undefined,
    exchange: typeof value.exchange === "string" ? value.exchange : undefined,
    updated_at: typeof value.updated_at === "string" ? value.updated_at : null,
    symbol: typeof value.symbol === "string" ? value.symbol : undefined,
    interval: typeof value.interval === "string" ? value.interval : undefined,
  };
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

function toPipelineStats(value: unknown): PipelineStats | null {
  if (!isRecord(value)) return null;
  return {
    macro_stored: readNumber(value, ["macro_stored"]),
    news_stored: readNumber(value, ["news_stored"]),
    running: Boolean(value.running),
    store_available: typeof value.store_available === "boolean" ? value.store_available : undefined,
  };
}

function toIngestionOverview(value: unknown): IngestionOverview | null {
  if (!isRecord(value)) return null;
  const requirementsValue = value.requirements;
  const requirements = Array.isArray(requirementsValue)
    ? requirementsValue.filter(isRecord).map((item) => ({
        key: typeof item.key === "string" ? item.key : crypto.randomUUID(),
        title: typeof item.title === "string" ? item.title : "数据入口",
        status: typeof item.status === "string" ? item.status : "check",
        primary: typeof item.primary === "string" ? item.primary : "未记录",
        fallback: typeof item.fallback === "string" ? item.fallback : "未记录",
        api: typeof item.api === "string" ? item.api : "未记录",
        evidence: isRecord(item.evidence) ? item.evidence : undefined,
      }))
    : [];
  return {
    requirements,
    provider_totals: isRecord(value.provider_totals)
      ? Object.fromEntries(Object.entries(value.provider_totals).filter((entry): entry is [string, number] => typeof entry[1] === "number"))
      : {},
    source_groups: typeof value.source_groups === "number" ? value.source_groups : 0,
    notes: Array.isArray(value.notes) ? value.notes.filter((item): item is string => typeof item === "string") : [],
  };
}

function formatTimestamp(value?: string | null) {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatWindow(minTime?: string | null, maxTime?: string | null) {
  if (!minTime && !maxTime) return "暂无";
  return `${formatTimestamp(minTime)} → ${formatTimestamp(maxTime)}`;
}

function sourceFamily(row: SourceCoverageRow) {
  const provider = row.provider.toLowerCase();
  const exchange = row.exchange.toLowerCase();

  if (provider.startsWith("openbb")) return "OpenBB";
  if (provider === "ccxt" || provider.startsWith("ccxt")) return "CCXT";
  if (provider === "legacy" || exchange === "clickhouse") return "Legacy";
  return "Other";
}

function sourceFamilyClass(family: string) {
  switch (family) {
    case "OpenBB":
      return "border-sky-500/20 bg-sky-500/15 text-sky-200";
    case "CCXT":
      return "border-emerald-500/20 bg-emerald-500/15 text-emerald-200";
    case "Legacy":
      return "border-amber-500/20 bg-amber-500/15 text-amber-200";
    default:
      return "border-slate-500/20 bg-slate-500/15 text-slate-200";
  }
}

function sourceKey(row: SourceCoverageRow) {
  return `${row.symbol}|${row.interval}|${row.provider}|${row.exchange}`;
}

function metadataKey(metadata: KlineMetadata | null) {
  if (!metadata?.symbol || !metadata?.interval || !metadata?.provider || !metadata?.exchange) {
    return "";
  }
  return `${metadata.symbol}|${metadata.interval}|${metadata.provider}|${metadata.exchange}`;
}

function sortCoverageRows(rows: SourceCoverageRow[], metadata: KlineMetadata | null) {
  const activeKey = metadataKey(metadata);
  return [...rows].sort((left, right) => {
    const leftActive = activeKey && sourceKey(left) === activeKey ? 1 : 0;
    const rightActive = activeKey && sourceKey(right) === activeKey ? 1 : 0;
    if (leftActive !== rightActive) return rightActive - leftActive;

    return (
      left.symbol.localeCompare(right.symbol) ||
      left.interval.localeCompare(right.interval) ||
      left.provider.localeCompare(right.provider) ||
      left.exchange.localeCompare(right.exchange)
    );
  });
}

function requirementClass(status: string) {
  if (status === "ok") return "border-emerald-500/20 bg-emerald-500/15 text-emerald-200";
  return "border-amber-500/20 bg-amber-500/15 text-amber-200";
}

function requirementLabel(status: string) {
  return status === "ok" ? "可用" : "检查";
}

function shortEvidence(value: unknown): string {
  if (value === null || value === undefined) return "暂无";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.join("、") || "暂无";
  if (isRecord(value)) {
    return Object.entries(value)
      .slice(0, 3)
      .map(([key, val]) => `${key}: ${shortEvidence(val)}`)
      .join("；");
  }
  return String(value);
}

export default function DataSourcesPage() {
  const [health, setHealth] = useState<unknown>(null);
  const [backfillRows, setBackfillRows] = useState<BackfillRow[]>([]);
  const [equity, setEquity] = useState<EquityTicker | null>(null);
  const [coverageRows, setCoverageRows] = useState<SourceCoverageRow[]>([]);
  const [klineMetadata, setKlineMetadata] = useState<KlineMetadata | null>(null);
  const [pipelineStats, setPipelineStats] = useState<PipelineStats | null>(null);
  const [ingestionOverview, setIngestionOverview] = useState<IngestionOverview | null>(null);
  const [providerTest, setProviderTest] = useState({ provider: "yfinance", fallbackExchange: "okx", loading: false, message: "", error: "" });
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<ActionState>({ loading: false, message: "", error: "" });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [healthPayload, backfillPayload, equityPayload, coveragePayload, klinePayload, pipelinePayload, ingestionPayload] = await Promise.all([
        fetchJson("/api/v1/system/health"),
        fetchJson("/api/v1/market/backfill/status"),
        fetchJson("/api/v1/market/equity/ticker/SPY?provider=yfinance"),
        fetchJson("/api/v1/market/source-coverage"),
        fetchJson(`/api/v1/market/klines/${SAMPLE_SYMBOL}?interval=${SAMPLE_INTERVAL}&limit=1`),
        fetchJson("/api/v1/system/pipeline"),
        fetchJson("/api/v1/market/data-ingestion-overview"),
      ]);

      setHealth(healthPayload);
      setBackfillRows(toBackfillRows(readPath(backfillPayload, ["intervals"])));
      setEquity(toEquityTicker(equityPayload));
      const nextMetadata = toKlineMetadata(readPath(klinePayload, ["metadata"]));
      setKlineMetadata(nextMetadata);
      setPipelineStats(toPipelineStats(pipelinePayload));
      setCoverageRows(sortCoverageRows(toSourceCoverageRows(readPath(coveragePayload, ["sources"])), nextMetadata));
      setIngestionOverview(toIngestionOverview(ingestionPayload));
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
          ? "已触发 BTCUSDT/1小时小范围同步。"
          : `已归档 ${readNumber(payload, ["total_written"])} 行 BTCUSDT/1小时数据到 Parquet。`,
        error: "",
      });
      await refresh();
    } catch (error) {
      setAction({
        loading: false,
        message: "",
        error: friendlyDataError(),
      });
    }
  }, [refresh]);

  const runProviderTest = useCallback(async () => {
    setProviderTest((current) => ({ ...current, loading: true, message: "", error: "" }));
    try {
      const params = new URLSearchParams({
        interval: SAMPLE_INTERVAL,
        limit: "5",
        provider: providerTest.provider,
        fallback_exchange: providerTest.fallbackExchange,
        allow_ccxt_fallback: "true",
      });
      const response = await fetch(`/api/v1/market/klines/${SAMPLE_SYMBOL}?${params}`, { cache: "no-store" });
      const payload = (await response.json().catch(() => ({}))) as unknown;
      if (!response.ok) throw new Error(readString(payload, ["detail"], `provider test failed: ${response.status}`));
      const rows = Array.isArray(readPath(payload, ["data"])) ? (readPath(payload, ["data"]) as unknown[]).length : 0;
      const activeSource = readString(payload, ["metadata", "active_source"], readString(payload, ["source"], "unknown"));
      const fallbackChain = readPath(payload, ["metadata", "fallback_chain"]);
      setProviderTest((current) => ({
        ...current,
        loading: false,
        message: `取到 ${rows} 根 ${SAMPLE_SYMBOL}/${SAMPLE_INTERVAL} K线；当前读取层：${activeSource}；降级链：${Array.isArray(fallbackChain) ? fallbackChain.join(" → ") : "未返回"}`,
        error: "",
      }));
      await refresh();
    } catch (error) {
      setProviderTest((current) => ({
        ...current,
        loading: false,
        message: "",
        error: friendlyDataError(),
      }));
    }
  }, [providerTest.fallbackExchange, providerTest.provider, refresh]);

  const openbbOk = readString(health, ["layers", "L1_data_source", "openbb", "status"]) === "ok";
  const ccxtOk = readString(health, ["layers", "L1_data_source", "ccxt", "status"]) === "ok";
  const fredOk = readString(health, ["layers", "L1_data_source", "fred", "status"]) === "ok";
  const equityOk = readString(health, ["layers", "L1_data_source", "equity", "status"]) === "ok";
  const clickhouseOk = readString(health, ["layers", "L4_storage", "clickhouse", "status"]) === "ok";
  const parquetFiles = readNumber(health, ["layers", "L4_storage", "parquet", "files"]);
  const okBackfills = backfillRows.filter((row) => row.status === "ok").length;
  const ccxtExchanges = readPath(health, ["layers", "L1_data_source", "ccxt", "exchanges"]);
  const ccxtExchangeCount = Array.isArray(ccxtExchanges) ? ccxtExchanges.length : 0;
  const activeCoverageKey = metadataKey(klineMetadata);
  const activeCoverageRow = activeCoverageKey
    ? coverageRows.find((row) => sourceKey(row) === activeCoverageKey) ?? null
    : null;
  const sourceTotals = coverageRows.reduce<Record<string, number>>((acc, row) => {
    const family = sourceFamily(row);
    acc[family] = (acc[family] ?? 0) + row.row_count;
    return acc;
  }, {});
  const totalCoverageRows = coverageRows.reduce((sum, row) => sum + row.row_count, 0);
  const macroCount = pipelineStats?.macro_stored ?? 0;
  const newsCount = pipelineStats?.news_stored ?? 0;

  const dataPortals = [
    {
      title: "加密行情",
      summary: "价格、K 线、交易所覆盖和热门币种。",
      location: "仪表盘 > 总览",
      source: klineMetadata?.provider && klineMetadata.exchange
        ? `${klineMetadata.provider}:${klineMetadata.exchange}`
        : klineMetadata?.active_source || "统一行情网关",
      ok: openbbOk || ccxtOk || Boolean(activeCoverageRow) || Boolean(klineMetadata?.active_source),
      href: "/dashboard",
      action: "查看 K 线",
      icon: BarChart3,
      accent: "from-cyan-500/15 to-blue-500/5",
    },
    {
      title: "股票行情",
      summary: "SPY 是标普500ETF，用于跨资产参考和美股市场背景。",
      location: "本页健康检查",
      source: equity ? `${equity.symbol} 标普500ETF $${equity.price.toFixed(2)} · OpenBB/yfinance` : "SPY 标普500ETF暂不可用",
      ok: equityOk && Boolean(equity),
      href: "#health-cards",
      action: "看股票状态",
      icon: LineChart,
      accent: "from-emerald-500/15 to-teal-500/5",
    },
    {
      title: "新闻快讯",
      summary: "加密新闻会整理成智能体分析材料，供后续决策参考。",
      location: "仪表盘 > 总览",
      source: `${newsCount.toLocaleString()} 条已入库`,
      ok: newsCount > 0 || Boolean(pipelineStats?.store_available),
      href: "/dashboard?tab=overview",
      action: "看新闻面板",
      icon: Newspaper,
      accent: "from-amber-500/15 to-orange-500/5",
    },
    {
      title: "宏观数据",
      summary: "FRED/OECD 利率、通胀、就业等宏观指标。",
      location: "仪表盘 > 总览",
      source: `${macroCount.toLocaleString()} 条已入库 · FRED via OpenBB`,
      ok: fredOk && (macroCount > 0 || Boolean(pipelineStats?.store_available)),
      href: "/dashboard?tab=overview",
      action: "看宏观面板",
      icon: Globe2,
      accent: "from-violet-500/15 to-sky-500/5",
    },
  ];

  const cards = [
    { label: "OpenBB", ok: openbbOk, detail: readString(health, ["layers", "L1_data_source", "openbb", "detail"], "统一金融数据入口"), icon: Wifi },
    { label: "CCXT", ok: ccxtOk, detail: ccxtExchangeCount ? `已配置 ${ccxtExchangeCount} 个交易所连接器，实际可用需逐个测试` : "连接器列表待加载，实际可用需逐个测试", icon: Activity },
    { label: "FRED", ok: fredOk, detail: readString(health, ["layers", "L1_data_source", "fred", "detail"], "通过 OpenBB 接宏观数据"), icon: Database },
    { label: "股票", ok: equityOk && Boolean(equity), detail: equity ? `${equity.symbol} 是标普500ETF，价格来自 OpenBB/yfinance` : "SPY 是标普500ETF，行情暂不可用", icon: Activity },
    { label: "ClickHouse", ok: clickhouseOk, detail: readString(health, ["layers", "L4_storage", "clickhouse", "detail"], "时序行情存储"), icon: Server },
    { label: "Parquet", ok: parquetFiles > 0, detail: `${parquetFiles} 个历史归档文件，用于回放/备份，不是实时行情源`, icon: Archive },
    { label: "补数检查", ok: backfillRows.length > 0 && okBackfills === backfillRows.length, detail: `${okBackfills}/${backfillRows.length} 状态正常，不代表历史已补满`, icon: CheckCircle2 },
  ];

  return (
    <div className="min-h-screen bg-background">
      <AppTopNav
        activeSection="data-sources"
        title="数据源工作台"
        subtitle="行情接入、数据标准化与存储监控"
        rightSlot={
          <Button size="sm" variant="outline" className="border-border" onClick={refresh} disabled={loading}>
            <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", loading && "animate-spin")} />
            刷新
          </Button>
        }
      />

      <main className="container mx-auto space-y-6 px-4 py-6">
        <section className="overflow-hidden rounded-3xl border border-border/70 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-5 shadow-2xl shadow-black/20">
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge className="border border-cyan-500/20 bg-cyan-500/15 text-cyan-200">数据入口</Badge>
                <Badge variant="outline" className="border-emerald-500/25 bg-emerald-500/10 text-emerald-300">OpenBB 主入口</Badge>
                <Badge variant="outline" className="border-border bg-background/40 text-muted-foreground">CCXT 交易所补充</Badge>
              </div>
              <h2 className="text-2xl font-bold tracking-tight text-foreground">数据应该在哪里看？</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                这个页面负责管理和检查数据源；真正看行情和新闻时，优先去仪表盘对应分区。下面四张卡把入口、来源和状态放在一起，减少来回猜。
              </p>
            </div>
            <div className="rounded-2xl border border-border/70 bg-background/35 p-3 text-xs text-muted-foreground">
              <p className="font-medium text-foreground">当前样例</p>
              <p className="mt-1 font-mono">{SAMPLE_SYMBOL} / {SAMPLE_INTERVAL}</p>
            </div>
          </div>
        </section>

        <Card className="border-cyan-500/20 bg-gradient-to-r from-cyan-500/10 via-card to-emerald-500/10">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-foreground">数据接入状态</CardTitle>
            <p className="text-xs leading-5 text-muted-foreground">
              这里集中查看 crypto 行情、股票行情、新闻、宏观数据、OpenBB provider 切换和备用数据源降级。
              绿色表示当前接口或缓存里有真实返回；降级链只用于补救，不会把演示或空数据写成真实行情。
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {(ingestionOverview?.requirements || []).map((item) => (
                <div key={item.key} className="rounded-2xl border border-border/70 bg-background/40 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground">{item.title}</h3>
                      <p className="mt-1 font-mono text-[10px] text-cyan-300">{item.api}</p>
                    </div>
                    <Badge className={cn("text-[10px]", requirementClass(item.status))}>{requirementLabel(item.status)}</Badge>
                  </div>
                  <div className="mt-3 space-y-2 text-[11px] leading-5 text-muted-foreground">
                    <p><span className="text-foreground/80">主链路：</span>{item.primary}</p>
                    <p><span className="text-foreground/80">降级链：</span>{item.fallback}</p>
                    {item.evidence && (
                      <p><span className="text-foreground/80">证据：</span>{shortEvidence(item.evidence)}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="rounded-2xl border border-border/70 bg-background/45 p-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">OpenBB provider / 备用降级测试</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    测试 BTCUSDT 的 1小时 K线读取链路：本地缓存 → OpenBB provider → CCXT 交易所降级。默认不打 Binance。
                  </p>
                </div>
                <div className="grid gap-2 sm:grid-cols-[150px_150px_auto]">
                  <select
                    value={providerTest.provider}
                    onChange={(event) => setProviderTest((current) => ({ ...current, provider: event.target.value }))}
                    className="h-9 rounded-lg border border-border bg-secondary px-3 text-xs text-foreground"
                  >
                    <option value="yfinance">OpenBB/yfinance</option>
                    <option value="fmp">OpenBB/fmp</option>
                    <option value="tiingo">OpenBB/tiingo</option>
                  </select>
                  <select
                    value={providerTest.fallbackExchange}
                    onChange={(event) => setProviderTest((current) => ({ ...current, fallbackExchange: event.target.value }))}
                    className="h-9 rounded-lg border border-border bg-secondary px-3 text-xs text-foreground"
                  >
                    <option value="okx">CCXT/OKX</option>
                    <option value="bybit">CCXT/Bybit</option>
                    <option value="gateio">CCXT/Gate.io</option>
                    <option value="kraken">CCXT/Kraken</option>
                  </select>
                  <Button disabled={providerTest.loading} onClick={() => void runProviderTest()} className="h-9 bg-cyan-600 text-white hover:bg-cyan-500">
                    {providerTest.loading ? <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Wifi className="mr-1.5 h-3.5 w-3.5" />}
                    测试读取
                  </Button>
                </div>
              </div>
              {providerTest.message && (
                <div className="mt-3 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
                  {providerTest.message}
                </div>
              )}
              {providerTest.error && (
                <div className="mt-3 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                  {providerTest.error}
                </div>
              )}
            </div>

            {ingestionOverview?.notes?.length ? (
              <div className="space-y-1 rounded-xl border border-border/60 bg-card/50 px-3 py-2 text-[11px] text-muted-foreground">
                {ingestionOverview.notes.map((note) => <p key={note}>{note}</p>)}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {dataPortals.map((portal) => {
            const Icon = portal.icon;
            return (
              <Card key={portal.title} className={cn("overflow-hidden border-border bg-gradient-to-br", portal.accent)}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="rounded-2xl border border-white/10 bg-background/35 p-2">
                      <Icon className="h-5 w-5 text-cyan-200" />
                    </div>
                    <Badge className={cn("text-[10px]", portal.ok ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300")}>
                      {portal.ok ? "已接入" : "待检查"}
                    </Badge>
                  </div>
                  <h3 className="mt-4 text-base font-semibold text-foreground">{portal.title}</h3>
                  <p className="mt-1 min-h-[38px] text-xs leading-5 text-muted-foreground">{portal.summary}</p>
                  <div className="mt-4 space-y-2 rounded-2xl border border-border/60 bg-background/35 p-3 text-xs">
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">入口</span>
                      <span className="text-right font-medium text-foreground">{portal.location}</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">来源</span>
                      <span className="max-w-[180px] truncate text-right font-mono text-[11px] text-foreground" title={portal.source}>
                        {portal.source}
                      </span>
                    </div>
                  </div>
                  <Link href={portal.href} className="mt-4 inline-flex text-xs font-medium text-cyan-300 hover:text-cyan-200">
                    {portal.action}
                  </Link>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <PrdV1FlowPanel />

        <Card className="border-emerald-500/20 bg-gradient-to-r from-emerald-500/10 via-card to-slate-500/10">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-foreground">当前 BTCUSDT 1小时 K 线来源</CardTitle>
            <p className="text-xs text-muted-foreground">
              这里和仪表盘 K 线使用同一条行情网关。当前行数只表示这个来源窗口里已缓存的 K 线数量，不代表完整历史已经补满。
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2 text-[11px]">
              <Badge className={cn("border", "bg-background/70 text-foreground", activeCoverageRow ? "border-emerald-500/25" : "border-border")}>
                当前源 {klineMetadata?.active_source || "market_data_gateway"}
              </Badge>
              <Badge className="border border-sky-500/20 bg-sky-500/15 text-sky-200">
                缓存 {klineMetadata?.cache || "clickhouse:klines"}
              </Badge>
              <Badge className="border border-violet-500/20 bg-violet-500/15 text-violet-200">
                提供方 {klineMetadata?.provider || "unknown"}
              </Badge>
              <Badge className="border border-cyan-500/20 bg-cyan-500/15 text-cyan-200">
                交易所 {klineMetadata?.exchange || "unknown"}
              </Badge>
              <Badge className="border border-slate-500/20 bg-slate-500/15 text-slate-200">
                更新 {formatTimestamp(klineMetadata?.updated_at)}
              </Badge>
              <Badge className="border border-amber-500/20 bg-amber-500/15 text-amber-200">
                该源缓存行数 {activeCoverageRow ? activeCoverageRow.row_count.toLocaleString() : "暂无"}
              </Badge>
            </div>
            <p className="text-[11px] text-muted-foreground">
              K 线可以在 OpenBB、CCXT 与历史 ClickHouse 数据之间切换，但每批数据都会保留来源标签，避免混在一起看不清。
            </p>
          </CardContent>
        </Card>

        <div id="health-cards" className="grid gap-4 md:grid-cols-3 xl:grid-cols-7">
          {cards.map((card) => {
            const Icon = card.icon;
            return (
              <Card key={card.label} className="border-border bg-card">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <Icon className={cn("h-4 w-4", card.ok ? "text-emerald-400" : "text-amber-400")} />
                    <Badge className={cn("text-[10px]", card.ok ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300")}>
                      {card.ok ? "正常" : "检查"}
                    </Badge>
                  </div>
                  <h2 className="mt-3 text-sm font-semibold text-foreground">{card.label}</h2>
                  <p className="mt-1 line-clamp-3 text-[11px] text-muted-foreground">{card.detail}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
        <p className="rounded-xl border border-border/60 bg-card/60 px-3 py-2 text-[11px] text-muted-foreground">
          说明：绿色“正常”表示对应服务或检查项可用；“已配置连接器”不等于所有交易所都已实测接通；“补数检查正常”也不等于历史 K 线已经全部补满。
        </p>

        <Card className="border-border bg-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-foreground">历史行情覆盖表</CardTitle>
            <p className="text-xs text-muted-foreground">
              这里列出数据库里已有的 K 线：包含标的、周期、真实来源、行数和时间范围。行数是当前已入库数量，不代表完整历史覆盖。
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2 text-[11px]">
              <Badge className="border border-border bg-background/70 text-foreground">分组 {coverageRows.length}</Badge>
              <Badge className={sourceFamilyClass("OpenBB")}>OpenBB {sourceTotals.OpenBB ? sourceTotals.OpenBB.toLocaleString() : 0} 行</Badge>
              <Badge className={sourceFamilyClass("CCXT")}>CCXT {sourceTotals.CCXT ? sourceTotals.CCXT.toLocaleString() : 0} 行</Badge>
              <Badge className={sourceFamilyClass("Legacy")}>Legacy {sourceTotals.Legacy ? sourceTotals.Legacy.toLocaleString() : 0} 行</Badge>
              <Badge className="border border-slate-500/20 bg-slate-500/15 text-slate-200">
                总行数 {totalCoverageRows.toLocaleString()}
              </Badge>
            </div>

            <div className="overflow-hidden rounded-xl border border-border">
              <div className="max-h-[420px] overflow-auto">
                <table className="min-w-full text-left text-xs">
                  <thead className="sticky top-0 z-10 bg-muted/95 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 font-medium">标的</th>
                      <th className="px-3 py-2 font-medium">周期</th>
                      <th className="px-3 py-2 font-medium">数据源</th>
                      <th className="px-3 py-2 font-medium">行数</th>
                      <th className="px-3 py-2 font-medium">覆盖窗口</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coverageRows.length > 0 ? (
                      coverageRows.map((row) => {
                        const family = sourceFamily(row);
                        const isActive = activeCoverageKey ? sourceKey(row) === activeCoverageKey : false;
                        return (
                          <tr
                            key={sourceKey(row)}
                            className={cn("border-t border-border/60", isActive && "bg-emerald-500/5")}
                          >
                            <td className="px-3 py-2 font-mono text-[11px] text-foreground">{row.symbol}</td>
                            <td className="px-3 py-2 text-[11px] text-foreground">{row.interval}</td>
                            <td className="px-3 py-2">
                              <div className="flex flex-col gap-1">
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <Badge className={cn("text-[10px]", sourceFamilyClass(family))}>{family}</Badge>
                                  {isActive && (
                                    <Badge className="border border-emerald-500/20 bg-emerald-500/15 text-[10px] text-emerald-200">
                                      当前使用
                                    </Badge>
                                  )}
                                </div>
                                <span className="font-mono text-[10px] text-muted-foreground">
                                  {row.provider}:{row.exchange}
                                </span>
                              </div>
                            </td>
                            <td className="px-3 py-2 font-mono text-[11px] text-foreground">
                              {row.row_count.toLocaleString()}
                            </td>
                            <td className="px-3 py-2 text-[11px] text-muted-foreground">
                              {formatWindow(row.min_time, row.max_time)}
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td className="px-3 py-6 text-center text-[11px] text-muted-foreground" colSpan={5}>
                          暂无覆盖记录。K 线入库后，这里会显示 OpenBB、CCXT 和 Legacy 的覆盖范围。
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-sky-500/20 bg-gradient-to-r from-sky-500/10 via-card to-emerald-500/10">
          <CardHeader>
            <CardTitle className="text-sm text-foreground">数据链路测试（手动）</CardTitle>
            <p className="text-xs text-muted-foreground">
              这些按钮只用于连通性检查和排障：测试同步样例 K 线、测试归档文件，不会下单，也不会启动自动交易策略。
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col gap-3 md:flex-row">
              <Button disabled={action.loading} onClick={() => void runAction("backfill")} className="bg-blue-600 text-white hover:bg-blue-500">
                {action.loading ? <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Database className="mr-1.5 h-3.5 w-3.5" />}
                测试同步 BTCUSDT 1小时K线
              </Button>
              <Button disabled={action.loading} variant="outline" className="border-border" onClick={() => void runAction("archive")}>
                {action.loading ? <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Archive className="mr-1.5 h-3.5 w-3.5" />}
                测试导出 BTCUSDT 1小时K线到 Parquet
              </Button>
            </div>
            {action.message && <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{action.message}</div>}
            {action.error && <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-300">{action.error}</div>}
            <p className="text-[11px] text-muted-foreground">
              当前只针对 BTCUSDT/1小时，适合快速确认链路。正式数据更新应由后端数据管道或定时任务自动完成。
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
