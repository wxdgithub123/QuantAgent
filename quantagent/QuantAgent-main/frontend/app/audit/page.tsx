"use client";

import { useState, useEffect, useCallback, useRef, type KeyboardEvent, type ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import {
  RefreshCw, ChevronDown, ChevronUp,
  CheckCircle, Shield, XCircle, AlertTriangle,
  Database, Layers, ScrollText, Hash, GitCompare, Download, Filter, FileSearch, Copy
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────
interface AuditRecord {
  id: number | null; eventType: string; symbol?: string | null;
  asOfTime?: string | null; decisionId?: number | string | null;
  sourceDecisionId?: number | string | null; replayDecisionId?: number | string | null;
  riskStatus?: string | null; synthetic?: boolean;
  executionStatus?: string | null; orderIntentId?: string | null; orderId?: string | null;
  executionMode?: string | null; action?: string | null; createdAt?: string | null;
  backtestId?: number | string | null; replaySessionId?: string | null;
  contextHash?: string | null; payloadHash?: string | null; prevHash?: string | null;
  immutable?: boolean | null; isFullGraph?: boolean | null; strictSnapshotReplay?: boolean | null;
}

interface AgentAnalysisEntry {
  role?: string; label?: string; opinion?: string; confidence?: number | null;
  summary?: string; reasoning?: string; data_source_chain?: string; output?: string; available?: boolean;
  index?: number; phase?: string; risk_flag?: boolean; key_points?: string[];
}

type JsonRecord = Record<string, unknown>;

interface AuditTimelineEntry extends Record<string, unknown> {
  inputSummary?: JsonRecord;
  synthetic?: boolean;
  auditSource?: string;
  syntheticReason?: string;
  riskUnavailable?: boolean;
  riskStatus?: string;
  backtestId?: number | string | null;
  replaySessionId?: string | null;
  orderIntentId?: string | null;
  orderId?: string | null;
}

interface AgentRoleView extends AgentAnalysisEntry {
  key: string;
}

interface InputMaterials {
  source?: string;
  price?: unknown;
  riskNotes?: unknown;
  snapshotIds?: JsonRecord;
  bars?: unknown[];
  newsEvents?: unknown[];
  macroEvents?: unknown[];
  factorSnapshot?: JsonRecord;
  factorEvidence?: unknown[];
  recentSignals?: unknown[];
  signalEvents?: unknown[];
  normalizedSnapshot?: JsonRecord | null;
  countsSource?: JsonRecord;
  detailCompleteness?: JsonRecord;
  barsCount?: number;
  newsCount?: number;
  macroCount?: number;
  factorsCount?: number;
  signalsCount?: number;
}

interface ReplayRun {
  id?: number | null;
  eventType?: string;
  status?: string;
  sourceDecisionId?: number | string | null;
  replayDecisionId?: number | string | null;
  originalContextHash?: string | null;
  replayContextHash?: string | null;
  contextHashChanged?: boolean;
  contextHashChangeReason?: string | null;
  strictSnapshotReplay?: boolean;
  replayMethod?: string | null;
  fallbackReason?: string | null;
  diffSummary?: JsonRecord;
  auditUrl?: string | null;
  error?: string | null;
  createdAt?: string | null;
}

interface DecisionAuditDetail {
  schema_version?: string; generated_at?: string; strictSnapshotReplay?: boolean; strictSnapshotReplayAvailable?: boolean; originalAgentDecisionAuditPresent?: boolean; riskUnavailable?: boolean; syntheticAuditCount?: number;
  basic_info?: {
    decisionId?: number; symbol?: string; action?: string; confidence?: number; status?: string; createdAt?: string;
    model?: string; agentGraph?: string; source?: string; contextId?: string; contextHash?: string; availableTime?: string;
    modelVersion?: string; promptVersion?: string; graphMode?: string | null; configuredMode?: string | null;
    isFullGraph?: boolean | null; strongAcceptanceEligible?: boolean | null; modeNote?: string | null;
  };
  agent_analysis?: Record<string, AgentAnalysisEntry>;
  decision?: { final_signal?: string; risk_veto?: boolean; vote_breakdown?: Record<string, number> };
  input_snapshot?: {
    snapshotId?: JsonRecord; barsCount?: number; newsCount?: number; factorsCount?: number; signalsCount?: number;
    macroCount?: number; price?: number; dataProvider?: string; asOfTime?: string; availableTime?: string;
    factorSnapshot?: JsonRecord; recentSignals?: unknown[]; dataVersion?: string; sourceVersion?: string;
    barMeta?: JsonRecord | null; dataVersions?: JsonRecord | null;
  };
  trace_summary?: { factor_snapshots?: number; signal_events?: number; news_events?: number; macro_events?: number; role_outputs?: number; order_intent_events?: number; paper_trades?: number; risk_blocked?: boolean; risk_unavailable?: boolean; synthetic_audit_events?: number; input_snapshot_id_groups?: number; replay_runs?: number };
  risk_guard?: { passed?: boolean | null; riskUnavailable?: boolean; blockedReason?: string | null };
  execution_result?: { paperOrderGenerated?: boolean; orderId?: string | null; fillPrice?: number | null; orderStatus?: string; source?: string };
  order_intent?: { orderIntentId?: string | null; action?: string; reason?: string };
  decision_evidence?: Record<string, unknown>;
  draft_order_intent?: Record<string, unknown>;
  execution_preview_or_result?: Record<string, unknown>;
  pit_checks?: Array<Record<string, unknown>>;
  audit_timeline?: AuditTimelineEntry[];
  order_intent_events?: Array<Record<string, unknown>>;
  paper_trades?: Array<Record<string, unknown>>;
  factor_evidence?: Array<Record<string, unknown>>;
  role_outputs?: AgentAnalysisEntry[];
  input_materials?: InputMaterials;
  role_input_materials?: Array<Record<string, unknown>>;
  replay_runs?: ReplayRun[];
  links?: { research_snapshot?: string; decision_center?: string; audit_export?: string; replay?: string; analytics?: string; backtest?: string };
}

type AuditFilters = {
  symbol: string;
  eventType: string;
  riskStatus: string;
  executionStatus: string;
  executionMode: string;
  startTime: string;
  endTime: string;
  decisionId: string;
  orderIntentId: string;
  orderId: string;
  backtestId: string;
  replaySessionId: string;
};

type TimeRangeMode = "all" | "1h" | "24h" | "7d" | "custom";

const emptyFilters: AuditFilters = {
  symbol: "",
  eventType: "",
  riskStatus: "",
  executionStatus: "",
  executionMode: "",
  startTime: "",
  endTime: "",
  decisionId: "",
  orderIntentId: "",
  orderId: "",
  backtestId: "",
  replaySessionId: "",
};

const symbolOptions = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"];
const eventTypeOptions = [
  "AGENT_DECISION",
  "ORDER_INTENT_CREATED",
  "HOLD_RECORDED",
  "RISK_CHECK_PASSED",
  "RISK_BLOCKED",
  "RISK_CHECK_UNAVAILABLE",
  "PAPER_ORDER_FILLED",
  "PAPER_ORDER_REJECTED",
];
const executionStatusOptions = ["FILLED", "REJECTED", "EXECUTED", "BLOCKED", "READY", "NO_ACTION"];
type AdvancedFilterKey = "executionStatus" | "executionMode" | "decisionId" | "orderIntentId" | "orderId" | "backtestId" | "replaySessionId";
const timeRangeOptions: Array<{ value: TimeRangeMode; label: string }> = [
  { value: "all", label: "全部时间" },
  { value: "1h", label: "最近 1 小时" },
  { value: "24h", label: "最近 24 小时" },
  { value: "7d", label: "最近 7 天" },
  { value: "custom", label: "自定义" },
];
const timeRangeHours: Partial<Record<TimeRangeMode, number>> = { "1h": 1, "24h": 24, "7d": 24 * 7 };

const eventTypeLabels: Record<string, string> = {
  AGENT_DECISION: "AI 决策",
  ORDER_INTENT_CREATED: "生成下单意图",
  HOLD_RECORDED: "记录观望",
  RISK_CHECK_PASSED: "风控通过",
  RISK_BLOCKED: "风控拦截",
  RISK_CHECK_UNAVAILABLE: "风控不可用",
  PAPER_ORDER_FILLED: "模拟成交",
  PAPER_ORDER_REJECTED: "模拟拒单",
};
const riskStatusLabels: Record<string, string> = {
  passed: "风控通过",
  blocked: "风控拦截",
  unavailable: "风控不可用",
  not_checked: "未检查风控",
};
const executionStatusLabels: Record<string, string> = {
  FILLED: "已成交",
  REJECTED: "已拒单",
  EXECUTED: "已执行",
  BLOCKED: "被阻断",
  READY: "待执行",
  NO_ACTION: "无动作",
};
const executionModeLabels: Record<string, string> = {
  agent_audited: "Agent 审计执行",
  rule_only: "规则执行",
  paper: "模拟盘",
};
const actionLabels: Record<string, string> = {
  BUY: "买入",
  SELL: "卖出",
  HOLD: "观望",
  WAIT: "等待",
};
const presetFilters: Array<{ label: string; description: string; filters: Partial<AuditFilters> }> = [
  { label: "AI 决策", description: "只看 Agent 产出的决策事件", filters: { eventType: "AGENT_DECISION" } },
  { label: "风控拦截", description: "定位被风控挡下的链路", filters: { eventType: "RISK_BLOCKED", riskStatus: "blocked" } },
  { label: "风控异常", description: "查看风控不可用或降级记录", filters: { eventType: "RISK_CHECK_UNAVAILABLE", riskStatus: "unavailable" } },
  { label: "已成交", description: "查看产生模拟成交的事件", filters: { eventType: "PAPER_ORDER_FILLED", executionStatus: "FILLED" } },
  { label: "观望", description: "查看未生成下单动作的决策", filters: { eventType: "HOLD_RECORDED", executionStatus: "NO_ACTION" } },
];

const NA = "后端未返回";
const fmtTime = (t?: string | null) => {
  if (!t) return null;
  const date = new Date(t);
  return Number.isNaN(date.getTime()) ? String(t) : date.toLocaleString("zh-CN");
};
const toDateTimeInputValue = (date: Date) => {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
};
const toDateTimeInputText = (value?: string | null) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value.slice(0, 16) : toDateTimeInputValue(date);
};
const applyTimeRangeToFilters = (filters: AuditFilters, mode: TimeRangeMode) => {
  if (mode === "all") return { ...filters, startTime: "", endTime: "" };
  if (mode === "custom") return filters;
  const end = new Date();
  const start = new Date(end.getTime() - (timeRangeHours[mode] || 0) * 60 * 60 * 1000);
  return { ...filters, startTime: toDateTimeInputValue(start), endTime: toDateTimeInputValue(end) };
};
const advancedFiltersFrom = (filters: AuditFilters): Pick<AuditFilters, AdvancedFilterKey> => ({
  executionStatus: filters.executionStatus,
  executionMode: filters.executionMode,
  decisionId: filters.decisionId,
  orderIntentId: filters.orderIntentId,
  orderId: filters.orderId,
  backtestId: filters.backtestId,
  replaySessionId: filters.replaySessionId,
});
const readAuditUrlParams = () => {
  const params = new URLSearchParams(window.location.search);
  const get = (...keys: string[]) => keys.map(key => params.get(key)).find(value => value && value.trim() !== "") || "";
  const rawTimeRange = get("timeRange") as TimeRangeMode;
  const filters: AuditFilters = {
    ...emptyFilters,
    symbol: get("symbol").toUpperCase(),
    eventType: get("eventType", "type"),
    riskStatus: get("riskStatus", "risk"),
    executionStatus: get("executionStatus"),
    executionMode: get("executionMode"),
    startTime: toDateTimeInputText(get("startTime", "start_time")),
    endTime: toDateTimeInputText(get("endTime", "end_time")),
    decisionId: get("decision_id", "decisionId"),
    orderIntentId: get("orderIntentId", "order_intent_id"),
    orderId: get("orderId", "order_id"),
    backtestId: get("backtestId", "backtest_id"),
    replaySessionId: get("replaySessionId", "replay_session_id"),
  };
  const timeRangeFromUrl = timeRangeOptions.some(option => option.value === rawTimeRange) ? rawTimeRange : null;
  const selectedDecisionId = Number(filters.decisionId);
  return {
    filters: timeRangeFromUrl && timeRangeFromUrl !== "custom" ? applyTimeRangeToFilters(filters, timeRangeFromUrl) : filters,
    selectedDecisionId: Number.isFinite(selectedDecisionId) && selectedDecisionId > 0 ? selectedDecisionId : null,
    timeRangeMode: (timeRangeFromUrl || (filters.startTime || filters.endTime ? "custom" : "all")) as TimeRangeMode,
  };
};
const buildAuditUrlParams = (filters: AuditFilters, selectedId: number | null, timeRangeMode: TimeRangeMode) => {
  const params = new URLSearchParams();
  const set = (key: string, value?: string | number | null) => {
    if (value != null && String(value).trim() !== "") params.set(key, String(value));
  };
  set("symbol", filters.symbol);
  set("eventType", filters.eventType);
  set("riskStatus", filters.riskStatus);
  set("executionStatus", filters.executionStatus);
  set("executionMode", filters.executionMode);
  if (timeRangeMode === "custom") {
    set("startTime", filters.startTime);
    set("endTime", filters.endTime);
  }
  set("orderIntentId", filters.orderIntentId);
  set("orderId", filters.orderId);
  set("backtestId", filters.backtestId);
  set("replaySessionId", filters.replaySessionId);
  set("decision_id", selectedId || filters.decisionId);
  if (timeRangeMode !== "custom" && timeRangeMode !== "all") params.set("timeRange", timeRangeMode);
  return params;
};
const formatPct = (v?: number | null) => v != null ? (v * 100).toFixed(0) + "%" : "—";
const asRecord = (value: unknown): JsonRecord => value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
const asArray = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const asRecordArray = (value: unknown): JsonRecord[] => asArray(value).filter(item => item && typeof item === "object" && !Array.isArray(item)) as JsonRecord[];
const formatValue = (value: unknown) => typeof value === "number" ? Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 4 }) : value != null ? String(value) : "—";
const firstText = (...values: unknown[]) => {
  for (const value of values) {
    if (value != null && String(value).trim() !== "") return String(value);
  }
  return "";
};
const compactText = (value: unknown, max = 260) => {
  const text = value == null ? "" : String(value);
  return text.length > max ? `${text.slice(0, max)}...` : text;
};
const shortValue = (value: unknown, max = 80) => compactText(formatValue(value), max);
const valueOf = (record: JsonRecord, ...keys: string[]) => {
  for (const key of keys) {
    const value = record[key];
    if (value != null && String(value).trim() !== "") return value;
  }
  return null;
};
const textOf = (record: JsonRecord, ...keys: string[]) => firstText(...keys.map(key => record[key]));
const timeOf = (record: JsonRecord, ...keys: string[]) => {
  const raw = textOf(record, ...keys);
  return raw ? (fmtTime(raw) || raw) : "—";
};
const prettyJson = (value: unknown) => {
  try { return JSON.stringify(value, null, 2); }
  catch { return String(value); }
};
const shortHash = (value?: unknown, head = 12, tail = 8) => {
  const text = firstText(value);
  if (!text) return "";
  return text.length <= head + tail + 3 ? text : `${text.slice(0, head)}...${text.slice(-tail)}`;
};
const copyToClipboard = (value?: unknown) => {
  const text = firstText(value);
  if (!text || typeof navigator === "undefined" || !navigator.clipboard) return;
  void navigator.clipboard.writeText(text);
};
const listValue = (value: unknown, max = 4) => {
  if (Array.isArray(value)) return value.slice(0, max).map(item => String(item)).join(", ");
  if (value && typeof value === "object") return compactText(prettyJson(value), 120);
  return value != null ? String(value) : "";
};
const numericValue = (value: unknown) => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) return Number(value);
  return null;
};
const firstUsefulNumber = (...values: unknown[]) => {
  const numbers = values.map(numericValue).filter((value): value is number => value != null);
  const positive = numbers.find(value => value > 0);
  return positive ?? numbers[0] ?? null;
};
const boolValue = (value: unknown) => typeof value === "boolean" ? value : null;
const detailText = (value: unknown) => {
  if (value == null) return NA;
  if (typeof value === "string") return value;
  return compactText(prettyJson(value), 360);
};
const emptyTextFor = (context: "material" | "old_count_only" | "not_applicable" | "no_order" | "risk_not_run" | "blocked_no_trade" | "role_outputs" | "replay_runs") => {
  const texts = {
    material: "本记录未保存该材料",
    old_count_only: "旧记录仅保存数量，未保存逐条材料",
    not_applicable: "该事件不适用",
    no_order: "没有触发下单",
    risk_not_run: "风控未执行或未记录结果",
    blocked_no_trade: "被风控拦截所以无成交",
    role_outputs: "旧记录未保存角色输出",
    replay_runs: "本记录还没有复跑结果",
  };
  return texts[context];
};
const isInferredChain = (value?: string | null) => !!value && /推断|inferred|coordination_history/i.test(value);
const replayStatusLabel = (value?: string | null) => {
  if (value === "completed") return "完成";
  if (value === "failed") return "失败";
  if (value === "running") return "运行中";
  return value || "复跑";
};
const replayMethodLabel = (value?: string | null) => {
  if (value === "strict_snapshot") return "严格快照";
  if (value === "pit_rebuild") return "按时点重建";
  if (value === "fallback_pit_rebuild") return "旧记录降级重建";
  return value || NA;
};
const isPitTimingCheck = (key: string, label: string) => {
  const text = `${key} ${label}`.toLowerCase();
  return key === "point_in_time_rule" || key === "factor_signal_evidence" ||
    /point.?in.?time|future|as_of|available_time|factor_signal|时点|未来|因子.*信号|信号.*因子/.test(text);
};
const graphModeLabel = (isFullGraph?: boolean | null, graphMode?: string | null) => {
  if (isFullGraph === true) return "完整图";
  if (isFullGraph === false) return "快速研究";
  return graphMode || "未知模式";
};
const labelFor = (labels: Record<string, string>, value?: string | null, fallback = "全部") =>
  value ? labels[value] || value : fallback;
