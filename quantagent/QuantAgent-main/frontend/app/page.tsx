"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Brain,
  CheckCircle2,
  Clock3,
  Database,
  ExternalLink,
  FileJson,
  GitBranch,
  Layers,
  MonitorCog,
  PlayCircle,
  RefreshCw,
  Route,
  Shield,
  Sparkles,
  Wallet,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type StepStatus = "done" | "partial" | "pending" | "error" | string;

interface ClosedLoopStep {
  stepName: string;
  status: StepStatus;
  latestUpdateTime?: string | null;
  sampleId?: string | null;
  shortDescription: string;
  relatedPageUrl: string;
  relatedApi: string;
  evidenceCount: number;
}

interface PrdAcceptanceItem {
  name: string;
  status: StepStatus;
  evidence: string;
  jumpLink: string;
  note: string;
}

interface PrdAcceptancePhase {
  phaseName: string;
  items: PrdAcceptanceItem[];
}

interface DemoPathItem {
  title: string;
  description: string;
  url: string;
  expectedResult: string;
  fallbackNote: string;
}

interface DemoHealth {
  backendHealth?: string;
  databaseStatus?: string;
  redisStatus?: string;
  clickhouseStatus?: string;
  ingestionStatus?: string;
  frontendBuildStatus?: string;
  lastSmokeTestTime?: string;
  apiErrorCount?: number;
  lastErrorSummary?: string;
}

interface LatestSample {
  latestBacktestId?: number | string | null;
  latestReplaySessionId?: string | null;
  latestDecisionId?: number | string | null;
  latestOrderIntentId?: string | null;
  latestPaperOrderId?: string | null;
  latestAuditRecordId?: number | string | null;
  executionMode?: string | null;
  symbol?: string | null;
  strategyType?: string | null;
  interval?: string | null;
  createdAt?: string | null;
  backtestDetailUrl?: string;
  replayUrl?: string;
  decisionDetailUrl?: string;
  orderIntentUrl?: string;
  paperOrderUrl?: string;
  auditRecordUrl?: string;
}

interface DemoOverview {
  schemaVersion?: string;
  generatedAt?: string;
  overallStatus?: StepStatus;
  closedLoopSteps: ClosedLoopStep[];
  prdAcceptance: PrdAcceptancePhase[];
  demoPath: DemoPathItem[];
  health: DemoHealth;
  latestSample?: LatestSample | null;
  summary?: {
    doneSteps?: number;
    totalSteps?: number;
    phase1Done?: number;
    phase2Done?: number;
  };
}

const NAV_LINKS = [
  { href: "/", label: "演示首页", icon: Sparkles, active: true },
  { href: "/dashboard", label: "研究台", icon: BarChart3 },
  { href: "/data-sources", label: "数据源", icon: Database },
  { href: "/signals", label: "因子/信号", icon: Layers },
  { href: "/backtest", label: "回测台", icon: GitBranch },
  { href: "/audit", label: "审计台", icon: Shield },
  { href: "/monitor", label: "系统监控", icon: MonitorCog },
];

const FALLBACK_STEPS: ClosedLoopStep[] = [
  "数据接入",
  "数据标准化",
  "因子计算",
  "信号触发",
  "Agent 决策",
  "OrderIntent",
  "RiskGuard",
  "模拟执行",
  "持仓 / PnL",
  "回测验证",
  "历史回放",
  "审计导出",
].map((stepName) => ({
  stepName,
  status: "pending",
  latestUpdateTime: null,
  sampleId: null,
  shortDescription: "后端数据接口暂未响应，请检查后端服务是否已启动。",
  relatedPageUrl: "/monitor",
  relatedApi: "/api/v1/system/demo-overview",
  evidenceCount: 0,
}));

const FALLBACK_PRD: PrdAcceptancePhase[] = [
  {
    phaseName: "第一阶段",
    items: [
      "数据接入",
      "标准化数据模型",
      "TradingAgents 消费 AnalysisContext",
      "point-in-time 回测",
      "决策审计和回放",
      "前端配置、查看和复盘",
    ].map((name) => ({
      name,
      status: "pending",
      evidence: "后端暂未响应，刷新页面重试",
      jumpLink: "/monitor",
      note: "后端数据暂不可用时使用该兜底状态。",
    })),
  },
  {
    phaseName: "第二阶段",
    items: [
      "OrderIntent",
      "RiskGuard",
      "模拟交易执行",
      "研究台",
      "回测台",
      "审计台",
      "历史回放",
      "三台联动",
    ].map((name) => ({
      name,
      status: "pending",
      evidence: "后端暂未响应，刷新页面重试",
      jumpLink: "/monitor",
      note: "后端数据暂不可用时使用该兜底状态。",
    })),
  },
];

