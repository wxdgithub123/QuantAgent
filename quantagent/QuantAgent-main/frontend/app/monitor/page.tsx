"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import {
  Activity,
  BarChart3,
  Brain,
  CheckCircle2,
  CircleAlert,
  Database,
  ExternalLink,
  FileText,
  Layers,
  MonitorCog,
  RefreshCw,
  Server,
  Settings2,
  Shield,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ApiItem {
  method: string;
  path: string;
  purpose: string;
}

interface EvidenceItem {
  label: string;
  value: string;
}

interface FeatureItem {
  key: string;
  title: string;
  status: string;
  front_page: string;
  page_label: string;
  description: string;
  apis: ApiItem[];
  evidence: EvidenceItem[];
}

interface PageItem {
  path: string;
  label: string;
  role: string;
}

interface SourceNote {
  name: string;
  role: string;
}

interface SystemItem {
  label: string;
  status: string;
  detail?: string | null;
}

interface MonitorOverview {
  timestamp: number;
  overall_status: string;
  features: FeatureItem[];
  pages: PageItem[];
  counts: Record<string, number>;
  market_coverage: {
    source_groups: number;
    total_rows: number;
    providers: string[];
    exchanges: string[];
  };
  pipeline: Record<string, unknown>;
  source_notes: SourceNote[];
  system: SystemItem[];
}

interface TradingAgentsConfig {
  timestamp: number;
  overall_status: string;
  enabled: boolean;
  service: {
    status: string;
    http_status?: number | null;
    url: string;
    timeout_seconds: number;
    error?: string | null;
  };
  mode: {
    configured: string;
    fastResearchReady: boolean;
    fullGraphRequested: boolean;
    fullGraphReady: boolean;
    supportedModes: string[];
    selectedAnalysts: string[];
    roles: string[];
  };
  llm: {
    provider: string;
    openaiConfigured: boolean;
    ollamaEnabled: boolean;
    baseUrl: string;
    model: string;
    quickModel: string;
    deepModel: string;
  };
  graph: {
    tradingagentsAvailable: boolean;
    importError?: string | null;
    strongAcceptanceEligible: boolean;
  };
  data_boundary: {
    agent_input_policy: string;
    pit_rule: string;
    externalFallbackAllowed: boolean;
    allowCcxtFallback: boolean;
    allowBinanceFallback: boolean;
    snapshotEndpoints: string[];
  };
  readiness: Array<{
    id: string;
    label: string;
    status: string;
    detail: string;
  }>;
}

interface OpsSection {
  key: string;
  label: string;
  status: string;
  api?: string;
}

interface FreshnessItem {
  table: string;
  label: string;
  status: string;
  row_count: number;
  latest_available_time?: string | null;
  age_seconds?: number | null;
  pit_rule?: string | null;
  detail?: string | null;
  error?: string | null;
}

interface Phase2OpsMonitor {
  schema_version: string;
  generated_at: string;
  overall_status: string;
  pit_rule: string;
  agent_input_policy: string;
  external_fallback_allowed: boolean;
  sections: OpsSection[];
  data_freshness: Record<string, FreshnessItem>;
  pipeline_storage?: {
    status?: string;
    store_available?: boolean;
    running?: boolean;
    macro_stored?: number;
    news_stored?: number;
    latest_macro_available_time?: string | null;
    latest_news_available_time?: string | null;
  };
  llm_monitor?: {
    status?: string;
    provider?: string;
    model?: string;
    quick_model?: string;
    deep_model?: string;
    service_status?: string;
    timeout_seconds?: number | null;
    mode?: string;
    full_graph_ready?: boolean;
    call_monitoring?: string;
  };
  audit_health?: {
    status?: string;
    append_only?: boolean;
    row_count?: number;
    hash_coverage?: string;
    latest_created_at?: string | null;
    export_api?: string;
    replayable?: boolean;
  };
  execution_risk?: {
    status?: string;
    chain?: string[];
    riskguard?: {
      status?: string;
      fail_action_default?: string;
      rules?: string[];
      forbidden_symbols?: string[];
      max_single_position_pct?: number;
      max_total_exposure_pct?: number;
    };
    simulation?: {
      paper_trade_count?: number;
      open_position_count?: number;
      risk_event_count?: number;
      risk_blocked_count?: number;
      real_ordering_enabled?: boolean;
    };
  };
  backtest_replay?: {
    queue?: Record<string, unknown>;
    duckdb_archive?: Record<string, unknown>;
    replay_table?: FreshnessItem;
    result_table?: FreshnessItem;
  };
  resources?: Record<string, unknown>;
}

