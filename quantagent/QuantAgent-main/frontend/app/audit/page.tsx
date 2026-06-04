"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Activity,
  BarChart3,
  Clock,
  GitCompare,
  History,
  RefreshCw,
  Shield,
  ShieldCheck,
  TimerReset,
} from "lucide-react";

import { AppTopNav } from "@/components/navigation/AppTopNav";
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

interface PitView {
  enabled: boolean;
  sourceSnapshotId: string;
  rowCount: number;
  paramsHash: string;
}

interface ReplayRow {
  replay_session_id: string;
  strategy_type?: string | null;
  symbol: string;
  start_time?: string | null;
  end_time?: string | null;
  current_timestamp?: string | null;
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

type OrderIntentAuditRow = AuditLogRow;

interface StandardAuditRecord {
  id: number | null;
  eventType: string;
  symbol?: string | null;
  asOfTime?: string | null;
  snapshotId?: unknown;
  decisionId?: number | string | null;
  orderIntentId?: string | null;
  orderId?: string | null;
  action?: string | null;
  executionStatus?: string | null;
  riskStatus?: string | null;
  source?: string | null;
  inputSummary?: unknown;
  agentOutputs?: unknown;
  riskCheckResult?: JsonRecord;
  executionResult?: JsonRecord;
  backtestId?: number | string | null;
  replaySessionId?: string | null;
  executionMode?: string | null;
  replayTime?: string | null;
  createdAt?: string | null;
  immutable: boolean;
  raw?: JsonRecord;
  synthetic?: boolean;
}

interface AuditRecordsResponse {
  schema_version: string;
  generated_at: string;
  immutability_note: string;
  data: StandardAuditRecord[];
  total: number;
  limit: number;
  offset: number;
}

interface AuditRecordDetailResponse {
  audit_record: StandardAuditRecord;
}

interface AuditFilters {
  symbol: string;
  eventType: string;
  action: string;
  executionStatus: string;
  riskStatus: string;
  source: string;
  decisionId: string;
  orderIntentId: string;
  orderId: string;
  backtestId: string;
  replaySessionId: string;
  executionMode: string;
  startTime: string;
  endTime: string;
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

interface RoleOutput {
  role?: string;
  agent_type?: string;
  agent?: string;
  opinion?: string;
  signal?: string;
  confidence?: number;
  reasoning?: string;
  key_points?: string[];
  risk_flag?: boolean;
}

interface TradingAgentsChainEntry {
  index?: number;
  phase?: string;
  role?: string;
  label?: string;
  opinion?: string;
  confidence?: number;
  available?: boolean;
  reasoning?: string;
}

interface DecisionAuditDetail {
  schema_version: string;
  generated_at: string;
  immutability_note: string;
  decision: DecisionRow & {
    vote_breakdown?: JsonRecord;
    agent_signals?: RoleOutput[];
    bull_view?: string;
    bear_view?: string;
    role_opinions?: RoleOutput[];
    position_advice?: JsonRecord;
    risk_notes?: string;
    created_at?: string | null;
  };
  trace_summary: {
    input_snapshot_id_groups: number;
    factor_snapshots: number;
    signal_events: number;
    news_events: number;
    macro_events: number;
    role_outputs: number;
    order_intent_events: number;
    paper_trades: number;
    risk_blocked: boolean;
    executed: boolean;
  };
  role_outputs: RoleOutput[];
  order_intent_events: OrderIntentAuditRow[];
  paper_trades: Array<{
    id: number;
    client_order_id?: string | null;
    symbol: string;
    exchange_id?: string | null;
    side: string;
    order_type: string;
    quantity: number;
    price: number;
    benchmark_price?: number;
    fee?: number;
    funding_fee?: number;
    pnl?: number;
    status: string;
    mode?: string | null;
    session_id?: string | null;
    data_source?: string | null;
    created_at?: string | null;
  }>;
  links: {
    research_snapshot?: string;
    decision_center?: string;
    audit_export?: string | null;
  };
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
  latest_order_intents: OrderIntentAuditRow[];
  latest_decisions: DecisionRow[];
  comparison_candidates: ComparisonCandidate[];
  next_actions: NextAction[];
}

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

function formatRatioPercent(value: unknown) {
  return `${(readNumber(value) * 100).toFixed(1)}%`;
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

function roleLabel(role?: string) {
  if (!role) return "未标注角色";
  if (role === "tradingagents_openai_decision") return "TradingAgents 模型裁决";
  if (role === "tradingagents_context_adapter") return "TradingAgents 上下文基线";
  if (role === "tradingagents_quantagent_market") return "QuantAgent 市场结构分析";
  if (role === "tradingagents_quantagent_sentiment") return "QuantAgent 新闻情绪分析";
  if (role === "tradingagents_quantagent_news") return "QuantAgent 新闻/宏观分析";
  if (role === "tradingagents_quantagent_context") return "QuantAgent 加密上下文分析";
  if (role === "tradingagents_quantagent_situation") return "QuantAgent 情景摘要";
  if (role === "tradingagents_quantagent_trader") return "QuantAgent 交易员";
  if (role === "tradingagents_quantagent_final_judge") return "QuantAgent 最终裁决";
  if (role === "technical") return "技术分析师";
  if (role === "news") return "新闻分析师";
  if (role === "macro") return "宏观分析师";
  if (role === "risk") return "风险管理员";
  if (role.startsWith("tradingagents_native_")) return `原版实验：${role.replace("tradingagents_native_", "")}`;
  return role;
}

function roleOpinionLabel(role: RoleOutput) {
  return readString(role.opinion || role.signal, "未给出方向");
}

function snapshotCount(snapshot: JsonRecord, key: string) {
  const value = snapshot[key];
  return Array.isArray(value) ? value.length : 0;
}

function snapshotCountAny(snapshot: JsonRecord, keys: string[]) {
  for (const key of keys) {
    const count = snapshotCount(snapshot, key);
    if (count > 0) return count;
  }
  return 0;
}

function jsonObject(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function nestedObject(source: JsonRecord | undefined, key: string) {
  return jsonObject(source?.[key]);
}

function orderIntentActionLabel(action: string) {
  if (action === "AGENT_DECISION") return "Agent 决策";
  if (action === "ORDER_INTENT_CREATED") return "交易意图已创建";
  if (action === "RISK_CHECK_PASSED") return "风控通过";
  if (action === "RISK_BLOCKED") return "风控拦截";
  if (action === "PAPER_ORDER_FILLED") return "模拟成交";
  if (action === "PAPER_ORDER_REJECTED") return "模拟订单拒绝";
  if (action === "POSITION_UPDATED") return "持仓已更新";
  if (action === "PNL_UPDATED") return "盈亏已更新";
  if (action === "HOLD_RECORDED") return "观望已留痕";
  if (action === "ORDER_INTENT_NOOP") return "不下单";
  if (action === "ORDER_INTENT_PREVIEW") return "已预览";
  if (action === "ORDER_INTENT_BLOCKED") return "风控拦截";
  if (action === "ORDER_INTENT_EXECUTED") return "模拟盘已执行";
  return action;
}

function orderIntentBadge(action: string) {
  if (action === "PAPER_ORDER_FILLED" || action === "ORDER_INTENT_EXECUTED" || action === "RISK_CHECK_PASSED") return "border-emerald-400/30 bg-emerald-500/15 text-emerald-300";
  if (action === "RISK_BLOCKED" || action === "PAPER_ORDER_REJECTED" || action === "ORDER_INTENT_BLOCKED") return "border-rose-400/30 bg-rose-500/15 text-rose-300";
  if (action === "ORDER_INTENT_CREATED" || action === "ORDER_INTENT_PREVIEW") return "border-cyan-400/30 bg-cyan-500/15 text-cyan-200";
  if (action === "AGENT_DECISION") return "border-fuchsia-400/30 bg-fuchsia-500/15 text-fuchsia-200";
  if (action === "HOLD_RECORDED") return "border-slate-400/30 bg-slate-500/15 text-slate-200";
  return "border-slate-400/20 bg-slate-500/15 text-slate-300";
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

function pitView(pit?: JsonRecord): PitView {
  return {
    enabled: pit?.enabled === true,
    sourceSnapshotId: readString(pit?.source_snapshot_id, ""),
    rowCount: readNumber(pit?.row_count),
    paramsHash: readString(pit?.params_hash, ""),
  };
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

function auditExportHref(id: number) {
  return `/api/v1/audit/records/${id}/export`;
}

function tradingAgentsInternalChain(detail: DecisionAuditDetail | null): TradingAgentsChainEntry[] {
  const positionAdvice = detail?.decision.position_advice;
  const chain = positionAdvice?.tradingagents_internal_chain;
  return Array.isArray(chain) ? (chain as TradingAgentsChainEntry[]) : [];
}

function auditResultLines(detail: DecisionAuditDetail) {
  const materialCount = detail.trace_summary.factor_snapshots
    + detail.trace_summary.signal_events
    + detail.trace_summary.news_events
    + detail.trace_summary.macro_events;
  const chainCount = tradingAgentsInternalChain(detail).length;
  const executionText = detail.trace_summary.executed
    ? "已生成并执行到模拟盘成交记录"
    : detail.trace_summary.risk_blocked
      ? "已生成执行意图，但被风控拦截"
      : detail.trace_summary.order_intent_events > 0
        ? "已有 OrderIntent / 风控留痕，尚未进入模拟盘成交"
        : "仅完成决策审计，尚未生成执行意图";
  return [
    `结论：${detail.decision.symbol} 本次最终建议为 ${signalLabel(detail.decision.final_signal)}，置信度 ${formatRatioPercent(detail.decision.confidence)}。`,
    `输入材料：本次审计追踪到 ${formatNumber(materialCount)} 条材料，包括因子、信号、新闻和宏观事件。`,
    `智能体链路：核心角色输出 ${formatNumber(detail.trace_summary.role_outputs)} 个，完整 TradingAgentsGraph 内部链路 ${formatNumber(chainCount)} 个节点。`,
    `执行链路：${executionText}。`,
    `留痕状态：页面已直接展示摘要、角色输出、输入快照、OrderIntent、风控与模拟盘记录；JSON 导出只作为复核和归档。`,
  ];
}

function researchSnapshotHref(symbol: string, interval?: string | null, asOfTime?: string | null) {
  const params = new URLSearchParams({
    symbol,
    interval: interval || "1h",
  });
  if (asOfTime) params.set("as_of_time", asOfTime);
  return `/dashboard?${params.toString()}`;
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

function friendlyAuditError(error: unknown, fallback = "数据暂不可用，已展示缓存数据 / 暂无数据。") {
  const raw = error instanceof Error ? error.message : String(error || "");
  const lower = raw.toLowerCase();
  if (!raw || lower.includes("failed to fetch") || lower.includes("timeout") || lower.includes("abort") || lower.includes("http 5")) {
    return fallback;
  }
  return raw.length > 120 ? fallback : raw;
}

function fetchWithTimeout(url: string, timeoutMs = 15000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { cache: "no-store", signal: controller.signal }).finally(() => clearTimeout(timeout));
}

function AuditPageContent() {
  const searchParams = useSearchParams();
  const [overview, setOverview] = useState<AuditOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedDecisionId, setSelectedDecisionId] = useState<number | null>(null);
  const [decisionDetail, setDecisionDetail] = useState<DecisionAuditDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [auditRecords, setAuditRecords] = useState<StandardAuditRecord[]>([]);
  const [auditRecordsLoading, setAuditRecordsLoading] = useState(false);
  const [auditRecordsError, setAuditRecordsError] = useState("");
  const [auditFilters, setAuditFilters] = useState<AuditFilters>({
    symbol: "",
    eventType: "",
    action: "",
    executionStatus: "",
    riskStatus: "",
    source: "",
    decisionId: "",
    orderIntentId: "",
    orderId: "",
    backtestId: "",
    replaySessionId: "",
    executionMode: "",
    startTime: "",
    endTime: "",
  });
  const [selectedAuditRecord, setSelectedAuditRecord] = useState<StandardAuditRecord | null>(null);
  const [auditRecordDetailLoading, setAuditRecordDetailLoading] = useState(false);
  const [copyMessage, setCopyMessage] = useState("");

  const fetchOverview = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetchWithTimeout("/api/v1/audit/overview");
      const data = (await response.json()) as AuditOverview;
      if (!response.ok || data.error) {
        throw new Error(data.error || "回测与审计概览加载失败");
      }
      setOverview(data);
    } catch (err) {
      setError(friendlyAuditError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchOverview();
  }, [fetchOverview]);

  const fetchAuditRecords = useCallback(async () => {
    setAuditRecordsLoading(true);
    setAuditRecordsError("");
    const params = new URLSearchParams({ limit: "50" });
    Object.entries(auditFilters).forEach(([key, value]) => {
      if (!value) return;
      if (key === "startTime" || key === "endTime") {
        params.set(key, new Date(value).toISOString());
      } else {
        params.set(key, value);
      }
    });
    try {
      const response = await fetchWithTimeout(`/api/v1/audit/records?${params.toString()}`, 20000);
      const data = (await response.json()) as AuditRecordsResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(data.detail || "审计记录加载失败");
      }
      setAuditRecords(Array.isArray(data.data) ? data.data : []);
      setSelectedAuditRecord((current) => current || data.data?.[0] || null);
    } catch (err) {
      setAuditRecords([]);
      setAuditRecordsError(friendlyAuditError(err, "数据暂不可用，暂无审计记录。"));
    } finally {
      setAuditRecordsLoading(false);
    }
  }, [auditFilters]);

  useEffect(() => {
    void fetchAuditRecords();
  }, [fetchAuditRecords]);

  const updateAuditFilter = useCallback((key: keyof AuditFilters, value: string) => {
    setAuditFilters((current) => ({ ...current, [key]: value }));
  }, []);

  const fetchAuditRecordDetail = useCallback(async (record: StandardAuditRecord) => {
    if (!record.id) {
      setSelectedAuditRecord(record);
      return;
    }
    setAuditRecordDetailLoading(true);
    setCopyMessage("");
    try {
      const response = await fetchWithTimeout(`/api/v1/audit/records/${record.id}`, 15000);
      const data = (await response.json()) as AuditRecordDetailResponse & { detail?: string };
      if (!response.ok) throw new Error(data.detail || "审计详情加载失败");
      setSelectedAuditRecord(data.audit_record);
    } catch (err) {
      setAuditRecordsError(friendlyAuditError(err, "数据暂不可用，暂无审计详情。"));
      setSelectedAuditRecord(record);
    } finally {
      setAuditRecordDetailLoading(false);
    }
  }, []);

  const copyAuditJson = useCallback(async () => {
    if (!selectedAuditRecord) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(selectedAuditRecord, null, 2));
      setCopyMessage("已复制 JSON");
    } catch {
      setCopyMessage("复制失败，可以手动选中 JSON 内容");
    }
  }, [selectedAuditRecord]);