const FALLBACK_DEMO_PATH: DemoPathItem[] = [
  { title: "查看数据源状态", description: "确认数据入口和缓存状态。", url: "/data-sources", expectedResult: "看到数据源健康信息。", fallbackNote: "暂无数据时看空状态。" },
  { title: "查看因子资产目录", description: "了解因子分类和可用性。", url: "/signals", expectedResult: "看到因子、策略、信号关系。", fallbackNote: "暂无统计时显示暂无数据。" },
  { title: "运行 Agent 审计回测", description: "生成可追溯回测样例。", url: "/backtest", expectedResult: "看到回测结果和交易明细。", fallbackNote: "可直接看历史样例。" },
  { title: "查看历史回放", description: "按时间点还原事件流。", url: "/replay", expectedResult: "看到播放器和事件详情。", fallbackNote: "暂无会话时进入回放首页。" },
  { title: "查看审计记录", description: "验证链路可导出。", url: "/audit", expectedResult: "看到不可变审计记录。", fallbackNote: "暂无关联时看审计列表。" },
];

const STATUS_LABEL: Record<string, string> = {
  done: "已完成",
  partial: "部分完成",
  pending: "待补充",
  error: "异常",
  ok: "正常",
  connected: "已连接",
  unavailable: "暂不可用",
  unknown: "未知",
};

const STEP_ICONS: Record<string, typeof Database> = {
  数据接入: Database,
  数据标准化: Route,
  因子计算: Layers,
  信号触发: Activity,
  "Agent 决策": Brain,
  OrderIntent: FileJson,
  RiskGuard: Shield,
  模拟执行: PlayCircle,
  "持仓 / PnL": Wallet,
  回测验证: GitBranch,
  历史回放: Clock3,
  审计导出: FileJson,
};

function statusLabel(status?: string | null) {
  if (!status) return "未知";
  return STATUS_LABEL[status] || status;
}

function statusClass(status?: string | null) {
  if (status === "done" || status === "ok" || status === "connected") {
    return "border-emerald-400/30 bg-emerald-500/15 text-emerald-100";
  }
  if (status === "partial") {
    return "border-amber-400/30 bg-amber-500/15 text-amber-100";
  }
  if (status === "error") {
    return "border-rose-400/30 bg-rose-500/15 text-rose-100";
  }
  return "border-slate-400/25 bg-slate-500/15 text-slate-300";
}

function formatNumber(value: unknown) {
  const numberValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numberValue) ? numberValue.toLocaleString("zh-CN") : "0";
}