const eventTypeLabel = (value?: string | null) => labelFor(eventTypeLabels, value, "全部环节");
const riskStatusLabel = (value?: string | null) => labelFor(riskStatusLabels, value, "全部风控状态");
const executionStatusLabel = (value?: string | null) => labelFor(executionStatusLabels, value, "全部执行状态");
const executionModeLabel = (value?: string | null) => labelFor(executionModeLabels, value, "全部执行模式");
const actionLabel = (value?: string | null) => value ? actionLabels[String(value).toUpperCase()] || value : "";
const eventTypeBadgeClass = (value?: string | null) =>
  value === "RISK_BLOCKED" || value === "PAPER_ORDER_REJECTED" ? "bg-red-500/15 text-red-300" :
  value === "RISK_CHECK_UNAVAILABLE" ? "bg-amber-500/15 text-amber-300" :
  value === "RISK_CHECK_PASSED" || value === "PAPER_ORDER_FILLED" ? "bg-green-500/15 text-green-300" :
  value === "AGENT_DECISION" ? "bg-cyan-500/15 text-cyan-300" :
  "bg-slate-700/50 text-slate-300";
const riskBadgeClass = (value?: string | null) =>
  value === "blocked" ? "bg-red-500/15 text-red-300" :
  value === "unavailable" ? "bg-amber-500/15 text-amber-300" :
  value === "passed" ? "bg-green-500/15 text-green-300" :
  "bg-slate-800 text-slate-400";
const actionBadgeClass = (value?: string | null) => {
  const action = String(value || "").toUpperCase();
  return action === "BUY" ? "bg-green-500/15 text-green-300" :
    action === "SELL" ? "bg-red-500/15 text-red-300" :
    action === "HOLD" || action === "WAIT" ? "bg-slate-800 text-slate-300" :
    "bg-slate-800 text-slate-400";
};

const materialKey = (prefix: string, item: JsonRecord, index: number) =>
  `${prefix}-${index}-${String(valueOf(item, "id", "snapshotId", "event_id", "event_time", "timestamp", "published_at", "indicator", "name") || "row")}`;

function MaterialPanel({ title, count, children, empty }: { title: string; count: number; children: ReactNode; empty?: string }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950/40 p-2 min-w-0">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <p className="text-[9px] text-slate-500">{title}</p>
        <Badge className="bg-slate-800 text-slate-400 text-[8px]">{count} 条</Badge>
      </div>
      {count > 0 ? children : <p className="text-[10px] text-slate-600 italic">{empty || emptyTextFor("material")}</p>}
    </div>
  );
}

function EvidenceBadge({
  label,
  state,
  title,
}: {
  label: string;
  state: "pass" | "warn" | "fail" | "neutral";
  title?: string;
}) {
  const className = state === "pass"
    ? "border-green-500/20 bg-green-500/10 text-green-300"
    : state === "warn"
      ? "border-amber-500/20 bg-amber-500/10 text-amber-300"
      : state === "fail"
        ? "border-red-500/20 bg-red-500/10 text-red-300"
        : "border-slate-700 bg-slate-900/70 text-slate-400";
  const Icon = state === "pass" ? CheckCircle : state === "fail" ? XCircle : state === "warn" ? AlertTriangle : Shield;
  return (
    <span title={title} className={`inline-flex h-5 items-center gap-1 rounded border px-1.5 text-[8px] ${className}`}>
      <Icon className="h-2.5 w-2.5 shrink-0" />
      <span className="leading-none">{label}</span>
    </span>
  );
}

