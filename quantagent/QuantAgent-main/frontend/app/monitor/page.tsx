"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  Brain,
  CheckCircle2,
  CircleAlert,
  Database,
  ExternalLink,
  FileText,
  GitBranch,
  Layers,
  MonitorCog,
  RefreshCw,
  Server,
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

const FEATURE_ICONS: Record<string, typeof Database> = {
  data_source_management: Database,
  standardized_factors: Layers,
  backtest_tasks: BarChart3,
  audit_view: Shield,
  system_monitoring: MonitorCog,
};

const NAV_LINKS = [
  { href: "/dashboard", label: "仪表盘", icon: BarChart3 },
  { href: "/data-sources", label: "数据源", icon: Database },
  { href: "/signals", label: "因子/信号", icon: Layers },
  { href: "/backtest", label: "回测", icon: GitBranch },
  { href: "/audit", label: "回测与审计", icon: Shield },
  { href: "/monitor", label: "系统监控", icon: MonitorCog, active: true },
];

function statusText(status: string) {
  if (status === "ready") return "可使用";
  if (status === "partial") return "部分可用";
  if (status === "check") return "需检查";
  return status || "未知";
}

function statusClass(status: string) {
  if (status === "ready") return "border-emerald-400/30 bg-emerald-500/15 text-emerald-200";
  if (status === "partial") return "border-amber-400/30 bg-amber-500/15 text-amber-200";
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

function compactList(values?: string[]) {
  if (!values || values.length === 0) return "暂无记录";
  if (values.length <= 4) return values.join("、");
  return `${values.slice(0, 4).join("、")} 等 ${values.length} 项`;
}

function pipelineNumber(pipeline: Record<string, unknown>, key: string) {
  const value = pipeline[key];
  return typeof value === "number" ? value : 0;
}

export default function MonitorPage() {
  const [overview, setOverview] = useState<MonitorOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/v1/system/frontend-api-overview", { cache: "no-store" });
      const data = (await response.json()) as MonitorOverview;
      if (!response.ok) throw new Error("系统监控数据加载失败");
      setOverview(data);
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

  return (
    <div className="min-h-screen bg-[#071019] text-slate-100">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#071019]/85 backdrop-blur-xl">
        <div className="container mx-auto flex items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="rounded-xl border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div>
              <h1 className="text-lg font-semibold text-white">系统状态监控</h1>
              <p className="text-xs text-slate-500">按 PRD 10.6 查看前端页面、后端接口和真实数据状态</p>
            </div>
          </div>

          <nav className="hidden items-center gap-1 lg:flex">
            {NAV_LINKS.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition",
                    item.active
                      ? "border border-cyan-400/30 bg-cyan-500/15 text-cyan-100"
                      : "text-slate-300 hover:bg-white/10 hover:text-white",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <Button
            size="sm"
            variant="outline"
            className="border-white/10 bg-white/5 text-slate-100 hover:bg-white/10"
            onClick={() => void refresh()}
            disabled={loading}
          >
            <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
            刷新
          </Button>
        </div>
      </header>

      <main className="container mx-auto space-y-6 px-4 py-6">
        <section className="overflow-hidden rounded-3xl border border-cyan-400/20 bg-[radial-gradient(circle_at_10%_10%,rgba(34,211,238,0.2),transparent_32%),radial-gradient(circle_at_80%_20%,rgba(16,185,129,0.16),transparent_30%),linear-gradient(135deg,rgba(15,23,42,0.98),rgba(2,6,23,0.98))] p-6 shadow-2xl">
          <div className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr] lg:items-end">
            <div>
              <Badge className="border-cyan-400/30 bg-cyan-500/15 text-cyan-100">PRD 10.6 前端与 API</Badge>
              <h2 className="mt-4 max-w-4xl text-3xl font-semibold tracking-tight text-white">
                把“页面在哪里、接口是什么、数据从哪来”放到一个地方
              </h2>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">
                这个页面不是交易建议，也不是验收报告。它是日常使用入口：看数据源是否可用、因子有没有生成、回测和审计是否有记录、TradingAgents 与基础设施是否在线。
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