function formatTime(value?: string | null) {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "暂无";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function executionModeLabel(mode?: string | null) {
  if (mode === "agent_audited") return "Agent 审计回测";
  if (mode === "rule_only") return "普通规则回测";
  return mode || "暂无数据";
}

async function fetchOverviewWithTimeout(timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch("/api/v1/system/demo-overview", {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error("overview_unavailable");
    }
    return (await response.json()) as DemoOverview;
  } finally {
    window.clearTimeout(timer);
  }
}

export default function DemoHomePage() {
  const [overview, setOverview] = useState<DemoOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");

  async function refresh() {
    setLoading(true);
    setNotice("");
    try {
      const data = await fetchOverviewWithTimeout();
      setOverview(data);
    } catch {
      setOverview(null);
      setNotice("后端数据接口暂未响应，请检查后端服务是否已启动。请稍后刷新或先进入各功能页查看缓存数据。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const closedLoopSteps = overview?.closedLoopSteps?.length ? overview.closedLoopSteps : FALLBACK_STEPS;
  const prdAcceptance = overview?.prdAcceptance?.length ? overview.prdAcceptance : FALLBACK_PRD;
  const demoPath = overview?.demoPath?.length ? overview.demoPath : FALLBACK_DEMO_PATH;
  const health = overview?.health || {};
  const latestSample = overview?.latestSample || null;
  const doneSteps = overview?.summary?.doneSteps ?? closedLoopSteps.filter((item) => item.status === "done").length;
  const totalSteps = overview?.summary?.totalSteps ?? closedLoopSteps.length;
  const phase1 = prdAcceptance[0];
  const phase2 = prdAcceptance[1];
  const phase1Done = overview?.summary?.phase1Done ?? (phase1?.items || []).filter((item) => item.status === "done").length;
  const phase2Done = overview?.summary?.phase2Done ?? (phase2?.items || []).filter((item) => item.status === "done").length;

  return (
    <div className="min-h-screen overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none fixed inset-0 -z-10">
        <div className="absolute left-[-8rem] top-[-8rem] h-96 w-96 rounded-full bg-cyan-500/20 blur-3xl" />
        <div className="absolute right-[-10rem] top-40 h-[30rem] w-[30rem] rounded-full bg-emerald-500/10 blur-3xl" />
        <div className="absolute bottom-[-12rem] left-1/3 h-[28rem] w-[28rem] rounded-full bg-amber-500/10 blur-3xl" />
      </div>

      <AppTopNav
        activeSection="home"
        title="QuantAgent OS"
        subtitle="闭环演示总览"
        rightSlot={
          <Button
            variant="outline"
            size="sm"
            className="border-border"
            onClick={() => void refresh()}
            disabled={loading}
          >
            <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
            刷新状态
          </Button>
        }
      />

      <main className="container mx-auto space-y-6 px-4 py-6">
        <section className="overflow-hidden rounded-[2rem] border border-cyan-400/20 bg-[linear-gradient(135deg,rgba(8,47,73,0.9),rgba(2,6,23,0.96)_45%,rgba(6,78,59,0.72))] p-6 shadow-2xl">
          <div className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr] lg:items-end">
            <div>
              <Badge className="border-cyan-400/30 bg-cyan-500/15 text-cyan-100">
                P5 演示闭环总览
              </Badge>
              <h2 className="mt-4 max-w-4xl text-3xl font-semibold tracking-tight text-white md:text-5xl">
                一条线讲清楚：数据进来，策略判断，Agent 决策，模拟执行，最后能回测、回放、审计。
              </h2>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-300">
                这个页面不替代研究台或交易页，它是汇报入口：先看系统闭环状态，再按推荐路径逐页演示证据。
                任何缺数据或接口异常都会显示友好兜底，不直接暴露底层错误。
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
                <p className="text-sm text-slate-400">闭环步骤</p>
                <p className="mt-2 text-3xl font-semibold text-white">{doneSteps}/{totalSteps}</p>
                <p className="mt-1 text-xs text-slate-500">按真实记录和健康状态判断</p>
              </div>
              <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
                <p className="text-sm text-slate-400">第一阶段验收</p>
                <p className="mt-2 text-3xl font-semibold text-white">{phase1Done}/{phase1?.items.length || 0}</p>
                <p className="mt-1 text-xs text-slate-500">数据、PIT、Agent、审计和前端</p>
              </div>
              <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
                <p className="text-sm text-slate-400">第二阶段验收</p>
                <p className="mt-2 text-3xl font-semibold text-white">{phase2Done}/{phase2?.items.length || 0}</p>
                <p className="mt-1 text-xs text-slate-500">OrderIntent、RiskGuard、三台联动</p>
              </div>
            </div>
          </div>
        </section>

        {notice && (
          <section className="rounded-2xl border border-amber-400/25 bg-amber-500/10 p-4 text-sm text-amber-100">
            {notice}
          </section>
        )}

        <section className="space-y-4">
          <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
            <div>
              <h2 className="text-xl font-semibold text-white">系统闭环状态</h2>
              <p className="mt-1 text-sm text-slate-500">每一步都给出跳转页面、接口、样例 ID 和证据数量。</p>
            </div>
            <Badge className={statusClass(overview?.overallStatus || "partial")}>
              总体：{statusLabel(overview?.overallStatus || "partial")}
            </Badge>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {closedLoopSteps.map((step, index) => {
              const Icon = STEP_ICONS[step.stepName] || Activity;
              return (
                <Card key={`${step.stepName}-${index}`} className="group border-white/10 bg-white/[0.04] transition hover:border-cyan-400/30 hover:bg-cyan-500/10">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="rounded-2xl border border-white/10 bg-black/20 p-2">
                        <Icon className="h-5 w-5 text-cyan-100" />
                      </div>
                      <Badge className={statusClass(step.status)}>{statusLabel(step.status)}</Badge>
                    </div>
                    <div className="mt-4 flex items-center gap-2">
                      <span className="font-mono text-xs text-cyan-200">{String(index + 1).padStart(2, "0")}</span>
                      <h3 className="font-semibold text-white">{step.stepName}</h3>
                    </div>
                    <p className="mt-2 min-h-12 text-xs leading-5 text-slate-400">{step.shortDescription}</p>
                    <div className="mt-4 space-y-2 rounded-2xl border border-white/10 bg-black/20 p-3 text-xs">
                      <p className="flex justify-between gap-3 text-slate-400">
                        <span>证据数量</span>
                        <span className="font-mono text-slate-100">{formatNumber(step.evidenceCount)}</span>
                      </p>
                      <p className="flex justify-between gap-3 text-slate-400">
                        <span>样例</span>
                        <span className="max-w-36 truncate font-mono text-slate-100">{step.sampleId || "暂无样例数据"}</span>
                      </p>
                      <p className="flex justify-between gap-3 text-slate-400">
                        <span>更新时间</span>
                        <span className="text-slate-100">{formatTime(step.latestUpdateTime)}</span>
                      </p>
                    </div>
                    <div className="mt-4 flex items-center justify-between gap-3">
                      <Link href={step.relatedPageUrl} className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-100 hover:text-cyan-50">
                        查看详情
                        <ExternalLink className="h-3.5 w-3.5" />
                      </Link>
                      <span className="max-w-40 truncate font-mono text-[10px] text-slate-500">{step.relatedApi}</span>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          {prdAcceptance.map((phase) => {
            const done = phase.items.filter((item) => item.status === "done").length;
            return (
              <Card key={phase.phaseName} className="border-white/10 bg-white/[0.04]">
                <CardHeader>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <CardTitle className="text-white">{phase.phaseName} PRD 验收进度</CardTitle>
                      <p className="mt-1 text-xs text-slate-500">不是验收结论书，是演示时方便快速定位证据。</p>
                    </div>
                    <Badge className="border-cyan-400/30 bg-cyan-500/15 text-cyan-100">{done}/{phase.items.length}</Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  {phase.items.map((item) => (
                    <Link
                      key={`${phase.phaseName}-${item.name}`}
                      href={item.jumpLink}
                      className="block rounded-2xl border border-white/10 bg-black/20 p-3 transition hover:border-cyan-400/30 hover:bg-cyan-500/10"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-medium text-white">{item.name}</p>
                          <p className="mt-1 text-xs leading-5 text-slate-400">{item.evidence}</p>
                          <p className="mt-1 text-[11px] leading-5 text-slate-500">{item.note}</p>
                        </div>
                        <Badge className={statusClass(item.status)}>{statusLabel(item.status)}</Badge>
                      </div>
                    </Link>
                  ))}
                </CardContent>
              </Card>
            );
          })}
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Route className="h-5 w-5 text-cyan-200" />
                推荐演示路径
              </CardTitle>
              <p className="text-xs text-slate-500">按这个顺序讲，能从“数据来源”自然讲到“可审计闭环”。</p>
            </CardHeader>
            <CardContent className="space-y-3">
              {demoPath.map((item, index) => (
                <Link
                  key={`${item.title}-${index}`}
                  href={item.url}
                  className="group grid gap-3 rounded-2xl border border-white/10 bg-black/20 p-4 transition hover:border-cyan-400/30 hover:bg-cyan-500/10 md:grid-cols-[auto_1fr_auto]"
                >
                  <div className="flex h-9 w-9 items-center justify-center rounded-full border border-cyan-400/25 bg-cyan-500/15 font-mono text-sm text-cyan-100">
                    {index + 1}
                  </div>
                  <div>
                    <p className="font-medium text-white">{item.title}</p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">{item.description}</p>
                    <p className="mt-2 text-[11px] leading-5 text-emerald-200">预期：{item.expectedResult}</p>
                    <p className="text-[11px] leading-5 text-slate-500">兜底：{item.fallbackNote}</p>
                  </div>
                  <ArrowRight className="hidden h-5 w-5 self-center text-slate-500 transition group-hover:text-cyan-100 md:block" />
                </Link>
              ))}
            </CardContent>
          </Card>

          <div className="space-y-4">
            <Card className="border-white/10 bg-white/[0.04]">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white">
                  <CheckCircle2 className="h-5 w-5 text-emerald-200" />
                  最近完整链路样例
                </CardTitle>
                <p className="text-xs text-slate-500">优先展示最新 Agent 审计回测样例；缺失时显示空状态。</p>
              </CardHeader>
              <CardContent>
                {latestSample ? (
                  <div className="space-y-4">
                    <div className="rounded-2xl border border-emerald-400/20 bg-emerald-500/10 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm text-emerald-100">{latestSample.symbol || "暂无标的"}</p>
                          <p className="mt-2 text-2xl font-semibold text-white">{executionModeLabel(latestSample.executionMode)}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            {latestSample.strategyType || "暂无策略"} · {latestSample.interval || "暂无周期"} · {formatTime(latestSample.createdAt)}
                          </p>
                        </div>
                        <Badge className={statusClass("done")}>可演示</Badge>
                      </div>
                    </div>
                    <div className="grid gap-2 text-xs sm:grid-cols-2">
                      {[
                        ["Backtest", latestSample.latestBacktestId],
                        ["Replay", latestSample.latestReplaySessionId],
                        ["Decision", latestSample.latestDecisionId],
                        ["OrderIntent", latestSample.latestOrderIntentId],
                        ["PaperOrder", latestSample.latestPaperOrderId],
                        ["Audit", latestSample.latestAuditRecordId],
                      ].map(([label, value]) => (
                        <div key={label} className="rounded-xl border border-white/10 bg-black/20 p-3">
                          <p className="text-slate-500">{label}</p>
                          <p className="mt-1 truncate font-mono text-slate-100">{value || "暂无关联记录"}</p>
                        </div>
                      ))}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <LinkButton href={latestSample.backtestDetailUrl || "/backtest"} label="查看回测详情" />
                      <LinkButton href={latestSample.replayUrl || "/replay"} label="查看历史回放" />
                      <LinkButton href={latestSample.decisionDetailUrl || "/decisions"} label="查看决策详情" />
                      <LinkButton href={latestSample.auditRecordUrl || "/audit"} label="查看审计记录" />
                    </div>
                  </div>
                ) : (
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-8 text-center text-sm text-slate-400">
                    暂无样例数据。可以先运行一次 Agent 审计回测，再回到这里查看完整链路。
                    <div className="mt-4">
                      <LinkButton href="/backtest" label="去回测台" />
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border-white/10 bg-white/[0.04]">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white">
                  <MonitorCog className="h-5 w-5 text-cyan-200" />
                  系统健康状态
                </CardTitle>
                <p className="text-xs text-slate-500">健康卡片复用系统监控能力，不为了首页重构后端。</p>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2">
                <HealthRow label="后端" value={health.backendHealth || "unknown"} />
                <HealthRow label="PostgreSQL" value={health.databaseStatus || "unknown"} />
                <HealthRow label="Redis" value={health.redisStatus || "unknown"} />
                <HealthRow label="ClickHouse" value={health.clickhouseStatus || "unknown"} />
                <HealthRow label="数据管道" value={health.ingestionStatus || "unknown"} />
                <HealthRow label="API 错误数" value={String(health.apiErrorCount ?? 0)} />
                <div className="sm:col-span-2 rounded-2xl border border-white/10 bg-black/20 p-3">
                  <p className="text-xs text-slate-500">前端构建状态</p>
                  <p className="mt-1 text-xs leading-5 text-slate-300">{health.frontendBuildStatus || "暂无数据"}</p>
                </div>
                <div className="sm:col-span-2 rounded-2xl border border-white/10 bg-black/20 p-3">
                  <p className="text-xs text-slate-500">最近检查</p>
                  <p className="mt-1 text-xs text-slate-300">{formatTime(health.lastSmokeTestTime)}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">{health.lastErrorSummary || "暂无明显错误"}</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>
      </main>
    </div>
  );
}

function LinkButton({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-cyan-400/20 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-100 transition hover:bg-cyan-500/20"
    >
      {label}
      <ExternalLink className="h-3.5 w-3.5" />
    </Link>
  );
}

function HealthRow({ label, value }: { label: string; value: string }) {
  const normalized = value === "0" ? "ok" : value;
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-slate-500">{label}</p>
        <Badge className={statusClass(normalized)}>{statusLabel(normalized)}</Badge>
      </div>
      <p className="mt-2 truncate font-mono text-xs text-slate-200">{value || "暂无数据"}</p>
    </div>
  );
}