  const fetchDecisionDetail = useCallback(async (decisionId: number) => {
    setSelectedDecisionId(decisionId);
    setDetailLoading(true);
    setDetailError("");
    try {
      const response = await fetchWithTimeout(`/api/v1/audit/decisions/${decisionId}`);
      const data = (await response.json()) as DecisionAuditDetail & { detail?: string };
      if (!response.ok) {
        throw new Error(data.detail || "决策审计详情加载失败");
      }
      setDecisionDetail(data);
    } catch (err) {
      setDecisionDetail(null);
      setDetailError(friendlyAuditError(err, "数据暂不可用，暂无决策审计详情。"));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const counts = overview?.counts || {};
  const pit = overview?.point_in_time;
  const decisionParam = searchParams.get("decision_id");
  const orderIdParam = searchParams.get("order_id");
  const orderIntentParam = searchParams.get("order_intent_id");
  const auditIdParam = searchParams.get("audit_id");
  const backtestParam = searchParams.get("backtest_id");
  const replaySessionParam = searchParams.get("replay_session_id") || searchParams.get("session_id");
  const readyComparisons = useMemo(
    () => (overview?.comparison_candidates || []).filter((item) => item.ready).length,
    [overview?.comparison_candidates],
  );
  const strictComparisons = readNumber(counts.strict_comparison_ready || counts.comparison_ready);

  useEffect(() => {
    const decisionId = Number(decisionParam);
    if (Number.isFinite(decisionId) && decisionId > 0 && selectedDecisionId !== decisionId) {
      void fetchDecisionDetail(decisionId);
    }
  }, [decisionParam, fetchDecisionDetail, selectedDecisionId]);

  useEffect(() => {
    if (!decisionParam && !orderIdParam && !orderIntentParam && !backtestParam && !replaySessionParam) return;
    setAuditFilters((current) => ({
      ...current,
      decisionId: decisionParam || current.decisionId,
      orderId: orderIdParam || current.orderId,
      orderIntentId: orderIntentParam || current.orderIntentId,
      backtestId: backtestParam || current.backtestId,
      replaySessionId: replaySessionParam || current.replaySessionId,
    }));
  }, [backtestParam, decisionParam, orderIdParam, orderIntentParam, replaySessionParam]);

  useEffect(() => {
    const auditId = Number(auditIdParam);
    if (!Number.isFinite(auditId) || auditId <= 0) return;
    void fetchAuditRecordDetail({
      id: auditId,
      eventType: "AUDIT_RECORDED",
      immutable: true,
    });
  }, [auditIdParam, fetchAuditRecordDetail]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppTopNav
        activeSection="audit"
        title="回测与审计"
        subtitle="PIT 回测、决策回放、执行闭环和审计导出"
        rightSlot={
          <Button
            size="sm"
            variant="outline"
            className="border-white/10 bg-white/5 text-slate-100 hover:bg-white/10"
            onClick={() => void fetchOverview()}
          >
            <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
            刷新
          </Button>
        }
      />

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
            title="执行闭环事件"
            value={formatNumber(counts.order_intent_events)}
            hint="TradingAgents 建议生成 OrderIntent、风控检查和模拟盘执行的审计事件。"
            icon={Shield}
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
                  {(overview?.latest_backtests || []).map((row) => {
                    const pitMeta = pitView(row.pit);
                    return (
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
                          {pitMeta.enabled && (
                            <div className="text-xs leading-5 text-slate-600">
                              实际窗口：{pitWindowText(row.pit)}
                            </div>
                          )}
                          {pitMeta.sourceSnapshotId && (
                            <div className="text-xs leading-5 text-slate-600">
                              快照ID：{shortHash(pitMeta.sourceSnapshotId)}
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {pitMeta.enabled ? (
                          <div className="space-y-1">
                            <Badge className="border-cyan-400/30 bg-cyan-500/15 text-cyan-200">已记录</Badge>
                            <div className="text-xs text-slate-500">截止：{formatTime(pitAsOfTime(row.pit))}</div>
                            <div className="text-xs text-slate-600">K线：{formatNumber(pitMeta.rowCount)} 根</div>
                            <div className="text-xs text-slate-600">参数：{shortHash(pitMeta.paramsHash)}</div>
                            <div className="text-xs text-slate-600">策略：{pitString(row.pit, "strategy_version")}</div>
                            <div className="text-xs text-slate-600">引擎：{pitString(row.pit, "engine_version")}</div>
                            <Link
                              href={researchSnapshotHref(row.symbol, row.interval, pitAsOfTime(row.pit))}
                              className="inline-flex text-xs text-cyan-200 hover:text-cyan-100"
                            >
                              回看当时上下文
                            </Link>
                          </div>
                        ) : (
                          <Badge className="border-slate-400/20 bg-slate-500/15 text-slate-400">旧记录</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                    );
                  })}
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
                        <div className="mt-2">
                          <Link
                            href={researchSnapshotHref(row.symbol, null, row.current_timestamp || row.end_time || row.start_time)}
                            className="text-xs text-cyan-200 hover:text-cyan-100"
                          >
                            回看会话时间点
                          </Link>
                        </div>
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
                    <TableHead className="text-slate-400">摘要/操作</TableHead>
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
                        因子 {snapshotCountAny(row.input_snapshot_ids, ["factor_snapshot_ids", "factor_ids"])}
                        <br />
                        信号 {snapshotCountAny(row.input_snapshot_ids, ["signal_event_ids", "signal_ids"])}
                        <br />
                        <Link
                          href={researchSnapshotHref(row.symbol, "1h", row.timestamp)}
                          className="text-cyan-200 hover:text-cyan-100"
                        >
                          回看决策材料
                        </Link>
                      </TableCell>
                      <TableCell className="max-w-[320px]">
                        <div className="truncate text-slate-400">{row.summary || "暂无摘要"}</div>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs">
                          <button
                            type="button"
                            onClick={() => void fetchDecisionDetail(row.id)}
                            className={cn(
                              "text-cyan-200 hover:text-cyan-100",
                              selectedDecisionId === row.id && "font-semibold text-cyan-100",
                            )}
                          >
                            查看审计详情
                          </button>
                          <Link
                            href={researchSnapshotHref(row.symbol, "1h", row.timestamp)}
                            className="text-slate-300 hover:text-white"
                          >
                            回看研究台
                          </Link>
                          <Link
                            href={`/decisions?symbol=${encodeURIComponent(row.symbol)}`}
                            className="text-slate-300 hover:text-white"
                          >
                            去决策中心
                          </Link>
                        </div>
                      </TableCell>
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

        {(detailLoading || detailError || decisionDetail) && (
          <Card className="border-cyan-400/20 bg-[radial-gradient(circle_at_top_right,rgba(14,165,233,0.16),transparent_34%),rgba(255,255,255,0.04)]">
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div>
                <CardTitle className="text-white">单条决策审计详情</CardTitle>
                <p className="mt-1 text-sm leading-6 text-slate-500">
                  这里按“输入快照 → Agent 输出 → OrderIntent → RiskGuard → 模拟盘”的顺序展示，不修改任何历史记录。
                </p>
              </div>
              {decisionDetail && (
                <div className="flex flex-wrap justify-end gap-2">
                  <Link href={decisionDetail.links.research_snapshot || researchSnapshotHref(decisionDetail.decision.symbol, "1h", decisionDetail.decision.timestamp)}>
                    <Button size="sm" variant="outline" className="border-cyan-400/30 bg-cyan-500/10 text-cyan-100 hover:bg-cyan-500/20">
                      回看研究台
                    </Button>
                  </Link>
                  <Link href={decisionDetail.links.decision_center || `/decisions?symbol=${encodeURIComponent(decisionDetail.decision.symbol)}`}>
                    <Button size="sm" variant="ghost" className="text-cyan-100 hover:bg-cyan-500/10">
                      去决策中心
                    </Button>
                  </Link>
                  {decisionDetail.links.audit_export && (
                    <Link href={decisionDetail.links.audit_export} target="_blank">
                      <Button size="sm" variant="ghost" className="text-slate-200 hover:bg-white/10">
                        可选导出 JSON
                      </Button>
                    </Link>
                  )}
                </div>
              )}
            </CardHeader>
            <CardContent>
              {detailLoading && (
                <div className="rounded-2xl border border-white/10 bg-black/20 p-5 text-sm text-slate-300">
                  <RefreshCw className="mr-2 inline h-4 w-4 animate-spin" />
                  正在读取决策 #{selectedDecisionId} 的审计详情...
                </div>
              )}

              {detailError && (
                <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
                  {detailError}
                </div>
              )}

              {decisionDetail && !detailLoading && (
                <div className="space-y-4">
                  <div className="rounded-2xl border border-emerald-400/20 bg-emerald-500/[0.06] p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-emerald-100">审计结果</p>
                        <p className="mt-1 text-xs leading-5 text-slate-400">
                          这是给使用者直接看的结论版审计。JSON 仍可导出，但不是唯一查看方式。
                        </p>
                      </div>
                      <Badge className="border border-emerald-400/30 bg-emerald-500/15 text-emerald-200">
                        可追溯 · 可复核 · 可导出
                      </Badge>
                    </div>
                    <div className="mt-4 grid gap-3 lg:grid-cols-2">
                      {auditResultLines(decisionDetail).map((line) => (
                        <div key={line} className="rounded-xl border border-white/10 bg-slate-950/45 px-3 py-2 text-xs leading-5 text-slate-200">
                          {line}
                        </div>
                      ))}
                    </div>
                  </div>

                  {tradingAgentsInternalChain(decisionDetail).length > 0 && (
                    <details className="rounded-2xl border border-amber-300/20 bg-amber-400/[0.04] p-4">
                      <summary className="cursor-pointer select-none text-sm font-semibold text-amber-100">
                        完整 TradingAgentsGraph 链路：{tradingAgentsInternalChain(decisionDetail).length} 个内部角色 / 节点
                      </summary>
                      <p className="mt-2 text-xs leading-5 text-slate-400">
                        默认审计先显示核心结果；这里可以展开查看多头、空头、研究经理、三类风险分析员和最终裁决的原始链路。
                      </p>
                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        {tradingAgentsInternalChain(decisionDetail).map((entry, index) => (
                          <div key={`${entry.role || "chain"}-${entry.index || index}`} className="rounded-xl border border-white/10 bg-slate-950/45 p-3">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className="text-sm font-medium text-slate-100">
                                  {entry.index ? `${entry.index}. ` : ""}{entry.label || roleLabel(entry.role)}
                                </p>
                                <p className="mt-1 text-xs text-slate-500">{entry.phase || "chain"} · {entry.role}</p>
                              </div>
                              <Badge className="border border-amber-300/20 bg-amber-400/10 text-[11px] text-amber-100">
                                {entry.available ? "有独立输出" : "已折叠"}
                              </Badge>
                            </div>
                            <p className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs leading-5 text-slate-300">
                              {entry.reasoning || "本节点没有返回独立文本。"}
                            </p>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  <div className="grid gap-3 md:grid-cols-4">
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <p className="text-xs text-slate-500">决策</p>
                      <p className={cn("mt-2 text-lg font-semibold", signalClass(decisionDetail.decision.final_signal))}>
                        {signalLabel(decisionDetail.decision.final_signal)}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {decisionDetail.decision.symbol} · {formatTime(decisionDetail.decision.timestamp)}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <p className="text-xs text-slate-500">输入材料</p>
                      <p className="mt-2 text-lg font-semibold text-white">
                        {formatNumber(
                          decisionDetail.trace_summary.factor_snapshots
                          + decisionDetail.trace_summary.signal_events
                          + decisionDetail.trace_summary.news_events
                          + decisionDetail.trace_summary.macro_events,
                        )}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">因子/信号/新闻/宏观合计</p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <p className="text-xs text-slate-500">角色输出</p>
                      <p className="mt-2 text-lg font-semibold text-white">{formatNumber(decisionDetail.trace_summary.role_outputs)}</p>
                      <p className="mt-1 text-xs text-slate-500">来自 role_opinions 或 agent_signals</p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <p className="text-xs text-slate-500">执行链</p>
                      <p className={cn(
                        "mt-2 text-lg font-semibold",
                        decisionDetail.trace_summary.executed ? "text-emerald-300" : decisionDetail.trace_summary.risk_blocked ? "text-rose-300" : "text-slate-200",
                      )}>
                        {decisionDetail.trace_summary.executed ? "已进模拟盘" : decisionDetail.trace_summary.risk_blocked ? "风控拦截" : "未执行"}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        OrderIntent {formatNumber(decisionDetail.trace_summary.order_intent_events)} 条 · 交易 {formatNumber(decisionDetail.trace_summary.paper_trades)} 笔
                      </p>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-white">决策摘要</p>
                        <p className="mt-2 text-sm leading-6 text-slate-300">{decisionDetail.decision.summary || "这条决策没有写入摘要。"}</p>
                      </div>
                      <Badge className={decisionDetail.decision.risk_veto ? "border-rose-400/30 bg-rose-500/15 text-rose-300" : "border-emerald-400/30 bg-emerald-500/15 text-emerald-300"}>
                        {decisionDetail.decision.risk_veto ? "决策层风险否决" : "决策层未否决"}
                      </Badge>
                    </div>
                    <div className="mt-4 grid gap-3 text-xs text-slate-400 md:grid-cols-4">
                      <p>因子快照：<span className="font-mono text-slate-100">{formatNumber(decisionDetail.trace_summary.factor_snapshots)}</span></p>
                      <p>信号事件：<span className="font-mono text-slate-100">{formatNumber(decisionDetail.trace_summary.signal_events)}</span></p>
                      <p>新闻事件：<span className="font-mono text-slate-100">{formatNumber(decisionDetail.trace_summary.news_events)}</span></p>
                      <p>宏观事件：<span className="font-mono text-slate-100">{formatNumber(decisionDetail.trace_summary.macro_events)}</span></p>
                    </div>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <p className="text-sm font-semibold text-white">Agent 角色输出</p>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        {decisionDetail.role_outputs.length ? decisionDetail.role_outputs.map((role, index) => (
                          <div key={`${role.role || role.agent || "role"}-${index}`} className="rounded-xl border border-white/10 bg-slate-950/45 p-3">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className="text-sm font-medium text-slate-100">{roleLabel(role.role || role.agent_type || role.agent)}</p>
                                <p className="mt-1 text-xs text-slate-500">{roleOpinionLabel(role)}</p>
                              </div>
                              <Badge className="border-slate-400/20 bg-slate-500/15 text-[11px] text-slate-300">
                                {formatRatioPercent(role.confidence)}
                              </Badge>
                            </div>
                            <p className="mt-2 text-xs leading-5 text-slate-300">{readString(role.reasoning, "暂无推理摘要")}</p>
                            {Array.isArray(role.key_points) && role.key_points.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1">
                                {role.key_points.slice(0, 5).map((point) => (
                                  <span key={point} className="rounded-full bg-cyan-400/10 px-2 py-1 text-[10px] text-cyan-100">
                                    {point}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        )) : (
                          <div className="rounded-xl border border-white/10 bg-slate-950/45 p-4 text-sm text-slate-500 md:col-span-2">
                            这条决策没有保存结构化角色输出。
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <p className="text-sm font-semibold text-white">输入快照 ID</p>
                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        这些 ID 用来证明本次决策引用了哪些历史材料；真正回看内容请点“回看研究台”。
                      </p>
                      <pre className="mt-3 max-h-80 overflow-auto rounded-xl bg-slate-950/60 p-3 text-[11px] leading-5 text-slate-400">
                        {JSON.stringify(decisionDetail.decision.input_snapshot_ids || {}, null, 2)}
                      </pre>
                    </div>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-2">
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <p className="text-sm font-semibold text-white">OrderIntent / 风控事件</p>
                      <div className="mt-3 space-y-3">
                        {decisionDetail.order_intent_events.length ? decisionDetail.order_intent_events.map((row) => {
                          const details = row.details || {};
                          const intent = nestedObject(details, "intent");
                          const risk = nestedObject(details, "risk_preview");
                          const lineage = nestedObject(details, "data_lineage");
                          const riskAllowed = typeof risk.passed === "boolean" ? risk.passed : typeof risk.allowed === "boolean" ? risk.allowed : null;
                          return (
                            <div key={row.id} className="rounded-xl border border-white/10 bg-slate-950/45 p-3 text-xs text-slate-400">
                              <div className="flex items-start justify-between gap-3">
                                <Badge className={orderIntentBadge(row.action)}>{orderIntentActionLabel(row.action)}</Badge>
                                <span>{formatTime(row.created_at)}</span>
                              </div>
                              <div className="mt-3 grid gap-2 md:grid-cols-2">
                                <p>Intent：<span className="font-mono text-slate-200">{readString(intent.intent_id, "-")}</span></p>
                                <p>方向：<span className="font-mono text-slate-200">{readString(intent.side, "NO_ACTION")}</span></p>
                                <p>仓位：<span className="font-mono text-slate-200">{formatRatioPercent(intent.position_pct)}</span></p>
                                <p>风控：<span className={riskAllowed === true ? "text-emerald-300" : riskAllowed === false ? "text-rose-300" : "text-slate-300"}>{riskAllowed === true ? "通过" : riskAllowed === false ? "拦截" : "未触发"}</span></p>
                              </div>
                              <p className="mt-2 leading-5">价格来源：{readString(lineage.price_source, "未记录")}</p>
                              <Link href={auditExportHref(row.id)} target="_blank" className="mt-2 inline-flex text-cyan-200 hover:text-cyan-100">
                                导出该事件 JSON
                              </Link>
                            </div>
                          );
                        }) : (
                          <div className="rounded-xl border border-white/10 bg-slate-950/45 p-4 text-sm text-slate-500">
                            还没有为这条决策生成 OrderIntent。去决策中心展开该标的决策后，可以手动生成。
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <p className="text-sm font-semibold text-white">模拟盘成交记录</p>
                      <div className="mt-3 space-y-3">
                        {decisionDetail.paper_trades.length ? decisionDetail.paper_trades.map((trade) => (
                          <div key={trade.id} className="rounded-xl border border-white/10 bg-slate-950/45 p-3 text-xs text-slate-400">
                            <div className="flex items-start justify-between gap-3">
                              <p className="font-mono text-slate-100">{trade.client_order_id || `trade-${trade.id}`}</p>
                              <Badge className="border-emerald-400/30 bg-emerald-500/15 text-emerald-300">{trade.status}</Badge>
                            </div>
                            <div className="mt-3 grid gap-2 md:grid-cols-2">
                              <p>交易所：<span className="font-mono text-slate-200">{trade.exchange_id || "-"}</span></p>
                              <p>方向：<span className="font-mono text-slate-200">{trade.side}</span></p>
                              <p>数量：<span className="font-mono text-slate-200">{formatNumber(trade.quantity)}</span></p>
                              <p>价格：<span className="font-mono text-slate-200">{formatMoney(trade.price)}</span></p>
                              <p>手续费：<span className="font-mono text-slate-200">{formatMoney(trade.fee)}</span></p>
                              <p>时间：{formatTime(trade.created_at)}</p>
                            </div>
                          </div>
                        )) : (
                          <div className="rounded-xl border border-white/10 bg-slate-950/45 p-4 text-sm text-slate-500">
                            这条决策还没有对应的模拟盘成交。WAIT/观望或风控拦截都不会产生交易。
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <Card className="border-emerald-400/20 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.12),transparent_36%),rgba(255,255,255,0.04)]">
          <CardHeader>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <CardTitle className="text-white">审计记录查询</CardTitle>
                <p className="mt-1 text-sm leading-6 text-slate-500">
                  审计记录写入后不可修改，后续变化通过新增事件记录追踪。
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="border-white/10 bg-white/5 text-slate-100 hover:bg-white/10"
                onClick={() => void fetchAuditRecords()}
              >
                <RefreshCw className={cn("mr-2 h-4 w-4", auditRecordsLoading && "animate-spin")} />
                查询
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-10">
              <input
                value={auditFilters.symbol}
                onChange={(event) => updateAuditFilter("symbol", event.target.value.toUpperCase())}
                placeholder="symbol"
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              />
              <select
                value={auditFilters.eventType}
                onChange={(event) => updateAuditFilter("eventType", event.target.value)}
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              >
                <option value="">eventType</option>
                {["AGENT_DECISION", "ORDER_INTENT_CREATED", "RISK_CHECK_PASSED", "RISK_BLOCKED", "PAPER_ORDER_FILLED", "PAPER_ORDER_REJECTED", "POSITION_UPDATED", "PNL_UPDATED", "HOLD_RECORDED"].map((item) => (
                  <option key={item} value={item}>{orderIntentActionLabel(item)}</option>
                ))}
              </select>
              <select
                value={auditFilters.action}
                onChange={(event) => updateAuditFilter("action", event.target.value)}
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              >
                <option value="">action</option>
                <option value="BUY">买入</option>
                <option value="SELL">卖出</option>
                <option value="HOLD">持有/观望</option>
              </select>
              <select
                value={auditFilters.executionStatus}
                onChange={(event) => updateAuditFilter("executionStatus", event.target.value)}
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              >
                <option value="">executionStatus</option>
                <option value="FILLED">已成交</option>
                <option value="REJECTED">已拒绝</option>
                <option value="BLOCKED">已拦截</option>
              </select>
              <select
                value={auditFilters.riskStatus}
                onChange={(event) => updateAuditFilter("riskStatus", event.target.value)}
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              >
                <option value="">riskStatus</option>
                <option value="passed">风控通过</option>
                <option value="blocked">风控拦截</option>
                <option value="not_checked">未触发风控</option>
              </select>
              <select
                value={auditFilters.source}
                onChange={(event) => updateAuditFilter("source", event.target.value)}
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              >
                <option value="">source</option>
                <option value="manual">manual</option>
                <option value="coordination_history">agent</option>
                <option value="backtest">backtest</option>
              </select>
              <select
                value={auditFilters.executionMode}
                onChange={(event) => updateAuditFilter("executionMode", event.target.value)}
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              >
                <option value="">executionMode</option>
                <option value="rule_only">普通规则回测</option>
                <option value="agent_audited">Agent 审计回测</option>
              </select>
              <input
                value={auditFilters.backtestId}
                onChange={(event) => updateAuditFilter("backtestId", event.target.value)}
                placeholder="backtestId"
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              />
              <input
                value={auditFilters.replaySessionId}
                onChange={(event) => updateAuditFilter("replaySessionId", event.target.value)}
                placeholder="replaySessionId"
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              />
              <input
                type="datetime-local"
                value={auditFilters.startTime}
                onChange={(event) => updateAuditFilter("startTime", event.target.value)}
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              />
              <input
                type="datetime-local"
                value={auditFilters.endTime}
                onChange={(event) => updateAuditFilter("endTime", event.target.value)}
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-300/50"
              />
            </div>

            {auditRecordsError && (
              <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
                {auditRecordsError}
              </div>
            )}

            <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
              <div className="overflow-x-auto rounded-2xl border border-white/10 bg-black/20">
                <Table>
                  <TableHeader>
                    <TableRow className="border-white/10 hover:bg-transparent">
                      <TableHead className="text-slate-400">createdAt</TableHead>
                      <TableHead className="text-slate-400">symbol</TableHead>
                      <TableHead className="text-slate-400">eventType</TableHead>
                      <TableHead className="text-slate-400">decisionId</TableHead>
                      <TableHead className="text-slate-400">orderIntentId</TableHead>
                      <TableHead className="text-slate-400">orderId</TableHead>
                      <TableHead className="text-slate-400">action</TableHead>
                      <TableHead className="text-slate-400">executionStatus</TableHead>
                      <TableHead className="text-slate-400">riskStatus</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {auditRecordsLoading ? (
                      <TableRow className="border-white/10">
                        <TableCell colSpan={9} className="py-8 text-center text-slate-500">
                          <RefreshCw className="mr-2 inline h-4 w-4 animate-spin" />
                          正在读取审计记录...
                        </TableCell>
                      </TableRow>
                    ) : auditRecords.length ? auditRecords.map((record) => (
                      <TableRow
                        key={`${record.id}-${record.eventType}`}
                        className={cn("cursor-pointer border-white/10 hover:bg-white/[0.04]", selectedAuditRecord?.id === record.id && "bg-white/[0.06]")}
                        onClick={() => void fetchAuditRecordDetail(record)}
                      >
                        <TableCell className="text-xs text-slate-400">{formatTime(record.createdAt)}</TableCell>
                        <TableCell className="font-mono text-xs text-white">{record.symbol || "暂无数据"}</TableCell>
                        <TableCell><Badge className={orderIntentBadge(record.eventType)}>{orderIntentActionLabel(record.eventType)}</Badge></TableCell>
                        <TableCell className="font-mono text-xs text-slate-300">
                          {record.decisionId ? <Link href={`/audit?decision_id=${record.decisionId}`} className="text-cyan-200 hover:text-cyan-100">{String(record.decisionId)}</Link> : "暂无关联记录"}
                        </TableCell>
                        <TableCell className="max-w-[160px] truncate font-mono text-xs text-slate-400">{record.orderIntentId || "暂无关联记录"}</TableCell>
                        <TableCell className="font-mono text-xs text-slate-400">{record.orderId || "暂无关联记录"}</TableCell>
                        <TableCell className="text-xs text-slate-300">{record.action || "暂无数据"}</TableCell>
                        <TableCell className="text-xs text-slate-300">{record.executionStatus || "暂无数据"}</TableCell>
                        <TableCell className="text-xs text-slate-300">{record.riskStatus || "暂无数据"}</TableCell>
                      </TableRow>
                    )) : (
                      <TableRow className="border-white/10">
                        <TableCell colSpan={9} className="py-8 text-center text-slate-500">暂无审计记录。</TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-white">审计详情</p>
                    <p className="mt-1 text-xs text-slate-500">点击左侧记录查看完整 JSON 和友好摘要。</p>
                  </div>
                  <Button size="sm" variant="outline" className="border-white/10 bg-white/5 text-xs text-slate-100" onClick={() => void copyAuditJson()} disabled={!selectedAuditRecord}>
                    复制 JSON
                  </Button>
                </div>
                {copyMessage && <p className="mt-2 text-xs text-emerald-300">{copyMessage}</p>}
                {auditRecordDetailLoading ? (
                  <div className="py-10 text-center text-sm text-slate-500">
                    <RefreshCw className="mr-2 inline h-4 w-4 animate-spin" />
                    正在读取审计详情...
                  </div>
                ) : selectedAuditRecord ? (
                  <div className="mt-4 space-y-3">
                    <div className="rounded-xl border border-white/10 bg-slate-950/50 p-3 text-xs leading-5 text-slate-400">
                      <p>事件：<span className="text-slate-100">{orderIntentActionLabel(selectedAuditRecord.eventType)}</span></p>
                      <p>标的：<span className="font-mono text-slate-100">{selectedAuditRecord.symbol || "暂无数据"}</span></p>
                      <p>决策：<span className="font-mono text-slate-100">{selectedAuditRecord.decisionId || "暂无关联记录"}</span></p>
                      <p>OrderIntent：<span className="font-mono text-slate-100">{selectedAuditRecord.orderIntentId || "暂无关联记录"}</span></p>
                      <p>订单：<span className="font-mono text-slate-100">{selectedAuditRecord.orderId || "暂无关联记录"}</span></p>
                      <p>回测：<span className="font-mono text-slate-100">{selectedAuditRecord.backtestId || "暂无关联记录"}</span></p>
                      <p>回放：<span className="font-mono text-slate-100">{selectedAuditRecord.replaySessionId || "暂无关联记录"}</span></p>
                      <p>模式：<span className="font-mono text-slate-100">{selectedAuditRecord.executionMode || "暂无数据"}</span></p>
                      <p>不可修改：{selectedAuditRecord.immutable ? "是" : "否"}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {selectedAuditRecord.decisionId ? (
                        <Link href={`/audit?decision_id=${selectedAuditRecord.decisionId}`}>
                          <Button size="sm" variant="outline" className="h-7 border-cyan-500/30 text-xs text-cyan-200">查看决策详情</Button>
                        </Link>
                      ) : <span className="text-[11px] text-slate-500">暂无关联决策</span>}
                      {selectedAuditRecord.backtestId ? (
                        <Link href={`/backtest?backtest_id=${selectedAuditRecord.backtestId}`}>
                          <Button size="sm" variant="outline" className="h-7 border-indigo-500/30 text-xs text-indigo-200">返回回测详情</Button>
                        </Link>
                      ) : <span className="text-[11px] text-slate-500">暂无关联回测</span>}
                      {selectedAuditRecord.replaySessionId ? (
                        <Link href={`/replay?session_id=${selectedAuditRecord.replaySessionId}${selectedAuditRecord.replayTime ? `&as_of_time=${encodeURIComponent(selectedAuditRecord.replayTime)}` : ""}`}>
                          <Button size="sm" variant="outline" className="h-7 border-emerald-500/30 text-xs text-emerald-200">定位历史回放</Button>
                        </Link>
                      ) : <span className="text-[11px] text-slate-500">暂无关联回放</span>}
                      {selectedAuditRecord.orderIntentId ? (
                        <Link href={`/audit?order_intent_id=${selectedAuditRecord.orderIntentId}`}>
                          <Button size="sm" variant="outline" className="h-7 border-fuchsia-500/30 text-xs text-fuchsia-200">查看 OrderIntent</Button>
                        </Link>
                      ) : <span className="text-[11px] text-slate-500">暂无关联 OrderIntent</span>}
                    </div>
                    <details className="rounded-xl border border-white/10 bg-slate-950/50 p-3">
                      <summary className="cursor-pointer text-sm font-semibold text-white">完整 JSON</summary>
                      <pre className="mt-3 max-h-[520px] overflow-auto rounded-lg bg-black/40 p-3 text-[11px] leading-5 text-slate-400">
                        {JSON.stringify(selectedAuditRecord, null, 2)}
                      </pre>
                    </details>
                  </div>
                ) : (
                  <div className="mt-4 rounded-xl border border-white/10 bg-slate-950/40 p-6 text-center text-sm text-slate-500">
                    暂无数据。
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.14),transparent_34%),rgba(255,255,255,0.04)]">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-white">TradingAgents 执行闭环审计</CardTitle>
              <p className="mt-1 text-sm text-slate-500">
                展示“决策 → OrderIntent → RiskGuard → 模拟盘”的最近记录。这里不会代表真实交易，只追踪模拟盘和手动执行动作。
              </p>
            </div>
            <Link href="/decisions">
              <Button size="sm" variant="ghost" className="text-cyan-100 hover:bg-cyan-500/10">去生成 OrderIntent</Button>
            </Link>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 lg:grid-cols-2">
              {(overview?.latest_order_intents || []).map((row) => {
                const details = row.details || {};
                const intent = nestedObject(details, "intent");
                const decision = nestedObject(details, "decision");
                const sizing = nestedObject(details, "sizing");
                const risk = nestedObject(details, "risk_preview");
                const lineage = nestedObject(details, "data_lineage");
                const execution = nestedObject(details, "execution");
                const side = readString(intent.side, "NO_ACTION");
                const decisionId = readNumber(intent.decision_id || decision.id);
                const riskAllowed = typeof risk.passed === "boolean" ? risk.passed : typeof risk.allowed === "boolean" ? risk.allowed : null;
                return (
                  <div key={row.id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <Badge className={orderIntentBadge(row.action)}>{orderIntentActionLabel(row.action)}</Badge>
                        <p className="mt-2 font-mono text-sm text-white">{readString(intent.symbol || row.resource, "未知标的")}</p>
                        <p className="mt-1 text-xs text-slate-500">决策 #{decisionId || "-"} · {formatTime(row.created_at)}</p>
                      </div>
                      <div className="text-right text-xs text-slate-400">
                        <p>方向 <span className="font-mono text-slate-100">{side}</span></p>
                        <p>仓位 <span className="font-mono text-slate-100">{formatRatioPercent(intent.position_pct)}</span></p>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 text-xs text-slate-400 sm:grid-cols-2">
                      <div className="rounded-xl border border-white/10 bg-slate-950/50 p-3">
                        <p className="text-slate-500">OrderIntent</p>
                        <p className="mt-1">ID：<span className="font-mono text-slate-200">{readString(intent.intent_id, "-")}</span></p>
                        <p>置信度：<span className="font-mono text-slate-200">{formatRatioPercent(intent.confidence)}</span></p>
                        <p>有效期：{formatTime(readString(intent.valid_until, ""))}</p>
                      </div>
                      <div className="rounded-xl border border-white/10 bg-slate-950/50 p-3">
                        <p className="text-slate-500">RiskGuard / 模拟盘</p>
                        <p>风控：<span className={riskAllowed === true ? "text-emerald-300" : riskAllowed === false ? "text-rose-300" : "text-slate-300"}>{riskAllowed === true ? "通过" : riskAllowed === false ? "拦截" : "未触发下单检查"}</span></p>
                        <p>规则：<span className="font-mono text-slate-200">{readString(risk.rule, "-")}</span></p>
                        <p>数量：<span className="font-mono text-slate-200">{formatNumber(sizing.quantity)}</span></p>
                        <p>订单：<span className="font-mono text-slate-200">{readString(details.order_id || execution.order_id, "-")}</span></p>
                      </div>
                    </div>

                    <div className="mt-3 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-xs leading-5 text-slate-400">
                      <p>决策摘要：{readString(decision.summary, "暂无摘要")}</p>
                      <p>价格来源：{readString(lineage.price_source, "新记录会写入 MarketDataGateway / OpenBB/yfinance / CCXT fallback 说明")}</p>
                      <div className="mt-2">
                        <Link href={auditExportHref(row.id)} target="_blank" className="text-cyan-200 hover:text-cyan-100">
                          导出这条审计 JSON
                        </Link>
                      </div>
                    </div>
                  </div>
                );
              })}
              {!loading && !overview?.latest_order_intents?.length && (
                <div className="rounded-2xl border border-white/10 bg-black/20 p-8 text-center text-sm text-slate-500 lg:col-span-2">
                  还没有 OrderIntent 审计记录。去“决策中心”展开一条建议，点击“生成 OrderIntent”后这里会出现记录。
                </div>
              )}
            </div>
          </CardContent>
        </Card>

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
                    <TableCell className="max-w-[520px]">
                      <div className="truncate font-mono text-xs text-slate-500">{JSON.stringify(row.details || {})}</div>
                      <Link href={auditExportHref(row.id)} target="_blank" className="mt-1 inline-flex text-xs text-cyan-200 hover:text-cyan-100">
                        导出 JSON
                      </Link>
                    </TableCell>
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

export default function AuditPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-screen"><p className="text-muted-foreground">Loading audit page...</p></div>}>
      <AuditPageContent />
    </Suspense>
  );
}
