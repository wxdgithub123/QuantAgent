"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  Brain,
  Clock,
  Database,
  GitCompare,
  History,
  Layers,
  RefreshCw,
  Shield,
  ShieldCheck,
  TimerReset,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

type JsonRecord = Record<string, unknown>;

interface PrdModule {
  key: string;
  title: string;
  support_level: string;
  status: "ready" | "partial" | "todo" | string;
  description: string;
}

interface BacktestRow {
  id: number;
  strategy_type: string;
  symbol: string;
  interval: string;
  pit?: JsonRecord;
  total_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  total_trades: number;
  data_source?: string | null;
  created_at?: string | null;
}

interface ReplayRow {
  replay_session_id: string;
  strategy_type?: string | null;
  symbol: string;
  start_time?: string | null;
  end_time?: string | null;
  status: string;
  initial_capital: number;
  pnl: number;
  total_return: number;
  trade_count: number;
  equity_points: number;
  backtest_id?: number | null;
  created_at?: string | null;
}

interface AuditLogRow {
  id: number;
  action: string;
  user_id?: string | null;
  resource?: string | null;
  details: JsonRecord;
  created_at?: string | null;
}

interface DecisionRow {
  id: number;
  symbol: string;
  timestamp?: string | null;
  final_signal: string;
  confidence: number;
  risk_veto: boolean;
  summary: string;
  input_snapshot_ids: JsonRecord;
}

interface ComparisonCandidate {
  replay_session_id: string;
  symbol: string;
  strategy_type?: string | null;
  status: string;
  backtest_id?: number | null;
  candidate_backtest_id?: number | null;
  candidate_interval?: string | null;
  candidate_data_source?: string | null;
  candidate_initial_capital?: number | null;
  match_type?: string | null;
  match_label?: string | null;
  ready: boolean;
  strict?: boolean;
  needs_review?: boolean;
  created_at?: string | null;
}

interface PointInTimeInfo {
  rule: string;
  factor_snapshot_count: number;
  signal_event_count: number;
  backtest_count: number;
  reproducible_backtest_count?: number;
  symbol_count: number;
  min_available_time?: string | null;
  max_available_time?: string | null;
  sample_context_url: string;
}

interface NextAction {
  title: string;
  href: string;
  reason: string;
}

interface AuditOverview {
  generated_at: string;
  error?: string;
  counts: Record<string, number>;
  replay_status_counts: Record<string, number>;
  point_in_time?: PointInTimeInfo;
  modules: PrdModule[];
  latest_backtests: BacktestRow[];
  latest_replays: ReplayRow[];
  latest_audit_logs: AuditLogRow[];
  latest_decisions: DecisionRow[];
  comparison_candidates: ComparisonCandidate[];
  next_actions: NextAction[];
}

const NAV_LINKS = [
  { href: "/dashboard", label: "仪表盘", icon: BarChart3 },
  { href: "/data-sources", label: "数据源", icon: Database },
  { href: "/signals", label: "因子/信号", icon: Layers },
  { href: "/decisions", label: "决策中心", icon: Brain },
  { href: "/audit", label: "回测与审计", icon: Shield, active: true },
];