const FEATURE_ICONS: Record<string, typeof Database> = {
  data_source_management: Database,
  standardized_factors: Layers,
  backtest_tasks: BarChart3,
  audit_view: Shield,
  system_monitoring: MonitorCog,
};

function statusText(status: string) {
  if (status === "ready") return "可使用";
  if (status === "partial") return "部分可用";
  if (status === "declared") return "已声明";
  if (status === "degraded") return "降级";
  if (status === "disabled") return "未启用";
  if (status === "check") return "需检查";
  return status || "未知";
}

function statusClass(status: string) {
  if (status === "ready") return "border-emerald-400/30 bg-emerald-500/15 text-emerald-200";
  if (status === "partial" || status === "declared") return "border-amber-400/30 bg-amber-500/15 text-amber-200";
  if (status === "degraded") return "border-rose-400/30 bg-rose-500/15 text-rose-200";
  return "border-slate-400/25 bg-slate-500/15 text-slate-300";
}

function formatNumber(value: unknown) {
  const numberValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numberValue) ? numberValue.toLocaleString("zh-CN") : "0";
}

function formatTime(timestamp?: number) {
  if (!timestamp) return "暂无";
  return new Date(timestamp * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatIsoTime(value?: string | null) {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatAgeSeconds(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "暂无";
  if (value < 60) return `${Math.round(value)} 秒`;
  if (value < 3600) return `${Math.round(value / 60)} 分钟`;
  if (value < 86400) return `${Math.round(value / 3600)} 小时`;
  return `${Math.round(value / 86400)} 天`;
}

function compactList(values?: string[]) {
  if (!values || values.length === 0) return "暂无记录";
  if (values.length <= 4) return values.join("、");
  return `${values.slice(0, 4).join("、")} 等 ${values.length} 项`;
}

function boolText(value?: boolean) {
  return value ? "是" : "否";
}

function compactMode(value?: string) {
  return value ? value.replaceAll("_", " ") : "unknown";
}

function pipelineNumber(pipeline: Record<string, unknown>, key: string) {
  const value = pipeline[key];
  return typeof value === "number" ? value : 0;
}

function recordNumber(record: Record<string, unknown> | undefined, key: string) {
  const value = record?.[key];
  return typeof value === "number" ? value : 0;
}

function recordText(record: Record<string, unknown> | undefined, key: string, fallback = "暂无") {
  const value = record?.[key];
  if (typeof value === "string" && value) return value;
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") return formatNumber(value);
  return fallback;
}

export default function MonitorPage() {
  const [overview, setOverview] = useState<MonitorOverview | null>(null);
  const [tradingAgentsConfig, setTradingAgentsConfig] = useState<TradingAgentsConfig | null>(null);
  const [opsMonitor, setOpsMonitor] = useState<Phase2OpsMonitor | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [response, configResponse, opsResponse] = await Promise.all([
        fetch("/api/v1/system/frontend-api-overview", { cache: "no-store" }),
        fetch("/api/v1/system/tradingagents-config", { cache: "no-store" }),
        fetch("/api/v1/system/phase2-ops-monitor", { cache: "no-store" }),
      ]);
      if (!response.ok) throw new Error("系统监控数据加载失败");
      const data = (await response.json()) as MonitorOverview;
      setOverview(data);
      if (configResponse.ok) {
        setTradingAgentsConfig((await configResponse.json()) as TradingAgentsConfig);
      } else {
        setTradingAgentsConfig(null);
      }
      if (opsResponse.ok) {
        setOpsMonitor((await opsResponse.json()) as Phase2OpsMonitor);
      } else {
        setOpsMonitor(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const readyCount = useMemo(
    () => overview?.features.filter((feature) => feature.status === "ready").length ?? 0,
    [overview],
  );
  const totalFeatures = overview?.features.length ?? 5;
  const counts = overview?.counts ?? {};
  const pipeline = overview?.pipeline ?? {};
  const coverage = overview?.market_coverage;
  const freshnessItems = Object.values(opsMonitor?.data_freshness ?? {});
  const importantFreshness = freshnessItems.filter((item) => [
    "bar_1m",
    "bar_1h",
    "quote_latest",
    "news_event",
    "macro_indicator",
    "fundamental_report",
    "corporate_action",
    "adjustment_factor",
  ].includes(item.table));
  const queue = opsMonitor?.backtest_replay?.queue;
  const duckdbArchive = opsMonitor?.backtest_replay?.duckdb_archive;
  const simulation = opsMonitor?.execution_risk?.simulation;
  const riskguard = opsMonitor?.execution_risk?.riskguard;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppTopNav
        activeSection="monitor"
        title="系统状态"
        subtitle="服务健康、数据链路与缓存诊断"
        rightSlot={
          <Button
            size="sm"
            variant="outline"
            className="border-border"
            onClick={() => void refresh()}
            disabled={loading}
          >
            <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
            刷新
          </Button>
        }
      />

      <main className="container mx-auto space-y-6 px-4 py-6">
        <section className="overflow-hidden rounded-3xl border border-cyan-400/20 bg-[radial-gradient(circle_at_10%_10%,rgba(34,211,238,0.2),transparent_32%),radial-gradient(circle_at_80%_20%,rgba(16,185,129,0.16),transparent_30%),linear-gradient(135deg,rgba(15,23,42,0.98),rgba(2,6,23,0.98))] p-6 shadow-2xl">
          <div className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr] lg:items-end">
            <div>
              <Badge className="border-cyan-400/30 bg-cyan-500/15 text-cyan-100">PRD 10.6 前端与 API</Badge>
              <h2 className="mt-4 max-w-4xl text-3xl font-semibold tracking-tight text-white">
                把“页面在哪里、接口是什么、数据从哪来”放到一个地方
              </h2>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">
                这个页面不是交易建议，也不是项目总结报告。它是日常使用入口：看数据源是否可用、因子有没有生成、回测和审计是否有记录、TradingAgents 与基础设施是否在线。
              </p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-slate-400">10.6 功能项</p>
                  <p className="mt-2 text-3xl font-semibold text-white">{readyCount}/{totalFeatures}</p>
                  <p className="mt-1 text-xs text-slate-500">按真实接口返回判断</p>
                </div>
                {readyCount === totalFeatures ? (
                  <CheckCircle2 className="h-11 w-11 text-emerald-300" />
                ) : (
                  <CircleAlert className="h-11 w-11 text-amber-300" />
                )}
              </div>
              <div className="mt-4 text-xs text-slate-500">最近刷新：{formatTime(overview?.timestamp)}</div>
            </div>
          </div>
        </section>

        {error && (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
            {error}
          </div>
        )}

        <section className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-white">
                    <Settings2 className="h-5 w-5 text-cyan-200" />
                    TradingAgents 配置
                  </CardTitle>
                  <p className="mt-2 text-xs text-slate-500">P1 配置中心切片：有效模式、模型、服务和本地输入边界。</p>
                </div>
                <Badge className={statusClass(tradingAgentsConfig?.overall_status || "check")}>
                  {statusText(tradingAgentsConfig?.overall_status || "check")}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
                  <p className="text-[11px] text-slate-500">模式</p>
                  <p className="mt-1 truncate text-sm font-medium text-white" title={tradingAgentsConfig?.mode.configured}>
                    {compactMode(tradingAgentsConfig?.mode.configured)}
                  </p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
                  <p className="text-[11px] text-slate-500">Provider</p>
                  <p className="mt-1 truncate text-sm font-medium text-white">{tradingAgentsConfig?.llm.provider || "unknown"}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
                  <p className="text-[11px] text-slate-500">Quick / Deep</p>
                  <p
                    className="mt-1 truncate text-sm font-medium text-white"
                    title={`${tradingAgentsConfig?.llm.quickModel || ""} / ${tradingAgentsConfig?.llm.deepModel || ""}`}
                  >
                    {tradingAgentsConfig?.llm.quickModel || "unknown"} / {tradingAgentsConfig?.llm.deepModel || "unknown"}
                  </p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
                  <p className="text-[11px] text-slate-500">Full Graph</p>
                  <p className="mt-1 text-sm font-medium text-white">{boolText(tradingAgentsConfig?.mode.fullGraphReady)}</p>
                </div>
              </div>

              <div className="grid gap-3 lg:grid-cols-2">
                <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/10 p-4">
                  <p className="text-xs text-cyan-100">服务</p>
                  <div className="mt-2 grid gap-2 text-xs text-slate-300">
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-slate-500">状态</span>
                      <span>{tradingAgentsConfig?.service.status || "unknown"}</span>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-slate-500">URL</span>
                      <span className="break-all text-right font-mono">{tradingAgentsConfig?.service.url || "unknown"}</span>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-slate-500">超时</span>
                      <span>{tradingAgentsConfig?.service.timeout_seconds ?? "—"}s</span>
                    </div>
                  </div>
                </div>
                <div className="rounded-2xl border border-emerald-400/20 bg-emerald-500/10 p-4">
                  <p className="text-xs text-emerald-100">输入边界</p>
                  <div className="mt-2 grid gap-2 text-xs text-slate-300">
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-slate-500">策略</span>
                      <span>{tradingAgentsConfig?.data_boundary.agent_input_policy || "local_storage_only"}</span>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-slate-500">PIT</span>
                      <span className="text-right font-mono">{tradingAgentsConfig?.data_boundary.pit_rule || "available_time <= as_of_time"}</span>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-slate-500">外部回退</span>
                      <span>{boolText(tradingAgentsConfig?.data_boundary.externalFallbackAllowed)}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Link
                  href="/decisions"
                  className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-400/20 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-100 transition hover:bg-cyan-500/20"
                >
                  打开决策中心
                  <ExternalLink className="h-3.5 w-3.5" />
                </Link>
                <Link
                  href="/audit"
                  className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-100 transition hover:bg-emerald-500/20"
                >
                  打开审计台
                  <ExternalLink className="h-3.5 w-3.5" />
                </Link>
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Brain className="h-5 w-5 text-emerald-200" />
                运行准备度
              </CardTitle>
              <p className="text-xs text-slate-500">快速研究可用性和完整图强验收条件分开显示。</p>
            </CardHeader>
            <CardContent className="space-y-3">
              {(tradingAgentsConfig?.readiness || []).map((item) => (
                <div key={item.id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-white">{item.label}</p>
                      <p className="mt-1 text-xs leading-5 text-slate-500">{item.detail}</p>
                    </div>
                    <Badge className={statusClass(item.status)}>{statusText(item.status)}</Badge>
                  </div>
                </div>
              ))}
              {!tradingAgentsConfig && (
                <div className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-slate-400">
                  暂无 TradingAgents 配置数据
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-white">
                    <MonitorCog className="h-5 w-5 text-cyan-200" />
                    Phase2 运维总控
                  </CardTitle>
                  <p className="mt-2 text-xs text-slate-500">
                    {opsMonitor?.agent_input_policy || "local_storage_only"} · {opsMonitor?.pit_rule || "available_time <= as_of_time"} · 外部回退 {boolText(opsMonitor?.external_fallback_allowed)}
                  </p>
                </div>
                <Badge className={statusClass(opsMonitor?.overall_status || "check")}>
                  {statusText(opsMonitor?.overall_status || "check")}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {(opsMonitor?.sections || []).map((section) => (
                  <div key={section.key} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium text-white">{section.label}</p>
                        <p className="mt-1 break-all font-mono text-[11px] text-slate-500">{section.api || "local contract"}</p>
                      </div>
                      <Badge className={statusClass(section.status)}>{statusText(section.status)}</Badge>
                    </div>
                  </div>
                ))}
                {!opsMonitor && (
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-slate-400">
                    暂无 Phase2 运维总控数据
                  </div>
                )}
              </div>

              <div className="overflow-hidden rounded-2xl border border-white/10 bg-black/20">
                <div className="grid grid-cols-[1fr_0.6fr_0.8fr_0.6fr] gap-3 border-b border-white/10 px-4 py-3 text-xs text-slate-500">
                  <span>数据类型</span>
                  <span>行数</span>
                  <span>最新可见时间</span>
                  <span>年龄</span>
                </div>
                <div className="divide-y divide-white/10">
                  {importantFreshness.map((item) => (
                    <div key={item.table} className="grid grid-cols-[1fr_0.6fr_0.8fr_0.6fr] gap-3 px-4 py-3 text-xs">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge className={statusClass(item.status)}>{statusText(item.status)}</Badge>
                          <span className="truncate text-slate-200">{item.label}</span>
                        </div>
                        <p className="mt-1 truncate font-mono text-[11px] text-slate-600">{item.table}</p>
                      </div>
                      <span className="text-slate-300">{formatNumber(item.row_count)}</span>
                      <span className="text-slate-300">{formatIsoTime(item.latest_available_time)}</span>
                      <span className="text-slate-400">{formatAgeSeconds(item.age_seconds)}</span>
                    </div>
                  ))}
                  {importantFreshness.length === 0 && (
                    <div className="px-4 py-6 text-sm text-slate-500">暂无数据新鲜度明细</div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4">
            <Card className="border-white/10 bg-white/[0.04]">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <CardTitle className="flex items-center gap-2 text-white">
                    <Shield className="h-5 w-5 text-emerald-200" />
                    审计健康
                  </CardTitle>
                  <Badge className={statusClass(opsMonitor?.audit_health?.status || "check")}>
                    {statusText(opsMonitor?.audit_health?.status || "check")}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="grid gap-2 text-xs text-slate-300">
                <div className="flex justify-between gap-3"><span className="text-slate-500">append-only</span><span>{boolText(opsMonitor?.audit_health?.append_only)}</span></div>
                <div className="flex justify-between gap-3"><span className="text-slate-500">审计记录</span><span>{formatNumber(opsMonitor?.audit_health?.row_count)}</span></div>
                <div className="flex justify-between gap-3"><span className="text-slate-500">hash 覆盖</span><span>{opsMonitor?.audit_health?.hash_coverage || "暂无"}</span></div>
                <div className="flex justify-between gap-3"><span className="text-slate-500">最新写入</span><span>{formatIsoTime(opsMonitor?.audit_health?.latest_created_at)}</span></div>
                <div className="flex justify-between gap-3"><span className="text-slate-500">导出接口</span><span className="break-all text-right font-mono">{opsMonitor?.audit_health?.export_api || "/api/v1/audit/records/{audit_id}/export"}</span></div>
              </CardContent>
            </Card>

            <Card className="border-white/10 bg-white/[0.04]">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <CardTitle className="flex items-center gap-2 text-white">
                    <Activity className="h-5 w-5 text-amber-200" />
                    执行与 RiskGuard
                  </CardTitle>
                  <Badge className={statusClass(opsMonitor?.execution_risk?.status || "check")}>
                    {statusText(opsMonitor?.execution_risk?.status || "check")}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="rounded-2xl border border-white/10 bg-black/20 p-3 text-xs text-slate-300">
                  <p className="text-slate-500">链路</p>
                  <p className="mt-1 text-slate-200">{(opsMonitor?.execution_risk?.chain || ["OrderIntent", "RiskGuard", "PaperOrder", "PnL", "AuditRecord"]).join(" → ")}</p>
                </div>
                <div className="grid gap-2 text-xs text-slate-300 sm:grid-cols-2">
                  <div>模拟成交：{formatNumber(simulation?.paper_trade_count)}</div>
                  <div>持仓：{formatNumber(simulation?.open_position_count)}</div>
                  <div>风控事件：{formatNumber(simulation?.risk_event_count)}</div>
                  <div>拦截：{formatNumber(simulation?.risk_blocked_count)}</div>
                  <div>实盘下单：{boolText(simulation?.real_ordering_enabled)}</div>
                  <div>失败动作：{riskguard?.fail_action_default || "block"}</div>
                </div>
                <p className="text-xs leading-5 text-slate-500">规则：{compactList(riskguard?.rules)}</p>
              </CardContent>
            </Card>

            <Card className="border-white/10 bg-white/[0.04]">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <CardTitle className="flex items-center gap-2 text-white">
                    <BarChart3 className="h-5 w-5 text-sky-200" />
                    回测/回放运维
                  </CardTitle>
                  <Badge className={statusClass(opsMonitor?.backtest_replay?.duckdb_archive ? "ready" : "check")}>
                    {statusText(recordText(duckdbArchive, "status", "check"))}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-xs text-slate-300">
                <div className="grid gap-2 sm:grid-cols-2">
                  <div>队列：{recordText(queue, "queue_scope", "in_process_memory")}</div>
                  <div>活跃任务：{formatNumber(recordNumber(queue, "active_tasks"))}</div>
                  <div>最大并行：{formatNumber(recordNumber(queue, "max_parallel"))}</div>
                  <div>归档行：{formatNumber(recordNumber(duckdbArchive, "latest_result_count"))}</div>
                  <div>取消：{recordText(queue, "cancel_supported")}</div>
                  <div>重试：{recordText(queue, "retry_supported")}</div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
                  <p className="text-slate-500">DuckDB</p>
                  <p className="mt-1 break-all font-mono text-slate-200">{recordText(duckdbArchive, "path", "data/backtest/backtest_results.duckdb")}</p>
                  <p className="mt-1 text-slate-500">{recordText(duckdbArchive, "schema_version", "backtest_duckdb_archive.v1")}</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-400">K线缓存</p>
                  <p className="mt-2 text-2xl font-semibold text-white">{formatNumber(coverage?.total_rows)} 行</p>
                  <p className="mt-2 text-xs leading-5 text-slate-500">ClickHouse 是本地缓存，真实上游看 provider/exchange。</p>
                </div>
                <Database className="h-6 w-6 text-cyan-200" />
              </div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/[0.04]">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-400">因子与信号</p>
                  <p className="mt-2 text-2xl font-semibold text-white">
                    {formatNumber(counts.factor_snapshots)} / {formatNumber(counts.signal_events)}
                  </p>
                  <p className="mt-2 text-xs leading-5 text-slate-500">前者是因子快照，后者是策略信号事件。</p>
                </div>
                <Layers className="h-6 w-6 text-emerald-200" />
              </div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/[0.04]">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-400">回测与回放</p>
                  <p className="mt-2 text-2xl font-semibold text-white">
                    {formatNumber(counts.backtest_results)} / {formatNumber(counts.replay_sessions)}
                  </p>
                  <p className="mt-2 text-xs leading-5 text-slate-500">回测结果和 replay_sessions 会在审计页关联。</p>
                </div>
                <BarChart3 className="h-6 w-6 text-sky-200" />
              </div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/[0.04]">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-400">新闻与宏观</p>
                  <p className="mt-2 text-2xl font-semibold text-white">
                    {formatNumber(pipelineNumber(pipeline, "news_stored"))} / {formatNumber(pipelineNumber(pipeline, "macro_stored"))}
                  </p>
                  <p className="mt-2 text-xs leading-5 text-slate-500">新闻进入上下文；宏观来自 FRED/OECD 等入口。</p>
                </div>
                <FileText className="h-6 w-6 text-amber-200" />
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-5">
          {(overview?.features || []).map((feature) => {
            const Icon = FEATURE_ICONS[feature.key] || Activity;
            return (
              <Card key={feature.key} className="border-white/10 bg-white/[0.04] xl:col-span-1">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="rounded-2xl border border-white/10 bg-white/10 p-2">
                      <Icon className="h-5 w-5 text-cyan-100" />
                    </div>
                    <Badge className={statusClass(feature.status)}>{statusText(feature.status)}</Badge>
                  </div>
                  <CardTitle className="pt-2 text-base text-white">{feature.title}</CardTitle>
                  <p className="text-xs leading-5 text-slate-400">{feature.description}</p>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Link
                    href={feature.front_page}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-400/20 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-100 transition hover:bg-cyan-500/20"
                  >
                    打开{feature.page_label}
                    <ExternalLink className="h-3.5 w-3.5" />
                  </Link>
                  <div className="space-y-2">
                    {feature.evidence.map((item) => (
                      <div key={`${feature.key}-${item.label}`} className="rounded-xl border border-white/10 bg-black/20 p-2.5">
                        <p className="text-[11px] text-slate-500">{item.label}</p>
                        <p className="mt-1 break-words text-xs text-slate-200">{item.value}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </section>

        <section className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Server className="h-5 w-5 text-cyan-200" />
                系统连接状态
              </CardTitle>
              <p className="text-xs text-slate-500">这里看的是服务/组件可用性，不等于所有交易所实盘都已连通。</p>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              {(overview?.system || []).map((item) => (
                <div key={item.label} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-white">{item.label}</p>
                      <p className="mt-1 text-xs leading-5 text-slate-500">{item.detail || "暂无详情"}</p>
                    </div>
                    <Badge className={statusClass(item.status)}>{statusText(item.status)}</Badge>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Brain className="h-5 w-5 text-emerald-200" />
                数据来源说明
              </CardTitle>
              <p className="text-xs text-slate-500">避免把缓存、连接器和上游数据源混在一起看。</p>
            </CardHeader>
            <CardContent className="space-y-3">
              {(overview?.source_notes || []).map((note) => (
                <div key={note.name} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <p className="font-medium text-white">{note.name}</p>
                  <p className="mt-1 text-sm leading-6 text-slate-400">{note.role}</p>
                </div>
              ))}
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/10 p-4">
                  <p className="text-xs text-cyan-100">缓存来源分组</p>
                  <p className="mt-2 text-lg font-semibold text-white">{formatNumber(coverage?.source_groups)}</p>
                  <p className="mt-1 text-xs text-slate-500">{compactList(coverage?.providers)}</p>
                </div>
                <div className="rounded-2xl border border-emerald-400/20 bg-emerald-500/10 p-4">
                  <p className="text-xs text-emerald-100">交易所/市场标记</p>
                  <p className="mt-2 text-sm leading-6 text-white">{compactList(coverage?.exchanges)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="text-white">前端入口对应表</CardTitle>
              <p className="text-xs text-slate-500">以后找功能优先按这个表进，不需要在仪表盘里猜。</p>
            </CardHeader>
            <CardContent className="space-y-2">
              {(overview?.pages || []).map((page) => (
                <Link
                  key={page.path}
                  href={page.path}
                  className="block rounded-2xl border border-white/10 bg-black/20 p-4 transition hover:border-cyan-400/30 hover:bg-cyan-500/10"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-white">{page.label}</p>
                      <p className="mt-1 text-sm leading-6 text-slate-400">{page.role}</p>
                    </div>
                    <span className="font-mono text-xs text-cyan-200">{page.path}</span>
                  </div>
                </Link>
              ))}
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="text-white">后端 API 对应表</CardTitle>
              <p className="text-xs text-slate-500">每个功能卡片实际依赖的接口，方便后续排查。</p>
            </CardHeader>
            <CardContent className="space-y-4">
              {(overview?.features || []).map((feature) => (
                <div key={`api-${feature.key}`} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <p className="font-medium text-white">{feature.title}</p>
                    <Badge className={statusClass(feature.status)}>{statusText(feature.status)}</Badge>
                  </div>
                  <div className="space-y-2">
                    {feature.apis.map((api) => (
                      <div key={`${feature.key}-${api.method}-${api.path}`} className="grid gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs md:grid-cols-[0.82fr_1fr]">
                        <div className="font-mono text-cyan-100">{api.method} {api.path}</div>
                        <div className="text-slate-400">{api.purpose}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </section>

        {loading && (
          <div className="fixed bottom-6 right-6 rounded-full border border-white/10 bg-black/60 px-4 py-2 text-sm text-slate-300 shadow-xl backdrop-blur">
            <RefreshCw className="mr-2 inline h-4 w-4 animate-spin" />
            正在加载系统状态
          </div>
        )}
      </main>
    </div>
  );
}