export default function AuditPage() {
  const requestSeqRef = useRef(0);
  const detailRequestSeqRef = useRef(0);
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [filters, setFilters] = useState<AuditFilters>(emptyFilters);
  const [draftAdvancedFilters, setDraftAdvancedFilters] = useState<Pick<AuditFilters, AdvancedFilterKey>>(advancedFiltersFrom(emptyFilters));
  const [timeRangeMode, setTimeRangeMode] = useState<TimeRangeMode>("all");
  const [urlHydrated, setUrlHydrated] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DecisionAuditDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSnapshot, setShowSnapshot] = useState(true);
  const [showRoles, setShowRoles] = useState(true);
  const [showFutureCheck, setShowFutureCheck] = useState(true);
  const [showChain, setShowChain] = useState(true);
  const [showRepro, setShowRepro] = useState(true);
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [entryDecisionIds, setEntryDecisionIds] = useState<number[]>([]);

  const clearSelectedDetail = useCallback(() => {
    detailRequestSeqRef.current += 1;
    setSelectedId(null);
    setDetail(null);
    setDetailLoading(false);
    setEntryDecisionIds([]);
  }, []);

  const setFilter = <K extends keyof AuditFilters>(key: K, value: AuditFilters[K]) => {
    clearSelectedDetail();
    setFilters(current => ({ ...current, [key]: value }));
  };
  const applyPreset = (preset: Partial<AuditFilters>) => {
    clearSelectedDetail();
    setFilters(current => ({
      ...emptyFilters,
      symbol: current.symbol,
      startTime: current.startTime,
      endTime: current.endTime,
      ...preset,
    }));
    setDraftAdvancedFilters(advancedFiltersFrom({ ...emptyFilters, ...preset } as AuditFilters));
  };
  const setDraftAdvancedFilter = <K extends AdvancedFilterKey>(key: K, value: AuditFilters[K]) => {
    setDraftAdvancedFilters(current => ({ ...current, [key]: value }));
  };
  const applyAdvancedFilters = useCallback(() => {
    clearSelectedDetail();
    setFilters(current => ({ ...current, ...draftAdvancedFilters }));
  }, [clearSelectedDetail, draftAdvancedFilters]);
  const handleAdvancedKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") applyAdvancedFilters();
  };
  const updateTimeRange = (mode: TimeRangeMode) => {
    clearSelectedDetail();
    setTimeRangeMode(mode);
    setFilters(current => applyTimeRangeToFilters(current, mode));
  };
  const clearFilters = () => {
    clearSelectedDetail();
    setTimeRangeMode("all");
    setFilters(emptyFilters);
    setDraftAdvancedFilters(advancedFiltersFrom(emptyFilters));
  };

  const fetchRecords = useCallback(async () => {
    if (!urlHydrated) return;
    const requestId = ++requestSeqRef.current;
    setRecordsLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ limit: "50" });
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.set(key, value);
      });
      const res = await fetch("/api/v1/audit/records?" + params.toString());
      if (!res.ok) throw new Error("HTTP " + res.status);
      const rows = ((await res.json()).data || []) as AuditRecord[];
      if (requestId === requestSeqRef.current) setRecords(rows);
    } catch (e: unknown) {
      if (requestId === requestSeqRef.current) setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      if (requestId === requestSeqRef.current) setRecordsLoading(false);
    }
  }, [filters, urlHydrated]);

  const fetchDetail = useCallback(async (id: number) => {
    const requestId = ++detailRequestSeqRef.current;
    setDetailLoading(true); setSelectedId(id); setError(null);
    setEntryDecisionIds([]);
    try {
      const res = await fetch("/api/v1/audit/decisions/" + id);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const nextDetail = await res.json();
      if (requestId === detailRequestSeqRef.current) setDetail(nextDetail);
    } catch (e: unknown) {
      if (requestId === detailRequestSeqRef.current) {
        setError(e instanceof Error ? e.message : "加载失败");
        setDetail(null);
      }
    } finally {
      if (requestId === detailRequestSeqRef.current) setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    const parsed = readAuditUrlParams();
    setFilters(parsed.filters);
    setDraftAdvancedFilters(advancedFiltersFrom(parsed.filters));
    setTimeRangeMode(parsed.timeRangeMode);
    setUrlHydrated(true);
    if (parsed.selectedDecisionId) fetchDetail(parsed.selectedDecisionId);
  }, [fetchDetail]);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  useEffect(() => {
    if (!urlHydrated) return;
    const params = buildAuditUrlParams(filters, selectedId, timeRangeMode);
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}`;
    if (`${window.location.pathname}${window.location.search}` !== nextUrl) {
      window.history.replaceState(null, "", nextUrl);
    }
  }, [filters, selectedId, timeRangeMode, urlHydrated]);

  const d = detail;
  const bi = d?.basic_info;
  const dec = d?.decision;
  const aa = d?.agent_analysis || {};
  const snap = d?.input_snapshot;
  const trace = d?.trace_summary;
  const timeline = d?.audit_timeline || [];
  const replayRuns = d?.replay_runs || [];
  const roleRows: AgentRoleView[] = d?.role_outputs?.length
    ? d.role_outputs.map((entry, index) => ({
        ...entry,
        key: String(entry.role || entry.label || `role-${index + 1}`),
        index: entry.index ?? index + 1,
      }))
    : Object.entries(aa).map(([key, entry], index) => ({
        ...(entry as AgentAnalysisEntry),
        key,
        index: (entry as AgentAnalysisEntry).index ?? index + 1,
      }));
  const inputSummary = timeline
    .map(item => asRecord(item.inputSummary))
    .find(item => Object.keys(item).length > 0) || {};
  const inputMaterials = d?.input_materials || {};
  const normalizedSnapshot = asRecord(inputMaterials.normalizedSnapshot);
  const inputBars = asRecordArray(inputMaterials.bars ?? normalizedSnapshot.bars ?? inputSummary.bars);
  const inputNewsEvents = asRecordArray(inputMaterials.newsEvents ?? normalizedSnapshot.news_events ?? inputSummary.news_events);
  const inputMacroEvents = asRecordArray(inputMaterials.macroEvents ?? normalizedSnapshot.macro_events ?? inputSummary.macro_events);
  const inputFactorEvidence = asRecordArray(inputMaterials.factorEvidence ?? d?.factor_evidence);
  const inputSignalEvents = asRecordArray(inputMaterials.signalEvents ?? inputMaterials.recentSignals ?? normalizedSnapshot.recent_signals ?? inputSummary.recent_signals ?? snap?.recentSignals);
  const countsSource = asRecord(inputMaterials.countsSource);
  const detailCompleteness = asRecord(inputMaterials.detailCompleteness);
  const detailCompletenessNote = textOf(detailCompleteness, "note");
  const inputFactorSnapshot = asRecord(inputMaterials.factorSnapshot ?? normalizedSnapshot.latest_factors ?? inputSummary.factor_snapshot ?? snap?.factorSnapshot);
  const inputSnapshotIds = asRecord(inputMaterials.snapshotIds ?? inputSummary.snapshot_ids ?? snap?.snapshotId);
  const inputRecentSignals = inputSignalEvents;
  const inputAsOfTime = snap?.asOfTime || bi?.availableTime || bi?.createdAt;
  const selectedDecisionId = bi?.decisionId ?? selectedId;
  const linkedRecord = records.find(row => {
    const ids = [row.decisionId, row.sourceDecisionId, row.replayDecisionId].map(value => Number(value));
    return selectedDecisionId != null && ids.some(value => Number.isFinite(value) && value === Number(selectedDecisionId));
  }) || null;
  const linkedBacktestId = firstText(linkedRecord?.backtestId, ...timeline.map(item => item.backtestId));
  const linkedReplaySessionId = firstText(linkedRecord?.replaySessionId, ...timeline.map(item => item.replaySessionId), ...(d?.paper_trades || []).map(item => item.session_id));
  const linkedOrderIntentId = firstText(d?.order_intent?.orderIntentId, linkedRecord?.orderIntentId, ...timeline.map(item => item.orderIntentId));
  const linkedOrderId = firstText(d?.execution_result?.orderId, linkedRecord?.orderId, ...timeline.map(item => item.orderId));
  const researchHref = d?.links?.research_snapshot || (bi?.symbol ? `/dashboard?symbol=${encodeURIComponent(bi.symbol)}${inputAsOfTime ? `&as_of_time=${encodeURIComponent(inputAsOfTime)}` : ""}` : null);
  const decisionHref = d?.links?.decision_center || (bi?.symbol ? `/decisions?symbol=${encodeURIComponent(bi.symbol)}` : null);
  const replayHref = d?.links?.replay || (linkedReplaySessionId ? `/replay?session_id=${encodeURIComponent(linkedReplaySessionId)}` : null);
  const analyticsHref = d?.links?.analytics || (linkedReplaySessionId
    ? `/analytics?replay_session_id=${encodeURIComponent(linkedReplaySessionId)}${linkedBacktestId ? `&backtest_id=${encodeURIComponent(linkedBacktestId)}` : ""}`
    : linkedBacktestId ? `/analytics?backtest_id=${encodeURIComponent(linkedBacktestId)}` : null);
  const backtestHref = d?.links?.backtest || (linkedBacktestId ? `/backtest?backtest_id=${encodeURIComponent(linkedBacktestId)}` : null);
  const auditExportHref = d?.links?.audit_export;
  const crossLinks = [
    { label: "研究快照", href: researchHref },
    { label: "决策中心", href: decisionHref },
    { label: "历史回放", href: replayHref },
    { label: "回测页", href: backtestHref },
    { label: "回测/回放对比", href: analyticsHref },
    { label: "审计导出", href: auditExportHref },
  ].filter((item): item is { label: string; href: string } => !!item.href);
  const klineCount = firstUsefulNumber(inputBars.length, snap?.barsCount, inputMaterials.barsCount);
  const inputSnapshotGroupCount = firstUsefulNumber(Object.keys(inputSnapshotIds).length, trace?.input_snapshot_id_groups);
  const inputSummaryCards = [
    { label: "价格", value: inputMaterials.price ?? inputSummary.price ?? snap?.price },
    { label: "K线", value: firstUsefulNumber(inputBars.length, inputMaterials.barsCount, inputSummary.bars_count, snap?.barsCount) },
    { label: "新闻", value: firstUsefulNumber(inputNewsEvents.length, inputMaterials.newsCount, inputSummary.news_count, snap?.newsCount, trace?.news_events) },
    { label: "宏观", value: firstUsefulNumber(inputMacroEvents.length, inputMaterials.macroCount, inputSummary.macro_count, snap?.macroCount, trace?.macro_events) },
    { label: "因子键", value: firstUsefulNumber(inputMaterials.factorsCount, Object.keys(inputFactorSnapshot).length, snap?.factorsCount, trace?.factor_snapshots) },
    { label: "信号", value: firstUsefulNumber(inputMaterials.signalsCount, inputRecentSignals.length, snap?.signalsCount, trace?.signal_events) },
    { label: "快照组", value: (inputSnapshotGroupCount || 0) > 0 ? inputSnapshotGroupCount : null },
  ];
  const snapshotCards = [
    { l: "K线", v: (klineCount || 0) > 0 ? klineCount : null, n: (klineCount || 0) > 0 ? null : "仅记录价格" },
    { l: "因子", v: firstUsefulNumber(trace?.factor_snapshots, snap?.factorsCount, inputMaterials.factorsCount, Object.keys(inputFactorSnapshot).length) },
    { l: "信号", v: firstUsefulNumber(trace?.signal_events, snap?.signalsCount, inputMaterials.signalsCount, inputRecentSignals.length) },
    { l: "新闻", v: firstUsefulNumber(inputNewsEvents.length, trace?.news_events, snap?.newsCount, inputMaterials.newsCount, inputSummary.news_count) },
    { l: "宏观", v: firstUsefulNumber(inputMacroEvents.length, trace?.macro_events, snap?.macroCount, inputMaterials.macroCount, inputSummary.macro_count) },
    { l: "角色", v: trace?.role_outputs },
    { l: "意图", v: trace?.order_intent_events },
    { l: "成交", v: trace?.paper_trades },
  ];

  const syntheticAuditCount = firstUsefulNumber(trace?.synthetic_audit_events, d?.syntheticAuditCount, timeline.filter(item => item.synthetic).length) || 0;
  const hasSyntheticAudit = syntheticAuditCount > 0 || timeline.some(item => item.synthetic);
  const derivedOriginalAuditPresent = timeline.some(item => item.eventType === "AGENT_DECISION" && item.synthetic !== true && item.auditSource === "audit_logs");
  const originalAuditPresent = d?.originalAgentDecisionAuditPresent === true || (d?.originalAgentDecisionAuditPresent == null && derivedOriginalAuditPresent);
  const strictReplayAvailable = d?.strictSnapshotReplayAvailable === true || d?.strictSnapshotReplay === true;
  const riskUnavailable = d?.riskUnavailable === true || d?.risk_guard?.riskUnavailable === true || trace?.risk_unavailable === true || timeline.some(item => item.eventType === "RISK_CHECK_UNAVAILABLE" || item.riskUnavailable === true);
  const executionRiskBlocked = d?.risk_guard?.passed === false || trace?.risk_blocked === true || timeline.some(item => item.eventType === "RISK_BLOCKED");
  const decisionRiskVetoReported = dec?.risk_veto != null;
  const decisionRiskVeto = dec?.risk_veto === true;
  const holdRecorded = d?.order_intent?.orderIntentId === "NO_ACTION" || timeline.some(item => item.eventType === "HOLD_RECORDED");
  const orderIntentVisible = !!d?.order_intent?.orderIntentId || (d?.order_intent_events?.length || 0) > 0;
  const paperTradeVisible = d?.execution_result?.paperOrderGenerated === true || (d?.paper_trades?.length || 0) > 0;
  const executionChainVisible = orderIntentVisible || holdRecorded || paperTradeVisible || executionRiskBlocked || riskUnavailable;
  const riskGuardReported = d?.risk_guard?.passed != null || d?.risk_guard?.riskUnavailable === true ||
    trace?.risk_blocked != null || trace?.risk_unavailable != null ||
    timeline.some(item => item.eventType === "RISK_CHECK_PASSED" || item.eventType === "RISK_BLOCKED" || item.eventType === "RISK_CHECK_UNAVAILABLE" || item.riskStatus || item.riskUnavailable === true);
  const noTradeText = executionRiskBlocked ? emptyTextFor("blocked_no_trade") : riskUnavailable ? "风控不可用，已保守阻断成交" : emptyTextFor("no_order");
  const auditHashRows = timeline.map((item, index) => {
    const row = asRecord(item);
    return {
      index,
      id: textOf(row, "id"),
      eventType: String(item.eventType || valueOf(row, "eventType", "event_type") || "AUDIT_EVENT"),
      createdAt: textOf(row, "createdAt", "created_at"),
      payloadHash: textOf(row, "payloadHash", "payload_hash"),
      prevHash: textOf(row, "prevHash", "prev_hash"),
      immutable: item.immutable !== false,
      synthetic: item.synthetic === true,
    };
  });
  const originalAuditRows = auditHashRows.filter(item => !item.synthetic);
  const hashedOriginalRows = originalAuditRows.filter(item => item.payloadHash);
  const hashChainReady = !!linkedRecord?.payloadHash || hashedOriginalRows.length > 0;
  const hashCoverageLabel = originalAuditRows.length > 0
    ? `${hashedOriginalRows.length}/${originalAuditRows.length}`
    : hashChainReady ? "列表记录" : "0/0";
  const detailPayloadHash = firstText(linkedRecord?.payloadHash, ...auditHashRows.map(item => item.payloadHash));
  const detailPrevHash = firstText(linkedRecord?.prevHash, ...auditHashRows.map(item => item.prevHash));

  // ── PIT checks come from backend only; strict replay evidence is shown separately. ──
  const backendChecks = (d?.pit_checks || []).map((check, index) => {
    const key = String(check.key || "");
    const label = String(check.label || check.key || `检查 ${index + 1}`);
    return {
      key,
      label,
      isPit: isPitTimingCheck(key, label),
      ok: boolValue(check.passed),
      detail: detailText(check.detail ?? check.message ?? check),
    };
  });
  const fullGraphCheck = backendChecks.find(check => check.key === "full_graph_execution");
  const pitChecks = backendChecks.filter(check => check.isPit);
  const replayEvidenceChecks = backendChecks.filter(check => !check.isPit && check.key !== "full_graph_execution");
  if (pitChecks.length === 0) {
    pitChecks.push({
      key: "pit_checks_missing",
      label: "后端 PIT 检查",
      isPit: true,
      ok: null,
      detail: "本记录未保存独立 PIT 时点检查；页面不再使用 createdAt 自行判断。",
    });
  }
  const pitHasFailure = pitChecks.some(check => check.ok === false);
  const pitHasUnknown = pitChecks.some(check => check.ok === null);
  const pitHasPass = pitChecks.some(check => check.ok === true);
  const replayEvidenceHasFailure = replayEvidenceChecks.some(check => check.ok === false);
  const replayEvidenceHasUnknown = replayEvidenceChecks.some(check => check.ok === null);
  const replayEvidenceLabel = replayEvidenceHasFailure ? "证据缺失" : replayEvidenceHasUnknown ? "待核验" : "证据完整";
  const isFullGraph = bi?.isFullGraph ?? fullGraphCheck?.ok ?? null;
  const graphMode = bi?.graphMode || null;
  const graphModeText = graphModeLabel(isFullGraph, graphMode);
  const graphModeDetail = isFullGraph === true
    ? `完整 TradingAgentsGraph · ${graphMode || "full_graph"}`
    : isFullGraph === false
      ? `快速研究模式 · ${graphMode || "context_adapter"}`
      : "旧记录未保存执行模式";

  // ── Agent output completeness ──────────────────────────────────────────────
  const agentCompleteness = roleRows.map((e) => {
    const hasOpinion = !!(e.opinion);
    const hasChain = !!(e.data_source_chain);
    const inferredChain = isInferredChain(e.data_source_chain);
    const hasOutput = !!(e.summary || e.reasoning || e.output);
    return { key: e.key, label: e.label || e.role || e.key, hasOpinion, hasChain, inferredChain, hasOutput, dataSourceChain: e.data_source_chain || null };
  });

  // ── Reproducibility ───────────────────────────────────────────────────────
  const snapshotGroupCount = inputSnapshotGroupCount;
  const factorTraceCount = firstUsefulNumber(trace?.factor_snapshots, snap?.factorsCount, inputMaterials.factorsCount, Object.keys(inputFactorSnapshot).length);
  const signalTraceCount = firstUsefulNumber(trace?.signal_events, snap?.signalsCount, inputMaterials.signalsCount, inputRecentSignals.length);
  const reproItems = [
    { label: "快照 ID 组", ok: (snapshotGroupCount || 0) > 0, detail: snapshotGroupCount ? `${snapshotGroupCount} 组` : "旧记录未保存快照 ID 组" },
    { label: "因子快照 ID", ok: (factorTraceCount || 0) > 0, detail: factorTraceCount ? `${factorTraceCount} 条可精确复现` : "旧记录未保存因子快照 ID" },
    { label: "信号事件 ID", ok: (signalTraceCount || 0) > 0, detail: signalTraceCount ? `${signalTraceCount} 条可追溯` : "旧记录未保存信号事件 ID" },
    { label: "模型版本", ok: !!(bi?.model || bi?.agentGraph), detail: `model=${bi?.model || "—"} agentGraph=${bi?.agentGraph || "—"}` },
    { label: "schema", ok: !!d?.schema_version, detail: d?.schema_version || "旧记录未保存 schema" },
    { label: "原始 AGENT_DECISION", ok: originalAuditPresent, detail: originalAuditPresent ? "audit_logs 原始事件存在" : `缺原始事件；synthetic ${syntheticAuditCount} 条` },
    { label: "严格快照回放", ok: strictReplayAvailable, detail: strictReplayAvailable ? "决策时点输入证据可用" : "缺决策时点输入证据，复跑会降级" },
    { label: "完整图执行", ok: isFullGraph === true, detail: graphModeDetail },
  ];
  const acceptanceItems: Array<{ label: string; state: "pass" | "warn" | "fail"; detail: string }> = [
    {
      label: "完整图",
      state: isFullGraph === true ? "pass" : "warn",
      detail: isFullGraph === true ? graphModeDetail : isFullGraph === false ? "当前为快速研究模式，可用于稳定分析，但不计入完整多 Agent 强验收" : "旧记录未保存执行模式，无法证明走过完整图",
    },
    {
      label: "原始审计",
      state: originalAuditPresent ? (hasSyntheticAudit ? "warn" : "pass") : "fail",
      detail: originalAuditPresent ? `原始 AGENT_DECISION 存在${hasSyntheticAudit ? `，另有 synthetic ${syntheticAuditCount} 条` : ""}` : `缺原始 AGENT_DECISION；synthetic ${syntheticAuditCount} 条不能计入通过`,
    },
    {
      label: "Hash 链",
      state: hashChainReady ? "pass" : "warn",
      detail: hashChainReady ? `原始审计 hash 覆盖 ${hashCoverageLabel}` : "旧记录未返回 payloadHash/prevHash，无法在前端展示不可变链",
    },
    {
      label: "输入证据",
      state: strictReplayAvailable ? "pass" : "fail",
      detail: strictReplayAvailable ? "决策时点输入证据已固化，可严格回放" : "缺决策时点输入证据，只能降级复跑",
    },
    {
      label: "PIT 检查",
      state: pitHasFailure ? "fail" : pitHasUnknown || !pitHasPass ? "warn" : "pass",
      detail: pitHasFailure ? "PIT 时点检查未通过，存在未来数据风险" : pitHasUnknown || !pitHasPass ? "本记录未保存完整 PIT 结论" : `${pitChecks.length} 项通过`,
    },
    {
      label: "Synthetic",
      state: hasSyntheticAudit ? "warn" : "pass",
      detail: hasSyntheticAudit ? `${syntheticAuditCount} 条为兼容派生展示，不作为原始审计证据` : "未发现 synthetic 兼容事件",
    },
    {
      label: "RiskGuard",
      state: riskUnavailable ? "warn" : "pass",
      detail: riskUnavailable ? "风控不可用，后端已保守阻断成交" : executionRiskBlocked ? "风控可用，且本次阻断了执行" : "未报告风控不可用",
    },
    {
      label: "执行链",
      state: executionChainVisible ? "pass" : "warn",
      detail: paperTradeVisible ? "已看到模拟成交结果" : orderIntentVisible ? "已看到 OrderIntent/HOLD 草案" : executionRiskBlocked || riskUnavailable ? "执行被风控闭环拦截" : "未看到 OrderIntent、HOLD 或模拟成交",
    },
  ];
  const acceptanceFailures = acceptanceItems.filter(item => item.state === "fail").length;
  const acceptanceWarnings = acceptanceItems.filter(item => item.state === "warn").length;
  const acceptanceLabel = acceptanceFailures > 0 ? "未通过" : acceptanceWarnings > 0 ? "需复核" : "可强验收";
  const acceptanceIssues = acceptanceItems.filter(item => item.state !== "pass");
  const acceptanceTone = acceptanceFailures > 0 ? "fail" : acceptanceWarnings > 0 ? "warn" : "pass";
  const acceptanceToneClasses = {
    fail: {
      ring: "ring-1 ring-red-500/20",
      bar: "h-1 bg-red-500",
      icon: "w-5 h-5 text-red-400",
      badge: "bg-red-500/15 text-red-300",
      panel: "border-red-500/25 bg-red-500/5",
      text: "text-red-100",
    },
    warn: {
      ring: "ring-1 ring-amber-500/20",
      bar: "h-1 bg-amber-500",
      icon: "w-5 h-5 text-amber-400",
      badge: "bg-amber-500/15 text-amber-300",
      panel: "border-amber-500/25 bg-amber-500/5",
      text: "text-amber-100",
    },
    pass: {
      ring: "ring-1 ring-green-500/20",
      bar: "h-1 bg-green-500",
      icon: "w-5 h-5 text-green-400",
      badge: "bg-green-500/15 text-green-300",
      panel: "border-green-500/25 bg-green-500/5",
      text: "text-green-100",
    },
  }[acceptanceTone];
  const advancedFilterCount = [
    filters.executionStatus,
    filters.executionMode,
    filters.decisionId,
    filters.orderIntentId,
    filters.orderId,
    filters.backtestId,
    filters.replaySessionId,
  ].filter(Boolean).length;
  const timeFilterLabel = timeRangeMode === "custom"
    ? (filters.startTime || filters.endTime
      ? `${filters.startTime ? fmtTime(filters.startTime) || filters.startTime : "不限开始"} 至 ${filters.endTime ? fmtTime(filters.endTime) || filters.endTime : "不限结束"}`
      : "自定义时间")
    : timeRangeOptions.find(option => option.value === timeRangeMode)?.label || "全部时间";
  const querySummary = [
    filters.symbol || "全部交易对",
    eventTypeLabel(filters.eventType),
    riskStatusLabel(filters.riskStatus),
    filters.executionStatus ? executionStatusLabel(filters.executionStatus) : null,
    filters.executionMode ? executionModeLabel(filters.executionMode) : null,
    timeFilterLabel,
    advancedFilterCount > 0 ? `高级筛选 ${advancedFilterCount} 项` : null,
    "最近 50 条",
  ].filter(Boolean).join(" · ");
  const recordEvidenceStats = [
    { label: "记录", value: records.length, tone: "text-slate-200", title: "当前筛选返回的审计记录数" },
    { label: "Hash", value: records.filter(row => row.payloadHash).length, tone: records.some(row => row.payloadHash) ? "text-green-300" : "text-amber-300", title: "带 payloadHash 的记录数" },
    { label: "原始", value: records.filter(row => !row.synthetic).length, tone: "text-cyan-200", title: "非 synthetic 兼容行的记录数" },
    { label: "Synthetic", value: records.filter(row => row.synthetic).length, tone: records.some(row => row.synthetic) ? "text-amber-300" : "text-slate-400", title: "兼容派生展示记录数" },
    { label: "FullGraph", value: records.filter(row => row.isFullGraph === true).length, tone: records.some(row => row.isFullGraph === true) ? "text-green-300" : "text-slate-400", title: "完整 TradingAgentsGraph 记录数" },
    { label: "可回放", value: records.filter(row => row.strictSnapshotReplay === true || row.contextHash).length, tone: records.some(row => row.strictSnapshotReplay === true || row.contextHash) ? "text-green-300" : "text-slate-400", title: "有 strictSnapshotReplay 或 contextHash 的记录数" },
    { label: "风控拦截", value: records.filter(row => row.eventType === "RISK_BLOCKED" || row.riskStatus === "blocked").length, tone: records.some(row => row.eventType === "RISK_BLOCKED" || row.riskStatus === "blocked") ? "text-red-300" : "text-slate-400", title: "当前列表中的风控阻断记录数" },
  ];

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <>
      <AppTopNav activeSection="audit" title="决策证据链与可追溯中心" subtitle="能不能被证明 · 能不能回放 · 有没有违规" />
      <div className="container mx-auto px-4 py-4 space-y-5 max-w-7xl">

        {/* ── Records list ────────────────────────────────────────────────── */}
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold text-slate-200">审计查询</p>
              <p className="mt-1 text-[10px] text-slate-500">当前查看：{querySummary}</p>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={fetchRecords} disabled={recordsLoading} className="h-8 gap-1 text-xs">
                <RefreshCw className={"h-3 w-3 " + (recordsLoading ? "animate-spin" : "")} />刷新
              </Button>
              <Button size="sm" variant="outline" onClick={clearFilters} className="h-8 px-2 text-xs">清空</Button>
            </div>
          </div>

          <div className="mb-3 flex flex-wrap gap-1.5">
            {presetFilters.map(preset => {
              const active = Object.entries(preset.filters).every(([key, value]) => filters[key as keyof AuditFilters] === value);
              return (
                <button
                  key={preset.label}
                  type="button"
                  title={preset.description}
                  onClick={() => applyPreset(preset.filters)}
                  className={`rounded border px-2 py-1 text-[10px] ${active ? "border-cyan-400/50 bg-cyan-500/15 text-cyan-100" : "border-slate-800 bg-slate-900/50 text-slate-400 hover:border-slate-700 hover:text-slate-200"}`}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>

          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <label className="space-y-1">
              <span className="text-[9px] text-slate-500">交易对</span>
              <select value={filters.symbol} onChange={e => setFilter("symbol", e.target.value)} className="h-8 w-full rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300">
                <option value="">全部交易对</option>
                {symbolOptions.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[9px] text-slate-500">链路环节</span>
              <select value={filters.eventType} onChange={e => setFilter("eventType", e.target.value)} className="h-8 w-full rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300">
                <option value="">全部链路环节</option>
                {eventTypeOptions.map(v => <option key={v} value={v}>{eventTypeLabels[v]}</option>)}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[9px] text-slate-500">风控状态</span>
              <select value={filters.riskStatus} onChange={e => setFilter("riskStatus", e.target.value)} className="h-8 w-full rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300">
                <option value="">全部风控状态</option>
                {Object.entries(riskStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[9px] text-slate-500">时间范围</span>
              <select value={timeRangeMode} onChange={e => updateTimeRange(e.target.value as TimeRangeMode)} className="h-8 w-full rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300">
                {timeRangeOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
          </div>
          {timeRangeMode === "custom" && (
            <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-4">
              <label className="space-y-1">
                <span className="text-[9px] text-slate-500">开始时间</span>
                <input type="datetime-local" value={filters.startTime} onChange={e => setFilter("startTime", e.target.value)} className="h-8 w-full rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300" />
              </label>
              <label className="space-y-1">
                <span className="text-[9px] text-slate-500">结束时间</span>
                <input type="datetime-local" value={filters.endTime} onChange={e => setFilter("endTime", e.target.value)} className="h-8 w-full rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300" />
              </label>
            </div>
          )}

          <div className="mt-3">
            <button
              type="button"
              onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
              className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-200"
            >
              高级追踪筛选 {advancedFilterCount > 0 && <Badge className="bg-cyan-500/15 text-cyan-300 text-[8px]">{advancedFilterCount}</Badge>}
              {showAdvancedFilters ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
            {showAdvancedFilters && (
              <div className="mt-2 space-y-2">
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
                  <select value={draftAdvancedFilters.executionStatus} onChange={e => setDraftAdvancedFilter("executionStatus", e.target.value)} className="h-8 rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300">
                    <option value="">全部执行状态</option>
                    {executionStatusOptions.map(v => <option key={v} value={v}>{executionStatusLabels[v]}</option>)}
                  </select>
                  <select value={draftAdvancedFilters.executionMode} onChange={e => setDraftAdvancedFilter("executionMode", e.target.value)} className="h-8 rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300">
                    <option value="">全部执行模式</option>
                    {Object.entries(executionModeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                  <input value={draftAdvancedFilters.decisionId} onChange={e => setDraftAdvancedFilter("decisionId", e.target.value)} onKeyDown={handleAdvancedKeyDown} placeholder="决策 ID" className="h-8 rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300 placeholder:text-slate-600" />
                  <input value={draftAdvancedFilters.orderIntentId} onChange={e => setDraftAdvancedFilter("orderIntentId", e.target.value)} onKeyDown={handleAdvancedKeyDown} placeholder="下单意图 ID" className="h-8 rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300 placeholder:text-slate-600" />
                  <input value={draftAdvancedFilters.orderId} onChange={e => setDraftAdvancedFilter("orderId", e.target.value)} onKeyDown={handleAdvancedKeyDown} placeholder="订单 ID" className="h-8 rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300 placeholder:text-slate-600" />
                  <input value={draftAdvancedFilters.backtestId} onChange={e => setDraftAdvancedFilter("backtestId", e.target.value)} onKeyDown={handleAdvancedKeyDown} placeholder="回测 ID" className="h-8 rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300 placeholder:text-slate-600" />
                  <input value={draftAdvancedFilters.replaySessionId} onChange={e => setDraftAdvancedFilter("replaySessionId", e.target.value)} onKeyDown={handleAdvancedKeyDown} placeholder="回放 Session ID" className="h-8 rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300 placeholder:text-slate-600" />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="outline" onClick={applyAdvancedFilters} className="h-7 px-2 text-[10px]">查询高级筛选</Button>
                  <Button size="sm" variant="ghost" onClick={() => setDraftAdvancedFilters(advancedFiltersFrom(filters))} className="h-7 px-2 text-[10px] text-slate-500">还原输入</Button>
                  <span className="text-[9px] text-slate-600">高级 ID 输入按 Enter 或点查询后才会刷新列表。</span>
                </div>
              </div>
            )}
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
            {recordEvidenceStats.map(item => (
              <div key={item.label} title={item.title} className="rounded border border-slate-800 bg-slate-900/40 px-2 py-1.5">
                <p className="text-[9px] text-slate-500">{item.label}</p>
                <p className={`text-sm font-semibold ${item.tone}`}>{item.value}</p>
              </div>
            ))}
          </div>

          {records.length > 0 && <div className="mt-2 text-right text-[10px] text-slate-500">{records.length} 条记录</div>}
        </div>
        {error && <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-400">{error}</div>}

        <Card className="border-slate-700/50 bg-slate-950/60">
          <CardHeader className="pb-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-sm">审计记录列表</CardTitle>
              <span className="text-[10px] text-slate-500">查询结果 {records.length} 条</span>
            </div>
          </CardHeader>
          <CardContent>
            {recordsLoading ? <p className="text-xs text-slate-500 py-4 text-center">加载中...</p>
              : records.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-800 bg-slate-900/30 px-3 py-6 text-center">
                  <p className="text-xs text-slate-400">没有匹配的审计记录</p>
                  <p className="mt-1 text-[10px] text-slate-600">可以清空筛选，或把时间范围放宽后重新查看。</p>
                </div>
              )
              : <div className="space-y-1 max-h-[320px] overflow-y-auto">
                {records.map(r => {
                  const decisionReference = r.decisionId || r.sourceDecisionId || r.replayDecisionId;
                  const detailDecisionId = r.decisionId ? Number(r.decisionId) : null;
                  const canOpenDetail = detailDecisionId != null && Number.isFinite(detailDecisionId);
                  const selected = selectedId === detailDecisionId;
                  const hasHash = !!r.payloadHash;
                  const hasContextHash = !!r.contextHash;
                  const immutableState = r.immutable === false ? "fail" : hasHash ? "pass" : "neutral";
                  const graphState = r.isFullGraph === true ? "pass" : r.isFullGraph === false ? "warn" : "neutral";
                  const snapshotState = r.strictSnapshotReplay === true || hasContextHash ? "pass" : "neutral";
                  return (
                    <div
                      key={`${r.id}-${r.eventType}`}
                      onClick={() => canOpenDetail ? fetchDetail(detailDecisionId) : null}
                      className={`rounded-lg border p-2 text-[11px] ${canOpenDetail ? "cursor-pointer" : "cursor-default opacity-80"} ${selected ? "border-cyan-500/50 bg-cyan-500/10" : canOpenDetail ? "border-slate-800 bg-slate-900/30 hover:border-slate-700" : "border-slate-800 bg-slate-900/20"}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex min-w-0 flex-wrap items-center gap-2">
                          <span className="font-mono text-slate-600 text-[10px]">#{r.id || "—"}</span>
                          <Badge title={r.eventType} className={`${eventTypeBadgeClass(r.eventType)} text-[9px]`}>{eventTypeLabel(r.eventType)}</Badge>
                          <span className="truncate text-slate-300">{r.symbol || "全部交易对"}</span>
                          {r.action && <Badge title={r.action} className={`${actionBadgeClass(r.action)} text-[8px]`}>{actionLabel(r.action)}</Badge>}
                          {r.synthetic && <Badge className="bg-amber-500/15 text-amber-300 text-[8px]">兼容派生</Badge>}
                        </div>
                        <span className="shrink-0 text-slate-600 text-[10px]">{fmtTime(r.createdAt) || "—"}</span>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[9px] text-slate-500">
                        <span className="font-mono">决策 #{decisionReference || "—"}</span>
                        {r.riskStatus && <Badge title={r.riskStatus} className={`${riskBadgeClass(r.riskStatus)} text-[8px]`}>{riskStatusLabel(r.riskStatus)}</Badge>}
                        {r.executionStatus && <Badge title={r.executionStatus} className="bg-slate-800 text-slate-300 text-[8px]">{executionStatusLabel(r.executionStatus)}</Badge>}
                        {r.executionMode && <Badge title={r.executionMode} className="bg-slate-800 text-slate-300 text-[8px]">{executionModeLabel(r.executionMode)}</Badge>}
                        {r.orderIntentId && <span className="truncate max-w-[180px]">下单意图 {r.orderIntentId}</span>}
                        {r.orderId && <span className="truncate max-w-[180px]">订单 {r.orderId}</span>}
                        {r.backtestId && <span className="truncate max-w-[140px]">回测 {r.backtestId}</span>}
                        {r.replaySessionId && <span className="truncate max-w-[180px]">回放 {r.replaySessionId}</span>}
                        {canOpenDetail ? <span className="text-cyan-500/80">可打开详情</span> : <span className="text-slate-600">仅列表记录</span>}
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[9px] text-slate-500">
                        <EvidenceBadge label="Immutable" state={immutableState} title={r.immutable === false ? "后端返回 immutable=false" : hasHash ? "有 payloadHash，可作为不可变审计证据" : "未返回 payloadHash，通常是旧记录或兼容记录"} />
                        <EvidenceBadge label="Hash" state={hasHash ? "pass" : "warn"} title={r.payloadHash || "未返回 payloadHash"} />
                        <EvidenceBadge label="Snapshot" state={snapshotState} title={r.contextHash || "未返回 contextHash/strictSnapshotReplay"} />
                        <EvidenceBadge label="FullGraph" state={graphState} title={r.isFullGraph === true ? "完整 TradingAgentsGraph" : r.isFullGraph === false ? "快速研究模式，不计入完整图强验收" : "未返回图执行模式"} />
                        {r.synthetic && <EvidenceBadge label="Synthetic" state="warn" title="兼容派生展示，不作为原始不可变审计证据" />}
                        {r.payloadHash && (
                          <button
                            type="button"
                            title={r.payloadHash}
                            onClick={(event) => { event.stopPropagation(); copyToClipboard(r.payloadHash); }}
                            className="inline-flex h-5 items-center gap-1 rounded border border-slate-700 bg-slate-950/50 px-1.5 font-mono text-[8px] text-slate-400 hover:border-cyan-500/40 hover:text-cyan-200"
                          >
                            <Copy className="h-2.5 w-2.5" />{shortHash(r.payloadHash)}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            }
          </CardContent>
        </Card>

        {entryDecisionIds.length > 1 && !detailLoading && (
          <Card className="border-amber-500/30 bg-amber-500/5">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2 text-amber-100">
                <AlertTriangle className="h-4 w-4 text-amber-300" />该入口关联多个决策
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {entryDecisionIds.map(id => (
                <Button key={id} size="sm" variant="outline" className="h-8 text-xs" onClick={() => fetchDetail(id)}>
                  打开决策 #{id}
                </Button>
              ))}
            </CardContent>
          </Card>
        )}

        {detailLoading && <p className="text-xs text-slate-500 py-8 text-center"><RefreshCw className="h-4 w-4 animate-spin inline mr-2" />加载审计详情...</p>}

        {d && !detailLoading && (
          <>
            {/* ═══ 1. Audit Conclusion ═════════════════════════════════════ */}
            <Card className={`border-slate-700/50 bg-slate-950/60 overflow-hidden ${acceptanceToneClasses.ring}`}>
              <div className={acceptanceToneClasses.bar} />
              <CardContent className="p-4 space-y-3">
                <div className={`rounded-lg border p-3 ${acceptanceToneClasses.panel}`}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-2">
                      <Shield className={`${acceptanceToneClasses.icon} shrink-0 mt-0.5`} />
                      <div className="min-w-0">
                        <p className={`text-base font-semibold ${acceptanceToneClasses.text}`}>当前审计：{acceptanceLabel}</p>
                        <p className="mt-1 text-[10px] text-slate-400">
                          {acceptanceIssues.length > 0 ? `${acceptanceFailures} 个阻断 · ${acceptanceWarnings} 个需复核` : "原始审计、输入证据、PIT 检查和执行链路均满足当前强验收条件。"}
                        </p>
                      </div>
                    </div>
                    <Badge className={`${acceptanceToneClasses.badge} text-[10px]`}>{acceptanceLabel}</Badge>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {acceptanceIssues.length > 0 ? acceptanceIssues.slice(0, 5).map(item => (
                      <span
                        key={`issue-${item.label}`}
                        title={item.detail}
                        className={`rounded border px-2 py-1 text-[10px] ${item.state === "fail" ? "border-red-500/25 bg-red-500/10 text-red-200" : "border-amber-500/25 bg-amber-500/10 text-amber-200"}`}
                      >
                        {item.label}：{item.detail}
                      </span>
                    )) : (
                      <span className="rounded border border-green-500/20 bg-green-500/10 px-2 py-1 text-[10px] text-green-200">未发现需要人工复核的关键原因</span>
                    )}
                    {acceptanceIssues.length > 5 && <span className="rounded border border-slate-700 bg-slate-900/50 px-2 py-1 text-[10px] text-slate-400">另有 {acceptanceIssues.length - 5} 项</span>}
                  </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-7 gap-2">
                  {acceptanceItems.map(item => {
                    const ok = item.state === "pass";
                    const warn = item.state === "warn";
                    return (
                      <div key={item.label} className={`rounded-lg border p-2 ${ok ? "border-green-500/20 bg-green-500/5" : warn ? "border-amber-500/20 bg-amber-500/5" : "border-red-500/20 bg-red-500/5"}`}>
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-[10px] font-semibold text-slate-300">{item.label}</p>
                          {ok ? <CheckCircle className="w-3.5 h-3.5 text-green-400" /> : warn ? <AlertTriangle className="w-3.5 h-3.5 text-amber-400" /> : <XCircle className="w-3.5 h-3.5 text-red-400" />}
                        </div>
                        <p className="mt-1 text-[10px] leading-4 text-slate-500">{item.detail}</p>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* ═══ 2. Decision Identity ════════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60 overflow-hidden">
              <div className="h-1 bg-cyan-500" />
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Hash className="w-4 h-4 text-cyan-400" />#{bi?.decisionId || selectedId}
                  <span className="text-[10px] text-slate-500 font-normal">{bi?.symbol || "—"} · {fmtTime(bi?.createdAt) || "—"}</span>
                  <Badge className={`${isFullGraph === true ? "bg-green-500/15 text-green-300" : isFullGraph === false ? "bg-amber-500/15 text-amber-300" : "bg-slate-500/15 text-slate-300"} text-[10px]`}>
                    {graphModeText}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {[
                    { l: "模型", v: bi?.modelVersion || bi?.model }, { l: "适配器", v: bi?.agentGraph },
                    { l: "执行模式", v: graphModeDetail },
                    { l: "数据源", v: bi?.source }, { l: "schema", v: d?.schema_version },
                    { l: "contextId", v: bi?.contextId }, { l: "contextHash", v: bi?.contextHash },
                    { l: "availableTime", v: fmtTime(bi?.availableTime) || fmtTime(bi?.createdAt) },
                    { l: "审计时间", v: fmtTime(d?.generated_at) }, { l: "决策状态", v: bi?.status || (dec?.risk_veto ? "risk_veto" : "created") },
                  ].map(m => (
                    <div key={m.l} className="rounded border border-slate-800 bg-slate-900/40 p-1.5">
                      <p className="text-[9px] text-slate-500">{m.l}</p>
                      <p className={`text-[10px] truncate ${m.v ? "text-slate-300" : "text-slate-600 italic"}`}>{m.v || NA}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="text-[10px] text-slate-500">闭环跳转：</span>
                  {crossLinks.length > 0 ? crossLinks.map(link => (
                    <a key={`${link.label}-${link.href}`} href={link.href} className="rounded border border-cyan-500/20 bg-cyan-500/5 px-2 py-1 text-[10px] text-cyan-200 hover:border-cyan-400/40 hover:text-cyan-100">
                      {link.label}
                    </a>
                  )) : <span className="text-[10px] text-slate-600 italic">{NA}</span>}
                </div>
                <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2">
                  {[
                    { l: "OrderIntent", v: linkedOrderIntentId },
                    { l: "OrderId", v: linkedOrderId },
                    { l: "backtestId", v: linkedBacktestId },
                    { l: "replaySessionId", v: linkedReplaySessionId },
                  ].map(item => (
                    <div key={item.l} className="rounded border border-slate-800 bg-slate-900/30 px-2 py-1.5 min-w-0">
                      <p className="text-[9px] text-slate-500">{item.l}</p>
                      <p className={`text-[10px] font-mono truncate ${item.v ? "text-slate-300" : "text-slate-600 italic"}`}>{item.v || NA}</p>
                    </div>
                  ))}
                </div>
                {(!originalAuditPresent || !strictReplayAvailable || hasSyntheticAudit || riskUnavailable || isFullGraph !== true) && (
                  <div className="mt-3 space-y-2">
                    {isFullGraph !== true && (
                      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[10px] text-amber-200">
                        {isFullGraph === false ? "当前记录来自快速研究模式，可用于稳定/批量分析，不计入完整 TradingAgentsGraph 多 Agent 强验收。" : "当前旧记录未保存执行模式，无法证明它走过完整 TradingAgentsGraph。"}
                      </div>
                    )}
                    {!originalAuditPresent && (
                      <div className="rounded-lg border border-red-500/25 bg-red-500/5 px-3 py-2 text-[10px] text-red-200">
                        缺原始 AGENT_DECISION 审计事件：当前只能兼容展示，不能算作强验收通过。
                      </div>
                    )}
                    {!strictReplayAvailable && (
                      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[10px] text-amber-200">
                        缺决策时点输入证据：严格回放不可用，复跑会降级为 PIT 重建上下文。
                      </div>
                    )}
                    {hasSyntheticAudit && (
                      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[10px] text-amber-200">
                        有 {syntheticAuditCount} 条时间线事件来自后端派生展示，不是 audit_logs 原始不可变事件。
                      </div>
                    )}
                    {riskUnavailable && (
                      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[10px] text-amber-200">
                        执行风控曾不可用，后端按保守策略阻断成交。
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ═══ 3. Immutable Hash Chain ═════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Hash className="w-4 h-4 text-cyan-400" />不可变 Hash 链
                  <Badge className={`${hashChainReady ? "bg-green-500/15 text-green-300" : "bg-amber-500/15 text-amber-300"} text-[9px]`}>
                    {hashChainReady ? `覆盖 ${hashCoverageLabel}` : "待补证据"}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {[
                    { l: "原始事件", v: originalAuditRows.length, tone: originalAuditRows.length > 0 ? "text-slate-200" : "text-amber-300" },
                    { l: "已带 hash", v: hashedOriginalRows.length, tone: hashedOriginalRows.length > 0 ? "text-green-300" : "text-amber-300" },
                    { l: "synthetic", v: auditHashRows.filter(item => item.synthetic).length, tone: hasSyntheticAudit ? "text-amber-300" : "text-slate-300" },
                    { l: "immutable=false", v: auditHashRows.filter(item => !item.immutable).length, tone: auditHashRows.some(item => !item.immutable) ? "text-red-300" : "text-green-300" },
                  ].map(item => (
                    <div key={item.l} className="rounded border border-slate-800 bg-slate-900/40 p-2">
                      <p className="text-[9px] text-slate-500">{item.l}</p>
                      <p className={`text-lg font-semibold ${item.tone}`}>{item.v}</p>
                    </div>
                  ))}
                </div>
                <div className="grid md:grid-cols-2 gap-2">
                  {[
                    { label: "当前 payloadHash", value: detailPayloadHash },
                    { label: "当前 prevHash", value: detailPrevHash },
                  ].map(item => (
                    <div key={item.label} className="rounded border border-slate-800 bg-slate-900/40 p-2 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[9px] text-slate-500">{item.label}</p>
                        {item.value && (
                          <button type="button" onClick={() => copyToClipboard(item.value)} className="text-slate-500 hover:text-cyan-300" title="复制">
                            <Copy className="h-3 w-3" />
                          </button>
                        )}
                      </div>
                      <p title={item.value || ""} className={`mt-1 truncate font-mono text-[10px] ${item.value ? "text-slate-300" : "text-slate-600 italic"}`}>
                        {item.value ? shortHash(item.value, 22, 12) : "后端未返回"}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="rounded border border-slate-800 bg-slate-900/30">
                  <div className="grid grid-cols-[72px_1fr_1fr_88px] gap-2 border-b border-slate-800 px-2 py-1.5 text-[9px] text-slate-500">
                    <span>事件</span>
                    <span>payloadHash</span>
                    <span>prevHash</span>
                    <span>证据</span>
                  </div>
                  <div className="max-h-[260px] overflow-auto">
                    {auditHashRows.length === 0 ? (
                      <p className="px-3 py-4 text-center text-[10px] text-slate-600">本记录未返回 audit_timeline hash 字段。</p>
                    ) : auditHashRows.slice(0, 40).map(item => (
                      <div key={`${item.eventType}-${item.index}`} className="grid grid-cols-[72px_1fr_1fr_88px] gap-2 border-b border-slate-900 px-2 py-1.5 text-[9px]">
                        <div className="min-w-0">
                          <p className="truncate text-slate-300" title={item.eventType}>{item.eventType}</p>
                          <p className="font-mono text-[8px] text-slate-600">#{item.id || item.index + 1}</p>
                        </div>
                        <button type="button" onClick={() => copyToClipboard(item.payloadHash)} disabled={!item.payloadHash} title={item.payloadHash || "无 payloadHash"} className={`min-w-0 truncate text-left font-mono ${item.payloadHash ? "text-cyan-200 hover:text-cyan-100" : "text-slate-700"}`}>
                          {item.payloadHash ? shortHash(item.payloadHash, 18, 10) : "—"}
                        </button>
                        <button type="button" onClick={() => copyToClipboard(item.prevHash)} disabled={!item.prevHash} title={item.prevHash || "无 prevHash"} className={`min-w-0 truncate text-left font-mono ${item.prevHash ? "text-slate-300 hover:text-cyan-100" : "text-slate-700"}`}>
                          {item.prevHash ? shortHash(item.prevHash, 18, 10) : "—"}
                        </button>
                        <div className="flex flex-wrap gap-1">
                          <EvidenceBadge label={item.immutable ? "Imm" : "Mut"} state={item.immutable ? "pass" : "fail"} />
                          {item.synthetic && <EvidenceBadge label="Syn" state="warn" />}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                {!hashChainReady && (
                  <div className="rounded border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[10px] text-amber-200">
                    当前详情缺少 payloadHash/prevHash 字段，通常表示旧记录或迁移前数据；它仍可用于排查，但不能作为完整不可变审计证据。
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ═══ 3. Unified Input Snapshot ════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800/50 bg-slate-900/40 cursor-pointer" onClick={() => setShowSnapshot(!showSnapshot)}>
                <Database className="w-4 h-4 text-cyan-400" />
                <p className="text-sm font-semibold text-white flex-1">统一输入快照 — 决策时用了哪些数据</p>
                {showSnapshot ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
              </div>
              {showSnapshot && (
                <CardContent className="p-4">
                  <div className="grid grid-cols-4 md:grid-cols-8 gap-2 mb-3">
                    {snapshotCards.map(s => (
                      <div key={s.l} className="rounded-lg border border-slate-800 bg-slate-900/40 p-2 text-center">
                        <p className={`text-lg font-bold ${s.n ? "text-amber-400" : "text-slate-200"}`}>{s.v != null ? s.v : "—"}</p>
                        <p className="text-[9px] text-slate-500">{s.l}</p>
                        {s.n && <p className="text-[8px] text-amber-500/80">{s.n}</p>}
                      </div>
                    ))}
                  </div>
                  <div className="text-[10px] text-slate-500 space-x-4">
                    <span>provider: {snap?.dataProvider || NA}</span>
                    <span>availableTime: {fmtTime(snap?.availableTime) || NA}</span>
                    <span>asOfTime: {fmtTime(snap?.asOfTime) || NA}</span>
                  </div>
                  {Object.keys(normalizedSnapshot).length > 0 && (
                    <div className="mt-3 grid md:grid-cols-3 gap-2">
                      {[
                        { l: "证据 schema", v: normalizedSnapshot.schema_version },
                        { l: "输入证据 contextHash", v: normalizedSnapshot.context_hash },
                        { l: "输入证据 as-of time", v: fmtTime(String(normalizedSnapshot.as_of_time || "")) || normalizedSnapshot.as_of_time },
                      ].map(item => (
                        <div key={item.l} className="rounded border border-cyan-500/20 bg-cyan-500/5 p-2 min-w-0">
                          <p className="text-[9px] text-cyan-200/70">{item.l}</p>
                          <p className="text-[10px] text-cyan-100 font-mono truncate">{String(item.v || NA)}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/30 p-3">
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <p className="text-[11px] font-semibold text-slate-200">具体数据材料</p>
                      <Badge className="bg-slate-800 text-slate-400 text-[9px]">{inputMaterials.source || "审计输入"}</Badge>
                      <Badge className={`${detailCompleteness.hasNormalizedSnapshot ? "bg-green-500/15 text-green-300" : "bg-amber-500/15 text-amber-300"} text-[9px]`}>
                        {detailCompleteness.hasNormalizedSnapshot ? "原始快照已固化" : "摘要/ID 兜底"}
                      </Badge>
                    </div>
                    {detailCompletenessNote && (
                      <div className="mb-2 rounded border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[10px] text-amber-200">
                        {detailCompletenessNote}
                      </div>
                    )}
                    {Object.keys(countsSource).length > 0 && (
                      <div className="mb-2 flex flex-wrap gap-1.5">
                        {Object.entries(countsSource).map(([name, source]) => (
                          <span key={name} className="rounded bg-slate-950/60 px-2 py-1 text-[9px] text-slate-500">
                            {name}: <span className="text-slate-300">{shortValue(source, 60)}</span>
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="grid xl:grid-cols-2 gap-2">
                      <MaterialPanel title="K线明细" count={inputBars.length} empty={(klineCount || 0) > 0 ? "旧记录只保存了 K 线数量/元数据，未保存逐条 OHLCV。" : undefined}>
                        <div className="max-h-[300px] overflow-auto">
                          <table className="w-full text-[9px]">
                            <thead className="sticky top-0 bg-slate-950 text-slate-500">
                              <tr>
                                <th className="py-1 pr-2 text-left font-normal">event_time</th>
                                <th className="py-1 pr-2 text-right font-normal">O</th>
                                <th className="py-1 pr-2 text-right font-normal">H</th>
                                <th className="py-1 pr-2 text-right font-normal">L</th>
                                <th className="py-1 pr-2 text-right font-normal">C</th>
                                <th className="py-1 text-right font-normal">V</th>
                              </tr>
                            </thead>
                            <tbody>
                              {inputBars.slice(-24).map((bar, idx) => (
                                <tr key={materialKey("bar", bar, idx)} className="border-t border-slate-900 text-slate-300">
                                  <td className="py-1 pr-2 font-mono text-slate-500">{timeOf(bar, "event_time", "timestamp", "time", "t")}</td>
                                  <td className="py-1 pr-2 text-right font-mono">{formatValue(valueOf(bar, "open", "o"))}</td>
                                  <td className="py-1 pr-2 text-right font-mono">{formatValue(valueOf(bar, "high", "h"))}</td>
                                  <td className="py-1 pr-2 text-right font-mono">{formatValue(valueOf(bar, "low", "l"))}</td>
                                  <td className="py-1 pr-2 text-right font-mono text-slate-100">{formatValue(valueOf(bar, "close", "c"))}</td>
                                  <td className="py-1 text-right font-mono">{formatValue(valueOf(bar, "volume", "v"))}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-2 text-[8px] text-slate-600">
                          <span>available: {inputBars.length ? timeOf(inputBars[inputBars.length - 1], "available_time", "availableTime", "close_time") : "—"}</span>
                          <span>provider: {inputBars.length ? textOf(inputBars[inputBars.length - 1], "provider", "data_provider", "source") || "—" : "—"}</span>
                        </div>
                      </MaterialPanel>

                      <MaterialPanel title="新闻事件" count={inputNewsEvents.length} empty={(inputMaterials.newsCount || 0) > 0 ? "旧记录只保存了新闻数量，未保存逐条新闻标题/来源。" : undefined}>
                        <div className="space-y-1 max-h-[300px] overflow-auto pr-1">
                          {inputNewsEvents.map((news, idx) => {
                            const title = textOf(news, "title", "headline", "summary", "name") || `新闻 #${idx + 1}`;
                            const url = textOf(news, "url", "link");
                            return (
                              <div key={materialKey("news", news, idx)} className="rounded bg-slate-900/70 px-2 py-1.5 text-[9px]">
                                <div className="flex items-start justify-between gap-2">
                                  {url ? <a href={url} target="_blank" rel="noreferrer" className="text-slate-200 hover:text-cyan-200">{compactText(title, 120)}</a> : <p className="text-slate-200">{compactText(title, 120)}</p>}
                                  <span className="shrink-0 font-mono text-slate-600">#{idx + 1}</span>
                                </div>
                                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-slate-500">
                                  <span>{textOf(news, "source", "provider", "publisher") || "source —"}</span>
                                  <span>{timeOf(news, "published_at", "event_time", "timestamp", "date")}</span>
                                  <span>available {timeOf(news, "available_time", "availableTime")}</span>
                                  {valueOf(news, "sentiment_score", "sentiment") != null && <span>sentiment {formatValue(valueOf(news, "sentiment_score", "sentiment"))}</span>}
                                  {listValue(valueOf(news, "tags", "symbols"), 4) && <span>{listValue(valueOf(news, "tags", "symbols"), 4)}</span>}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </MaterialPanel>

                      <MaterialPanel title="宏观事件" count={inputMacroEvents.length} empty={(inputMaterials.macroCount || 0) > 0 ? "旧记录只保存了宏观数量，未保存逐条指标。" : undefined}>
                        <div className="space-y-1 max-h-[260px] overflow-auto pr-1">
                          {inputMacroEvents.map((macro, idx) => (
                            <div key={materialKey("macro", macro, idx)} className="rounded bg-slate-900/70 px-2 py-1.5 text-[9px]">
                              <div className="flex items-center justify-between gap-2">
                                <span className="truncate text-slate-200">{textOf(macro, "indicator", "name", "series_id", "metric") || `macro #${idx + 1}`}</span>
                                <span className="shrink-0 font-mono text-slate-100">{formatValue(valueOf(macro, "value", "actual", "latest_value"))}</span>
                              </div>
                              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-slate-500">
                                <span>{textOf(macro, "source", "provider") || "source —"}</span>
                                <span>{timeOf(macro, "event_time", "timestamp", "date", "period")}</span>
                                <span>available {timeOf(macro, "available_time", "availableTime")}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </MaterialPanel>

                      <MaterialPanel title="因子证据" count={inputFactorEvidence.length || Object.keys(inputFactorSnapshot).length}>
                        <div className="space-y-1 max-h-[260px] overflow-auto pr-1">
                          {inputFactorEvidence.length > 0 ? inputFactorEvidence.map((factor, idx) => (
                            <div key={materialKey("factor", factor, idx)} className="rounded bg-slate-900/70 px-2 py-1.5 text-[9px]">
                              <div className="flex items-center justify-between gap-2">
                                <span className="truncate text-slate-300">{textOf(factor, "factorName", "factor_name", "displayName", "snapshotId") || `factor #${idx + 1}`}</span>
                                <span className="shrink-0 font-mono text-slate-100">{formatValue(valueOf(factor, "value", "factorValue", "factor_value"))}</span>
                              </div>
                              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-slate-500">
                                <span>{textOf(factor, "dataProvider", "provider", "data_source") || "provider —"}</span>
                                <span>available {timeOf(factor, "availableTime", "available_time")}</span>
                                <span>version {textOf(factor, "dataVersion", "sourceVersion", "schemaVersion") || "—"}</span>
                                {factor.pitRulePassed != null && <span className={factor.pitRulePassed === false ? "text-red-300" : "text-green-300"}>PIT {String(factor.pitRulePassed)}</span>}
                              </div>
                            </div>
                          )) : Object.entries(inputFactorSnapshot).map(([name, value]) => (
                            <div key={name} className="flex items-center justify-between gap-2 rounded bg-slate-900/70 px-2 py-1 text-[9px]">
                              <span className="text-slate-400 truncate">{name}</span>
                              <span className="text-slate-200 font-mono shrink-0">{formatValue(value)}</span>
                            </div>
                          ))}
                        </div>
                      </MaterialPanel>

                      <MaterialPanel title="信号事件" count={inputSignalEvents.length}>
                        <div className="space-y-1 max-h-[260px] overflow-auto pr-1">
                          {inputSignalEvents.map((sig, idx) => (
                            <div key={materialKey("signal", sig, idx)} className="rounded bg-slate-900/70 px-2 py-1.5 text-[9px] text-slate-300">
                              <div className="flex items-center justify-between gap-2">
                                <span className="truncate">{textOf(sig, "source_strategy", "strategy", "strategy_id") || "strategy"} · {textOf(sig, "signal_type", "type") || "—"}</span>
                                <span className="shrink-0 font-mono">{formatValue(valueOf(sig, "confidence", "conf", "signal_value"))}</span>
                              </div>
                              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-slate-500">
                                <span>{timeOf(sig, "event_time", "timestamp", "time")}</span>
                                <span>available {timeOf(sig, "available_time", "availableTime")}</span>
                                <span>{textOf(sig, "provider", "data_source") || "provider —"}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </MaterialPanel>

                      <MaterialPanel title="快照 ID / 版本" count={Object.keys(inputSnapshotIds).length + Object.keys(asRecord(snap?.dataVersions ?? normalizedSnapshot.data_versions)).length}>
                        <div className="grid gap-2 md:grid-cols-2">
                          <pre className="max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded bg-slate-900/70 p-2 text-[9px] leading-4 text-slate-300">{prettyJson(inputSnapshotIds)}</pre>
                          <pre className="max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded bg-slate-900/70 p-2 text-[9px] leading-4 text-slate-300">{prettyJson({ dataVersions: snap?.dataVersions ?? normalizedSnapshot.data_versions ?? null, barMeta: snap?.barMeta ?? normalizedSnapshot.bars_summary ?? null })}</pre>
                        </div>
                      </MaterialPanel>
                    </div>
                  </div>
                </CardContent>
              )}
            </Card>

            {/* ═══ 4. Per-Agent Data Materials ══════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800/50 bg-slate-900/40 cursor-pointer" onClick={() => setShowRoles(!showRoles)}>
                <Layers className="w-4 h-4 text-cyan-400" />
                <p className="text-sm font-semibold text-white flex-1">Agent 输入材料 — 每个 AI 当时看到了什么</p>
                <Badge className="text-[10px]">{roleRows.length} 个</Badge>
                {showRoles ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
              </div>
              {showRoles && (
                <CardContent className="p-4 space-y-2">
                  {roleRows.length === 0 ? <p className="text-xs text-slate-500 py-4 text-center">{emptyTextFor("role_outputs")}（role_outputs / agent_analysis）</p>
                    : <>
                      <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-3">
                        <div className="flex flex-wrap items-center gap-2 mb-3">
                          <p className="text-[11px] font-semibold text-cyan-100">本次决策共享输入快照</p>
                          <Badge className="bg-cyan-500/10 text-cyan-200 text-[9px]">AnalysisContext</Badge>
                          <span className="text-[9px] text-cyan-200/60">每个角色使用同一决策时点上下文；下面按角色回放输入管道、可见摘要和完整输出。</span>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
                          {inputSummaryCards.map(item => (
                            <div key={item.label} className="rounded border border-slate-800 bg-slate-950/40 p-2">
                              <p className="text-[9px] text-slate-500">{item.label}</p>
                              <p className="text-[11px] text-slate-200 font-mono truncate">{formatValue(item.value)}</p>
                            </div>
                          ))}
                        </div>
                        {Object.keys(inputFactorSnapshot).length > 0 && (
                          <div className="mt-3 rounded border border-slate-800 bg-slate-950/40 p-2">
                            <p className="text-[9px] text-slate-500 mb-1">AI 可见因子快照</p>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5">
                              {Object.entries(inputFactorSnapshot).slice(0, 16).map(([name, value]) => (
                                <div key={name} className="flex items-center justify-between gap-2 rounded bg-slate-900/70 px-2 py-1 text-[9px]">
                                  <span className="text-slate-400 truncate">{name}</span>
                                  <span className="text-slate-200 font-mono shrink-0">{formatValue(value)}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {inputRecentSignals.length > 0 && (
                          <div className="mt-2 rounded border border-slate-800 bg-slate-950/40 p-2">
                            <p className="text-[9px] text-slate-500 mb-1">AI 可见近期信号</p>
                            <div className="flex flex-wrap gap-1.5">
                              {inputRecentSignals.slice(0, 12).map((sig, idx) => (
                                <span key={`${sig.strategy || "signal"}-${idx}`} className="rounded bg-slate-900/80 px-2 py-1 text-[9px] text-slate-300">
                                  {String(sig.strategy || "strategy")} · {String(sig.type || "—")} · {formatValue(sig.conf)}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                      {roleRows.map((e) => {
                      const outputText = e.summary || e.reasoning || e.output;
                      const keyPoints = e.key_points || [];
                      return (
                        <div key={`${e.key}-${e.index || ""}`} className="rounded-lg border border-slate-800 bg-slate-900/30 p-2.5">
                          <div className="flex items-center justify-between gap-2">
                            <div>
                              <p className="text-[11px] font-semibold text-slate-200">{e.label || e.role || e.key}</p>
                              <p className="text-[9px] text-slate-500 font-mono">
                                {e.phase ? `${e.phase} · ` : ""}{e.role || e.key}
                              </p>
                            </div>
                            <div className="flex items-center gap-1">
                              {e.index != null && <Badge className="bg-slate-800 text-slate-400 text-[9px]">#{e.index}</Badge>}
                              {e.opinion ? <Badge className="bg-slate-700/50 text-slate-400 text-[9px]">{e.opinion}</Badge> : <span className="text-[9px] text-slate-600">未给出方向</span>}
                              {e.confidence != null && <span className="text-[9px] text-slate-500">{formatPct(e.confidence)}</span>}
                              {e.risk_flag && <Badge className="bg-red-500/15 text-red-300 text-[9px]">risk</Badge>}
                            </div>
                          </div>
                          <div className="mt-2 rounded border border-slate-800 bg-slate-950/40 p-2">
                            <p className="text-[9px] text-slate-500 mb-1">输入 — 系统提供的数据管道</p>
                            {e.data_source_chain ? (
                              <p className="text-[10px] text-slate-300 font-mono">{e.data_source_chain}</p>
                            ) : (
                              <p className="text-[10px] text-slate-600 italic">旧记录未保存输入管道（data_source_chain 为空）</p>
                            )}
                            <div className="grid grid-cols-2 md:grid-cols-6 gap-1.5 mt-2">
                              {inputSummaryCards.map(item => (
                                <div key={`${e.key}-${item.label}`} className="rounded bg-slate-900/60 px-2 py-1">
                                  <p className="text-[8px] text-slate-600">{item.label}</p>
                                  <p className="text-[9px] text-slate-300 font-mono truncate">{formatValue(item.value)}</p>
                                </div>
                              ))}
                            </div>
                            {keyPoints.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-2">
                                {keyPoints.slice(0, 4).map(point => (
                                  <span key={point} className="rounded bg-cyan-500/10 px-2 py-0.5 text-[9px] text-cyan-200/80">{point}</span>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="mt-1 rounded border border-slate-800 bg-slate-950/40 p-2">
                            <p className="text-[9px] text-slate-500 mb-1">输出 — {outputText ? "已记录" : "无输出"}</p>
                            {outputText ? (
                              <>
                                <p className="text-[10px] text-slate-400 leading-4">{compactText(outputText)}</p>
                                <details className="mt-2 rounded border border-slate-800 bg-slate-900/50 px-2 py-1">
                                  <summary className="cursor-pointer text-[9px] text-cyan-300">查看完整输出（{String(outputText).length} 字）</summary>
                                  <pre className="mt-2 max-h-[420px] overflow-auto whitespace-pre-wrap break-words text-[10px] leading-4 text-slate-300">{String(outputText)}</pre>
                                </details>
                              </>
                            ) : <p className="text-[10px] text-slate-600 italic">该角色未产生输出摘要</p>}
                          </div>
                        </div>
                      );
                    })}
                  </>}
                </CardContent>
              )}
            </Card>

            {/* ═══ 5. Agent Output Completeness ════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2"><FileSearch className="w-4 h-4 text-cyan-400" />Agent 输出完整性</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {agentCompleteness.map(a => (
                    <div key={a.key} className="flex items-center gap-3 text-[10px] py-1">
                      <span className="text-slate-300 w-32 truncate">{a.label}</span>
                      <span className="flex items-center gap-1">{a.hasOpinion ? <CheckCircle className="w-3 h-3 text-green-400" /> : <XCircle className="w-3 h-3 text-red-400" />}方向</span>
                      <span className="flex items-center gap-1">
                        {a.hasChain && !a.inferredChain ? <CheckCircle className="w-3 h-3 text-green-400" /> : a.hasChain ? <AlertTriangle className="w-3 h-3 text-amber-400" /> : <XCircle className="w-3 h-3 text-slate-500" />}
                        数据源{a.inferredChain ? "（推断）" : ""}
                      </span>
                      <span className="flex items-center gap-1">{a.hasOutput ? <CheckCircle className="w-3 h-3 text-green-400" /> : <XCircle className="w-3 h-3 text-red-400" />}输出</span>
                    </div>
                  ))}
                </div>
                {agentCompleteness.length === 0 && <p className="text-xs text-slate-600 py-4 text-center">{emptyTextFor("role_outputs")}（agent_analysis）</p>}
              </CardContent>
            </Card>

            {/* ═══ 6. Future Function Check ════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800/50 bg-slate-900/40 cursor-pointer" onClick={() => setShowFutureCheck(!showFutureCheck)}>
                <Filter className="w-4 h-4 text-amber-400" />
                <p className="text-sm font-semibold text-white flex-1">PIT 检查</p>
                <Badge className={`text-[10px] ${pitHasFailure ? "bg-red-500/15 text-red-400" : pitHasUnknown ? "bg-amber-500/15 text-amber-400" : "bg-green-500/15 text-green-400"}`}>
                  {pitHasFailure ? "有风险" : pitHasUnknown ? "待核验" : "通过"}
                </Badge>
                {showFutureCheck ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
              </div>
              {showFutureCheck && (
                <CardContent className="p-4 space-y-2">
                  {pitChecks.map((c, i) => (
                    <div key={i} className={`rounded-lg border p-2.5 flex items-start gap-2 ${c.ok === true ? "border-green-500/20 bg-green-500/5" : c.ok === false ? "border-red-500/20 bg-red-500/5" : "border-slate-800 bg-slate-900/30"}`}>
                      {c.ok === true ? <CheckCircle className="w-4 h-4 text-green-400 shrink-0 mt-0.5" /> : c.ok === false ? <XCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" /> : <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />}
                      <div>
                        <p className="text-[11px] font-semibold text-slate-300">{c.label}</p>
                        <p className="text-[10px] text-slate-500 mt-0.5">{c.detail}</p>
                      </div>
                    </div>
                  ))}
                  {replayEvidenceChecks.length > 0 && (
                    <div className={`rounded-lg border p-2.5 ${replayEvidenceHasFailure ? "border-amber-500/25 bg-amber-500/5" : replayEvidenceHasUnknown ? "border-slate-700 bg-slate-900/30" : "border-green-500/20 bg-green-500/5"}`}>
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[11px] font-semibold text-slate-300">严格回放证据</p>
                        <Badge className={`text-[10px] ${replayEvidenceHasFailure ? "bg-amber-500/15 text-amber-300" : replayEvidenceHasUnknown ? "bg-slate-500/15 text-slate-300" : "bg-green-500/15 text-green-300"}`}>
                          {replayEvidenceLabel}
                        </Badge>
                      </div>
                      <p className="mt-1 text-[10px] text-slate-500">这里失败表示旧记录缺严格快照、contextHash 或原始审计证据，不等同于发现未来函数。</p>
                      <div className="mt-2 space-y-1">
                        {replayEvidenceChecks.map((c, i) => (
                          <div key={`${c.key}-${i}`} className="flex items-start gap-2 text-[10px] text-slate-500">
                            {c.ok === true ? <CheckCircle className="w-3 h-3 text-green-400 shrink-0 mt-0.5" /> : c.ok === false ? <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" /> : <AlertTriangle className="w-3 h-3 text-slate-500 shrink-0 mt-0.5" />}
                            <span className="text-slate-400">{c.label}</span>
                            <span className="truncate">{c.detail}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              )}
            </Card>

            {/* ═══ 7. Decision Chain ════════════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800/50 bg-slate-900/40 cursor-pointer" onClick={() => setShowChain(!showChain)}>
                <ScrollText className="w-4 h-4 text-cyan-400" />
                <p className="text-sm font-semibold text-white flex-1">决策链路</p>
                {showChain ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
              </div>
              {showChain && (
                <CardContent className="p-4 space-y-3">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {[
                      { l: "Agent 风控否决", ok: decisionRiskVetoReported && !decisionRiskVeto, warn: !decisionRiskVetoReported, veto: decisionRiskVeto, d: decisionRiskVeto ? "已否决" : decisionRiskVetoReported ? "未否决" : "未记录 Agent 风控结论" },
                      { l: "RiskGuard 拦截", ok: executionRiskBlocked === false && !riskUnavailable, warn: riskUnavailable, veto: executionRiskBlocked && !riskUnavailable, d: riskUnavailable ? "风控不可用" : executionRiskBlocked ? "已拦截" : "未拦截" },
                      { l: "RiskGuard 可用性", ok: riskGuardReported && !riskUnavailable, warn: !riskGuardReported || riskUnavailable, veto: false, d: riskUnavailable ? "不可用" : riskGuardReported ? "可用或未报告异常" : emptyTextFor("risk_not_run") },
                      { l: "OrderIntent/HOLD", ok: orderIntentVisible || holdRecorded, warn: !orderIntentVisible && !holdRecorded, veto: false, d: holdRecorded ? "HOLD 已记录" : d?.order_intent?.orderIntentId || emptyTextFor("no_order") },
                      { l: "模拟成交", ok: paperTradeVisible, warn: !paperTradeVisible && (executionRiskBlocked || riskUnavailable), veto: false, d: paperTradeVisible ? `${d?.execution_result?.orderId || "—"} @ ${d?.execution_result?.fillPrice || "—"}` : noTradeText },
                      { l: "原始审计", ok: originalAuditPresent, warn: hasSyntheticAudit, veto: !originalAuditPresent, d: d?.audit_timeline?.length ? `${d.audit_timeline.length} 条 · synthetic ${syntheticAuditCount}` : "未保存原始时间线" },
                      { l: "严格回放", ok: strictReplayAvailable, warn: !strictReplayAvailable, veto: false, d: strictReplayAvailable ? "输入证据可用" : "缺严格快照/contextHash" },
                    ].map(s => (
                      <div key={s.l} className={`rounded-xl border p-3 ${s.ok ? "border-green-500/30 bg-green-500/5" : s.veto ? "border-red-500/30 bg-red-500/5" : s.warn ? "border-amber-500/30 bg-amber-500/5" : "border-slate-800 bg-slate-900/30"}`}>
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-[10px] text-slate-400 font-semibold">{s.l}</p>
                          {s.ok ? <CheckCircle className="w-3 h-3 text-green-400" /> : s.veto ? <Shield className="w-3 h-3 text-red-400" /> : s.warn ? <AlertTriangle className="w-3 h-3 text-amber-400" /> : <XCircle className="w-3 h-3 text-slate-500" />}
                        </div>
                        <p className="text-[10px] text-slate-500">{String(s.d)}</p>
                      </div>
                    ))}
                  </div>
                  {d?.order_intent?.reason && (
                    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-2">
                      <p className="text-[9px] text-slate-500 mb-1">OrderIntent 原因</p>
                      <p className="text-[10px] text-slate-400">{d.order_intent.reason}</p>
                    </div>
                  )}
                </CardContent>
              )}
            </Card>

            {/* ═══ 8. Reproducibility ═══════════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800/50 bg-slate-900/40 cursor-pointer" onClick={() => setShowRepro(!showRepro)}>
                <GitCompare className="w-4 h-4 text-purple-400" />
                <p className="text-sm font-semibold text-white flex-1">可复现性</p>
                <Badge className={`text-[10px] ${reproItems.filter(r => r.ok).length >= 4 ? "bg-green-500/15 text-green-400" : "bg-amber-500/15 text-amber-400"}`}>
                  {reproItems.filter(r => r.ok).length}/{reproItems.length}
                </Badge>
                {showRepro ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
              </div>
              {showRepro && (
                <CardContent className="p-4 space-y-1.5">
                  {reproItems.map((r, i) => (
                    <div key={i} className="flex items-center gap-2 text-[10px]">
                      {r.ok ? <CheckCircle className="w-3.5 h-3.5 text-green-400 shrink-0" /> : <XCircle className="w-3.5 h-3.5 text-slate-500 shrink-0" />}
                      <span className="text-slate-400 w-24 shrink-0">{r.label}</span>
                      <span className="text-slate-500">{r.detail}</span>
                    </div>
                  ))}
                </CardContent>
              )}
            </Card>

            {/* ═══ 9. Replay Runs ═══════════════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <GitCompare className="w-4 h-4 text-cyan-400" />复跑结果
                  <Badge className="bg-slate-800 text-slate-400 text-[9px]">{replayRuns.length} 条</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 space-y-2">
                {replayRuns.length === 0 ? <p className="text-xs text-slate-600 py-2">{emptyTextFor("replay_runs")}（replay_runs）</p>
                  : replayRuns.map((run, index) => {
                    const diff = asRecord(run.diffSummary);
                    const actionChanged = diff.actionChanged === true;
                    const contextChanged = diff.contextHashChanged === true;
                    return (
                      <div key={`${run.id || "replay"}-${index}`} className="rounded-lg border border-slate-800 bg-slate-900/30 p-2.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge className={`${run.status === "completed" ? "bg-green-500/15 text-green-300" : run.status === "failed" ? "bg-red-500/15 text-red-300" : "bg-amber-500/15 text-amber-300"} text-[9px]`}>
                            {replayStatusLabel(run.status || run.eventType)}
                          </Badge>
                          <span className="text-[10px] text-slate-400">源决策 #{run.sourceDecisionId || "—"}</span>
                          <span className="text-[10px] text-slate-500">→</span>
                          {run.replayDecisionId ? (
                            <button onClick={() => fetchDetail(Number(run.replayDecisionId))} className="text-[10px] text-cyan-300 hover:text-cyan-200">
                              复跑决策 #{run.replayDecisionId}
                            </button>
                          ) : <span className="text-[10px] text-slate-500">复跑决策 —</span>}
                          <span className="ml-auto text-[10px] text-slate-600">{fmtTime(run.createdAt) || "—"}</span>
                        </div>
                        <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2">
                          <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
                            <p className="text-[9px] text-slate-500">动作变化</p>
                            <p className={`text-[10px] ${actionChanged ? "text-amber-300" : "text-slate-300"}`}>
                              {String(diff.originalAction || "—")} → {String(diff.replayAction || "—")}
                            </p>
                          </div>
                          <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
                            <p className="text-[9px] text-slate-500">置信度差</p>
                            <p className="text-[10px] text-slate-300 font-mono">{formatValue(diff.confidenceDelta)}</p>
                          </div>
                          <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
                            <p className="text-[9px] text-slate-500">上下文变化</p>
                            <p className={`text-[10px] ${contextChanged ? "text-amber-300" : "text-slate-300"}`}>{contextChanged ? "已变化" : "未变化或未知"}</p>
                          </div>
                          <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
                            <p className="text-[9px] text-slate-500">风险否决</p>
                            <p className="text-[10px] text-slate-300">{String(diff.originalRiskVeto ?? "—")} → {String(diff.replayRiskVeto ?? "—")}</p>
                          </div>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px]">
                          <Badge className={`${run.strictSnapshotReplay ? "bg-green-500/15 text-green-300" : "bg-amber-500/15 text-amber-300"} text-[9px]`}>
                            {run.strictSnapshotReplay ? "严格快照" : "降级复跑"}
                          </Badge>
                          <span className="text-slate-500">方法：{replayMethodLabel(run.replayMethod)}</span>
                          {run.fallbackReason && <span className="text-amber-300">{run.fallbackReason}</span>}
                        </div>
                        {run.error && <p className="mt-2 text-[10px] text-red-300">{run.error}</p>}
                      </div>
                    );
                  })}
              </CardContent>
            </Card>

            {/* ═══ 10. Export ═══════════════════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <CardContent className="p-3 flex flex-wrap items-center gap-3">
                <span className="text-xs text-slate-400">导出：</span>
                {d?.links?.audit_export && <a href={d.links.audit_export} target="_blank" className="text-cyan-500 hover:text-cyan-400 text-xs flex items-center gap-1"><Download className="w-3 h-3" />审计 JSON</a>}
                <Button size="sm" variant="outline" className="h-7 text-[10px] gap-1"
                  onClick={() => { const blob = new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `audit-${selectedId || "export"}.json`; a.click(); URL.revokeObjectURL(url); }}>
                  <Download className="w-3 h-3" />导出当前审计详情
                </Button>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </>
  );
}