function readNumber(value: unknown, fallback = 0) {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function formatNumber(value: unknown) {
  return readNumber(value).toLocaleString("zh-CN");
}

function formatMoney(value: unknown) {
  return `$${readNumber(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}

function formatPercent(value: unknown) {
  return `${readNumber(value).toFixed(2)}%`;
}

function formatTime(value?: string | null) {
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

function shortId(value: string) {
  if (!value) return "-";
  return value.length > 14 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function moduleBadge(status: string) {
  if (status === "ready") return "border-emerald-400/30 bg-emerald-500/15 text-emerald-300";
  if (status === "partial") return "border-amber-400/30 bg-amber-500/15 text-amber-200";
  return "border-slate-400/20 bg-slate-500/15 text-slate-300";
}

function moduleLabel(status: string) {
  if (status === "ready") return "可使用";
  if (status === "partial") return "部分可用";
  if (status === "todo") return "待补齐";
  return status || "未知";
}

function replayBadge(status: string) {
  if (status === "completed") return "border-emerald-400/30 bg-emerald-500/15 text-emerald-300";
  if (status === "running") return "border-sky-400/30 bg-sky-500/15 text-sky-200";
  if (status === "failed") return "border-rose-400/30 bg-rose-500/15 text-rose-300";
  return "border-amber-400/30 bg-amber-500/15 text-amber-200";
}

function replayLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "running") return "运行中";
  if (status === "pending") return "待启动";
  if (status === "failed") return "失败";
  if (status === "paused") return "已暂停";
  return status || "未知";
}

function comparisonBadge(item: ComparisonCandidate) {
  if (item.strict) return "border-emerald-400/30 bg-emerald-500/15 text-emerald-300";
  if (item.ready) return "border-cyan-400/30 bg-cyan-500/15 text-cyan-200";
  if (item.needs_review) return "border-amber-400/30 bg-amber-500/15 text-amber-200";
  return "border-slate-400/20 bg-slate-500/15 text-slate-300";
}

function comparisonLabel(item: ComparisonCandidate) {
  if (item.strict) return "严格可比";
  if (item.ready) return "可对比";
  if (item.needs_review) return "候选参考";
  return "还不能对比";
}

function signalLabel(signal: string) {
  const normalized = signal.toUpperCase();
  if (normalized === "BUY") return "买入";
  if (normalized === "SELL") return "卖出";
  if (normalized === "HOLD") return "持有";
  return "观望";
}

function signalClass(signal: string) {
  const normalized = signal.toUpperCase();
  if (normalized === "BUY") return "text-emerald-300";
  if (normalized === "SELL") return "text-rose-300";
  return "text-slate-300";
}

function snapshotCount(snapshot: JsonRecord, key: string) {
  const value = snapshot[key];
  return Array.isArray(value) ? value.length : 0;
}

function pitAsOfTime(pit?: JsonRecord) {
  const value = pit?.as_of_time;
  return typeof value === "string" ? value : null;
}

function readString(value: unknown, fallback = "暂无") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function pitString(pit: JsonRecord | undefined, key: string, fallback = "暂无") {
  return readString(pit?.[key], fallback);
}

function backtestSourceLabel(source?: string | null) {
  if (source === "QUICK_BACKTEST") return "快速回测";
  if (source === "REPLAY_COMPARE") return "回放对比回测";
  if (source === "BACKTEST") return "普通回测";
  return source || "普通回测";
}

function dataReadSourceLabel(source: string) {
  if (source === "clickhouse:klines") return "ClickHouse K线缓存";
  if (source === "market_data_gateway") return "主数据网关";
  if (source === "market_data_gateway:fallback") return "主数据网关兜底";
  return source;
}

function pitWindowText(pit?: JsonRecord) {
  const start = pitString(pit, "actual_start_time", "");
  const end = pitString(pit, "actual_end_time", "");
  if (!start && !end) return "暂无";
  return `${formatTime(start)} 到 ${formatTime(end)}`;
}

function shortHash(value: unknown) {
  const text = typeof value === "string" ? value : "";
  if (!text) return "暂无";
  return text.length > 14 ? `${text.slice(0, 8)}...${text.slice(-6)}` : text;
}

function StatusCard({
  title,
  value,
  hint,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  hint: string;
  icon: typeof Shield;
}) {
  return (
    <Card className="border-white/10 bg-white/[0.04] shadow-xl">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm text-slate-400">{title}</p>
            <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
            <p className="mt-2 text-xs leading-5 text-slate-500">{hint}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/10 p-3">
            <Icon className="h-5 w-5 text-cyan-200" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function AuditPage() {
  const [overview, setOverview] = useState<AuditOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchOverview = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/v1/audit/overview", { cache: "no-store" });
      const data = (await response.json()) as AuditOverview;
      if (!response.ok || data.error) {
        throw new Error(data.error || "回测与审计概览加载失败");
      }
      setOverview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchOverview();
  }, [fetchOverview]);

  const counts = overview?.counts || {};
  const pit = overview?.point_in_time;
  const readyComparisons = useMemo(
    () => (overview?.comparison_candidates || []).filter((item) => item.ready).length,
    [overview?.comparison_candidates],
  );
  const strictComparisons = readNumber(counts.strict_comparison_ready || counts.comparison_ready);

  return (
    <div className="min-h-screen bg-[#070b12] text-slate-100">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#070b12]/85 backdrop-blur-xl">
        <div className="container mx-auto flex items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="rounded-xl border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div>
              <h1 className="text-lg font-semibold text-white">回测与审计</h1>
              <p className="text-xs text-slate-500">查看 PRD 10.5 闭环能力的真实数据状态</p>
            </div>
          </div>

          <nav className="hidden items-center gap-1 md:flex">
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
            onClick={() => void fetchOverview()}
          >
            <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
            刷新
          </Button>
        </div>
      </header>

      <main className="container mx-auto space-y-6 px-4 py-6">
        <section className="overflow-hidden rounded-3xl border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.22),transparent_36%),linear-gradient(135deg,rgba(15,23,42,0.96),rgba(2,6,23,0.96))] p-6 shadow-2xl">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <Badge className="border-cyan-400/30 bg-cyan-500/15 text-cyan-100">PRD 10.5 工作台</Badge>
              <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white">把“能回测、能回放、能追溯、能对比”放到同一个页面</h2>
              <p className="mt-3 text-sm leading-7 text-slate-300">
                这里展示的是数据库和接口里的真实状态：已有记录会直接列出来；如果某一步还缺完整样例，会提示应该去哪个页面继续跑，而不是把后端能力写成已经完全可用。
              </p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-slate-300">
              <div className="flex items-center gap-2 text-slate-400">
                <Clock className="h-4 w-4" />
                最近刷新
              </div>
              <div className="mt-2 text-lg font-semibold text-white">{formatTime(overview?.generated_at)}</div>
            </div>
          </div>
        </section>

        {error && (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
            {error}
          </div>
        )}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatusCard
            title="回测结果"
            value={formatNumber(counts.backtest_results)}
            hint="来自 backtest_results，用于策略结果复查和后续对比。"
            icon={BarChart3}
          />
          <StatusCard
            title="历史回放"
            value={`${formatNumber(counts.completed_replays)} / ${formatNumber(counts.replay_sessions)}`}
            hint="前面是已完成会话，后面是全部 replay_sessions。"
            icon={History}
          />
          <StatusCard
            title="审计与决策"
            value={`${formatNumber(counts.audit_logs)} + ${formatNumber(counts.coordination_history)}`}
            hint="audit_logs 记录操作，coordination_history 记录智能体决策。"
            icon={ShieldCheck}
          />
          <StatusCard
            title="可直接对比"
            value={formatNumber(strictComparisons || readyComparisons)}
            hint="只统计 completed 回放，并且已经明确关联到回测结果的样例。"
            icon={GitCompare}
          />
        </section>

        <section className="grid gap-4 lg:grid-cols-4">
          {(overview?.modules || []).map((item) => (
            <Card key={item.key} className="border-white/10 bg-white/[0.04]">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <CardTitle className="text-base text-white">{item.title}</CardTitle>
                  <Badge className={moduleBadge(item.status)}>{moduleLabel(item.status)}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-slate-300">
                <p className="font-medium text-cyan-100">{item.support_level}</p>
                <p className="leading-6 text-slate-400">{item.description}</p>
              </CardContent>
            </Card>
          ))}
        </section>

        <section className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <TimerReset className="h-5 w-5 text-cyan-200" />
                Point-in-time 输入规则
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 text-sm text-slate-300 md:grid-cols-3">
              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <p className="text-slate-500">取数规则</p>
                <p className="mt-2 font-mono text-cyan-100">{pit?.rule || "available_time <= as_of_time"}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <p className="text-slate-500">PIT 因子 / 信号 / 回测</p>
                <p className="mt-2 text-lg font-semibold text-white">
                  {formatNumber(pit?.factor_snapshot_count)} / {formatNumber(pit?.signal_event_count)} / {formatNumber(pit?.backtest_count)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  其中完整复现包：{formatNumber(pit?.reproducible_backtest_count)} 条
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <p className="text-slate-500">覆盖标的与时间</p>
                <p className="mt-2 text-white">{formatNumber(pit?.symbol_count)} 个标的</p>
                <p className="mt-1 text-xs text-slate-500">{formatTime(pit?.min_available_time)} 到 {formatTime(pit?.max_available_time)}</p>
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Activity className="h-5 w-5 text-emerald-200" />
                下一步动作
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {(overview?.next_actions || []).map((action) => (
                <Link
                  key={action.title}
                  href={action.href}
                  className="block rounded-2xl border border-white/10 bg-black/20 p-4 transition hover:border-cyan-400/30 hover:bg-cyan-500/10"
                >
                  <p className="font-medium text-white">{action.title}</p>
                  <p className="mt-1 text-sm leading-6 text-slate-400">{action.reason}</p>
                </Link>
              ))}
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-white">最近回测结果</CardTitle>
              <Link href="/backtest">
                <Button size="sm" variant="ghost" className="text-cyan-100 hover:bg-cyan-500/10">去回测</Button>
              </Link>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow className="border-white/10 hover:bg-transparent">
                    <TableHead className="text-slate-400">时间</TableHead>
                    <TableHead className="text-slate-400">标的/策略</TableHead>
                    <TableHead className="text-slate-400">收益</TableHead>
                    <TableHead className="text-slate-400">交易</TableHead>
                    <TableHead className="text-slate-400">来源说明</TableHead>
                    <TableHead className="text-slate-400">PIT</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(overview?.latest_backtests || []).map((row) => (
                    <TableRow key={row.id} className="border-white/10">
                      <TableCell className="text-slate-400">{formatTime(row.created_at)}</TableCell>
                      <TableCell>
                        <div className="font-medium text-white">{row.symbol} · {row.interval}</div>
                        <div className="text-xs text-slate-500">{row.strategy_type} · ID {row.id}</div>
                      </TableCell>
                      <TableCell>
                        <div className={readNumber(row.total_return) >= 0 ? "text-emerald-300" : "text-rose-300"}>{formatPercent(row.total_return)}</div>
                        <div className="text-xs text-slate-500">回撤 {formatPercent(row.max_drawdown)}</div>
                      </TableCell>
                      <TableCell className="text-slate-300">{formatNumber(row.total_trades)}</TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <Badge className="border-slate-400/20 bg-slate-500/15 text-slate-300">
                            {backtestSourceLabel(row.data_source)}
                          </Badge>
                          <div className="text-xs leading-5 text-slate-500">
                            读取：{dataReadSourceLabel(pitString(row.pit, "data_source", "旧记录未保存"))}
                          </div>
                          {row.pit?.enabled && (
                            <div className="text-xs leading-5 text-slate-600">
                              实际窗口：{pitWindowText(row.pit)}
                            </div>
                          )}
                          {row.pit?.source_snapshot_id && (
                            <div className="text-xs leading-5 text-slate-600">
                              快照ID：{shortHash(row.pit.source_snapshot_id)}
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {row.pit?.enabled ? (
                          <div className="space-y-1">
                            <Badge className="border-cyan-400/30 bg-cyan-500/15 text-cyan-200">已记录</Badge>
                            <div className="text-xs text-slate-500">截止：{formatTime(pitAsOfTime(row.pit))}</div>
                            <div className="text-xs text-slate-600">K线：{formatNumber(row.pit.row_count)} 根</div>
                            <div className="text-xs text-slate-600">参数：{shortHash(row.pit.params_hash)}</div>
                            <div className="text-xs text-slate-600">策略：{pitString(row.pit, "strategy_version")}</div>
                            <div className="text-xs text-slate-600">引擎：{pitString(row.pit, "engine_version")}</div>
                          </div>
                        ) : (
                          <Badge className="border-slate-400/20 bg-slate-500/15 text-slate-400">旧记录</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {!loading && !overview?.latest_backtests?.length && (
                    <TableRow className="border-white/10">
                      <TableCell colSpan={6} className="py-8 text-center text-slate-500">还没有回测记录，先去“回测”页面跑一个策略。</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-white">历史回放会话</CardTitle>
              <Link href="/replay">
                <Button size="sm" variant="ghost" className="text-cyan-100 hover:bg-cyan-500/10">去回放</Button>
              </Link>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow className="border-white/10 hover:bg-transparent">
                    <TableHead className="text-slate-400">状态</TableHead>
                    <TableHead className="text-slate-400">会话</TableHead>
                    <TableHead className="text-slate-400">盈亏</TableHead>
                    <TableHead className="text-slate-400">数据点</TableHead>
                    <TableHead className="text-slate-400">对比</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(overview?.latest_replays || []).map((row) => (
                    <TableRow key={row.replay_session_id} className="border-white/10">
                      <TableCell><Badge className={replayBadge(row.status)}>{replayLabel(row.status)}</Badge></TableCell>
                      <TableCell>
                        <div className="font-medium text-white">{row.symbol} · {row.strategy_type || "未记录策略"}</div>
                        <div className="text-xs text-slate-500">{shortId(row.replay_session_id)}</div>
                        <div className="text-xs text-slate-600">{formatTime(row.start_time)} 到 {formatTime(row.end_time)}</div>
                      </TableCell>
                      <TableCell>
                        <div className={readNumber(row.pnl) >= 0 ? "text-emerald-300" : "text-rose-300"}>{formatMoney(row.pnl)}</div>
                        <div className="text-xs text-slate-500">{formatPercent(row.total_return)}</div>
                      </TableCell>
                      <TableCell className="text-slate-300">
                        {formatNumber(row.trade_count)} 笔
                        <div className="text-xs text-slate-500">{formatNumber(row.equity_points)} 个权益点</div>
                      </TableCell>
                      <TableCell>
                        {row.backtest_id ? (
                          <Badge className="border-emerald-400/30 bg-emerald-500/15 text-emerald-300">回测 #{row.backtest_id}</Badge>
                        ) : (
                          <Badge className="border-amber-400/30 bg-amber-500/15 text-amber-200">待匹配</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {!loading && !overview?.latest_replays?.length && (
                    <TableRow className="border-white/10">
                      <TableCell colSpan={5} className="py-8 text-center text-slate-500">还没有历史回放会话，先创建并启动一个回放。</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="text-white">结果对比样例</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {(overview?.comparison_candidates || []).map((item) => (
                <div key={item.replay_session_id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-white">{item.symbol} · {item.strategy_type || "未记录策略"}</p>
                      <p className="mt-1 text-xs text-slate-500">{shortId(item.replay_session_id)}</p>
                    </div>
                    <Badge className={comparisonBadge(item)}>
                      {comparisonLabel(item)}
                    </Badge>
                  </div>
                  <div className="mt-3 grid gap-2 text-sm text-slate-400 sm:grid-cols-2">
                    <p>回放状态：{replayLabel(item.status)}</p>
                    <p>匹配方式：{item.match_label || "未知"}</p>
                    <p>回测记录：{item.candidate_backtest_id ? `#${item.candidate_backtest_id}` : "暂无"}</p>
                    <p>回测周期：{item.candidate_interval || "暂无"}</p>
                    <p>回测来源：{item.candidate_data_source || "暂无"}</p>
                    <p>初始资金：{item.candidate_initial_capital ? formatMoney(item.candidate_initial_capital) : "暂无"}</p>
                  </div>
                  {item.needs_review && (
                    <p className="mt-3 rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs leading-5 text-amber-100">
                      这是候选参考，不是严格关联。可能只是同币种、同策略，但周期、初始资金或参数不完全一致，不能当成最终结论。
                    </p>
                  )}
                  {item.ready && (
                    <Link
                      href={`/analytics?replay_session_id=${encodeURIComponent(item.replay_session_id)}${item.candidate_backtest_id ? `&backtest_id=${item.candidate_backtest_id}` : ""}`}
                      className="mt-3 inline-flex text-sm text-cyan-200 hover:text-cyan-100"
                    >
                      打开对比分析
                    </Link>
                  )}
                </div>
              ))}
              {!loading && !overview?.comparison_candidates?.length && (
                <div className="rounded-2xl border border-white/10 bg-black/20 p-8 text-center text-sm text-slate-500">还没有可检查的回放会话。</div>
              )}
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-white">最近智能体决策</CardTitle>
              <Link href="/decisions">
                <Button size="sm" variant="ghost" className="text-cyan-100 hover:bg-cyan-500/10">去决策中心</Button>
              </Link>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow className="border-white/10 hover:bg-transparent">
                    <TableHead className="text-slate-400">时间</TableHead>
                    <TableHead className="text-slate-400">标的</TableHead>
                    <TableHead className="text-slate-400">建议</TableHead>
                    <TableHead className="text-slate-400">材料</TableHead>
                    <TableHead className="text-slate-400">摘要</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(overview?.latest_decisions || []).map((row) => (
                    <TableRow key={row.id} className="border-white/10">
                      <TableCell className="text-slate-400">{formatTime(row.timestamp)}</TableCell>
                      <TableCell className="font-medium text-white">{row.symbol}</TableCell>
                      <TableCell>
                        <div className={cn("font-medium", signalClass(row.final_signal))}>{signalLabel(row.final_signal)}</div>
                        <div className="text-xs text-slate-500">置信度 {(row.confidence * 100).toFixed(1)}%</div>
                      </TableCell>
                      <TableCell className="text-xs text-slate-400">
                        因子 {snapshotCount(row.input_snapshot_ids, "factor_ids")}
                        <br />
                        信号 {snapshotCount(row.input_snapshot_ids, "signal_ids")}
                      </TableCell>
                      <TableCell className="max-w-[260px] truncate text-slate-400">{row.summary || "暂无摘要"}</TableCell>
                    </TableRow>
                  ))}
                  {!loading && !overview?.latest_decisions?.length && (
                    <TableRow className="border-white/10">
                      <TableCell colSpan={5} className="py-8 text-center text-slate-500">还没有智能体决策记录。</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>

        <Card className="border-white/10 bg-white/[0.04]">
          <CardHeader>
            <CardTitle className="text-white">最近审计日志</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow className="border-white/10 hover:bg-transparent">
                  <TableHead className="text-slate-400">时间</TableHead>
                  <TableHead className="text-slate-400">动作</TableHead>
                  <TableHead className="text-slate-400">对象</TableHead>
                  <TableHead className="text-slate-400">用户</TableHead>
                  <TableHead className="text-slate-400">详情</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(overview?.latest_audit_logs || []).map((row) => (
                  <TableRow key={row.id} className="border-white/10">
                    <TableCell className="text-slate-400">{formatTime(row.created_at)}</TableCell>
                    <TableCell><Badge className="border-slate-400/20 bg-slate-500/15 text-slate-300">{row.action}</Badge></TableCell>
                    <TableCell className="text-white">{row.resource || "未记录"}</TableCell>
                    <TableCell className="text-slate-300">{row.user_id || "system"}</TableCell>
                    <TableCell className="max-w-[520px] truncate font-mono text-xs text-slate-500">{JSON.stringify(row.details || {})}</TableCell>
                  </TableRow>
                ))}
                {!loading && !overview?.latest_audit_logs?.length && (
                  <TableRow className="border-white/10">
                    <TableCell colSpan={5} className="py-8 text-center text-slate-500">还没有审计日志。后续配置修改、关键操作和策略动作需要继续写入 audit_logs。</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {loading && (
          <div className="fixed bottom-6 right-6 rounded-full border border-white/10 bg-black/60 px-4 py-2 text-sm text-slate-300 shadow-xl backdrop-blur">
            <RefreshCw className="mr-2 inline h-4 w-4 animate-spin" />
            正在加载真实数据
          </div>
        )}
      </main>
    </div>
  );
}
