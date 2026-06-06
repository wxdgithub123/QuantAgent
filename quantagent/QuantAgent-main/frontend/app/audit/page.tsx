"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import {
  RefreshCw, ChevronDown, ChevronUp,
  CheckCircle, Shield, XCircle, AlertTriangle,
  Database, Layers, ScrollText, Hash, GitCompare, Download, Filter, FileSearch
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────
interface AuditRecord {
  id: number | null; eventType: string; symbol?: string | null;
  asOfTime?: string | null; decisionId?: number | string | null;
  action?: string | null; createdAt?: string | null;
}

interface AgentAnalysisEntry {
  role?: string; label?: string; opinion?: string; confidence?: number | null;
  summary?: string; reasoning?: string; data_source_chain?: string; output?: string; available?: boolean;
  index?: number; phase?: string; risk_flag?: boolean; key_points?: string[];
}

type JsonRecord = Record<string, unknown>;

interface AuditTimelineEntry extends Record<string, unknown> {
  inputSummary?: JsonRecord;
}

interface AgentRoleView extends AgentAnalysisEntry {
  key: string;
}

interface InputMaterials {
  source?: string;
  price?: unknown;
  riskNotes?: unknown;
  snapshotIds?: JsonRecord;
  factorSnapshot?: JsonRecord;
  recentSignals?: unknown[];
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
  diffSummary?: JsonRecord;
  auditUrl?: string | null;
  error?: string | null;
  createdAt?: string | null;
}

interface DecisionAuditDetail {
  schema_version?: string; generated_at?: string;
  basic_info?: { decisionId?: number; symbol?: string; action?: string; confidence?: number; status?: string; createdAt?: string; model?: string; agentGraph?: string; source?: string; contextId?: string; contextHash?: string; availableTime?: string; modelVersion?: string; promptVersion?: string };
  agent_analysis?: Record<string, AgentAnalysisEntry>;
  decision?: { final_signal?: string; risk_veto?: boolean; vote_breakdown?: Record<string, number> };
  input_snapshot?: { snapshotId?: JsonRecord; barsCount?: number; newsCount?: number; factorsCount?: number; signalsCount?: number; macroCount?: number; price?: number; dataProvider?: string; asOfTime?: string; availableTime?: string; factorSnapshot?: JsonRecord; recentSignals?: unknown[] };
  trace_summary?: { factor_snapshots?: number; signal_events?: number; news_events?: number; macro_events?: number; role_outputs?: number; order_intent_events?: number; paper_trades?: number; risk_blocked?: boolean; input_snapshot_id_groups?: number; replay_runs?: number };
  risk_guard?: { passed?: boolean | null; blockedReason?: string | null };
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
  links?: { research_snapshot?: string; audit_export?: string };
}

const NA = "后端未返回";
const fmtTime = (t?: string | null) => t ? new Date(t).toLocaleString("zh-CN") : null;
const formatPct = (v?: number | null) => v != null ? (v * 100).toFixed(0) + "%" : "—";
const asRecord = (value: unknown): JsonRecord => value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
const asArray = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const formatValue = (value: unknown) => typeof value === "number" ? Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 4 }) : value != null ? String(value) : "—";
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
const compactText = (value: unknown, max = 260) => {
  const text = value == null ? "" : String(value);
  return text.length > max ? `${text.slice(0, max)}...` : text;
};
const prettyJson = (value: unknown) => {
  try { return JSON.stringify(value, null, 2); }
  catch { return String(value); }
};

export default function AuditPage() {
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [filterSymbol, setFilterSymbol] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DecisionAuditDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSnapshot, setShowSnapshot] = useState(true);
  const [showRoles, setShowRoles] = useState(true);
  const [showFutureCheck, setShowFutureCheck] = useState(true);
  const [showChain, setShowChain] = useState(true);
  const [showRepro, setShowRepro] = useState(true);

  const fetchRecords = useCallback(async () => {
    setRecordsLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (filterSymbol) params.set("symbol", filterSymbol);
      const res = await fetch("/api/v1/audit/records?" + params.toString());
      if (!res.ok) throw new Error("HTTP " + res.status);
      setRecords(((await res.json()).data || []) as AuditRecord[]);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "加载失败"); }
    finally { setRecordsLoading(false); }
  }, [filterSymbol]);

  const fetchDetail = useCallback(async (id: number) => {
    setDetailLoading(true); setSelectedId(id); setError(null);
    try {
      const res = await fetch("/api/v1/audit/decisions/" + id);
      if (!res.ok) throw new Error("HTTP " + res.status);
      setDetail(await res.json());
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "加载失败"); setDetail(null); }
    finally { setDetailLoading(false); }
  }, []);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const decisionId = Number(params.get("decision_id"));
    if (Number.isFinite(decisionId) && decisionId > 0) {
      fetchDetail(decisionId);
      return;
    }

    const resolveDecisionId = async () => {
      const firstDecisionId = (value: unknown) => {
        const n = Number(value);
        return Number.isFinite(n) && n > 0 ? n : null;
      };
      const auditId = Number(params.get("audit_id"));
      if (Number.isFinite(auditId) && auditId > 0) {
        const res = await fetch(`/api/v1/audit/records/${auditId}`);
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        return firstDecisionId(data?.audit_record?.decisionId);
      }

      const recordsParams = new URLSearchParams({ limit: "50" });
      const orderIntentId = params.get("order_intent_id");
      const orderId = params.get("order_id");
      const backtestId = params.get("backtest_id");
      const replaySessionId = params.get("replay_session_id");
      if (orderIntentId) recordsParams.set("orderIntentId", orderIntentId);
      else if (orderId) recordsParams.set("orderId", orderId);
      else if (backtestId) recordsParams.set("backtestId", backtestId);
      else if (replaySessionId) recordsParams.set("replaySessionId", replaySessionId);
      else return null;

      const res = await fetch("/api/v1/audit/records?" + recordsParams.toString());
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      const rows = ((data?.data || []) as AuditRecord[]);
      setRecords(rows);
      return rows.map(row => firstDecisionId(row?.decisionId)).find((id): id is number => id != null) ?? null;
    };

    resolveDecisionId()
      .then(id => { if (id) fetchDetail(id); })
      .catch(e => setError(e instanceof Error ? e.message : "无法解析审计入口"));
  }, [fetchDetail]);

  const d = detail;
  const bi = d?.basic_info;
  const dec = d?.decision;
  const aa = d?.agent_analysis || {};
  const snap = d?.input_snapshot;
  const trace = d?.trace_summary;
  const evidence = d?.factor_evidence || [];
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
  const inputFactorSnapshot = asRecord(inputMaterials.factorSnapshot ?? inputSummary.factor_snapshot ?? snap?.factorSnapshot);
  const inputSnapshotIds = asRecord(inputMaterials.snapshotIds ?? inputSummary.snapshot_ids ?? snap?.snapshotId);
  const inputRecentSignals = asArray(inputMaterials.recentSignals ?? inputSummary.recent_signals ?? snap?.recentSignals).filter(item => item && typeof item === "object") as JsonRecord[];
  const klineCount = firstUsefulNumber(snap?.barsCount, inputMaterials.barsCount);
  const inputSnapshotGroupCount = firstUsefulNumber(Object.keys(inputSnapshotIds).length, trace?.input_snapshot_id_groups);
  const inputSummaryCards = [
    { label: "价格", value: inputMaterials.price ?? inputSummary.price ?? snap?.price },
    { label: "新闻", value: firstUsefulNumber(inputMaterials.newsCount, inputSummary.news_count, snap?.newsCount, trace?.news_events) },
    { label: "宏观", value: firstUsefulNumber(inputMaterials.macroCount, inputSummary.macro_count, snap?.macroCount, trace?.macro_events) },
    { label: "因子键", value: firstUsefulNumber(inputMaterials.factorsCount, Object.keys(inputFactorSnapshot).length, snap?.factorsCount, trace?.factor_snapshots) },
    { label: "信号", value: firstUsefulNumber(inputMaterials.signalsCount, inputRecentSignals.length, snap?.signalsCount, trace?.signal_events) },
    { label: "快照组", value: (inputSnapshotGroupCount || 0) > 0 ? inputSnapshotGroupCount : null },
  ];
  const snapshotCards = [
    { l: "K线", v: (klineCount || 0) > 0 ? klineCount : null, n: (klineCount || 0) > 0 ? null : "仅记录价格" },
    { l: "因子", v: firstUsefulNumber(trace?.factor_snapshots, snap?.factorsCount, inputMaterials.factorsCount, Object.keys(inputFactorSnapshot).length) },
    { l: "信号", v: firstUsefulNumber(trace?.signal_events, snap?.signalsCount, inputMaterials.signalsCount, inputRecentSignals.length) },
    { l: "新闻", v: firstUsefulNumber(trace?.news_events, snap?.newsCount, inputMaterials.newsCount, inputSummary.news_count) },
    { l: "宏观", v: firstUsefulNumber(trace?.macro_events, snap?.macroCount, inputMaterials.macroCount, inputSummary.macro_count) },
    { l: "角色", v: trace?.role_outputs },
    { l: "意图", v: trace?.order_intent_events },
    { l: "成交", v: trace?.paper_trades },
  ];

  // ── Future function check ──────────────────────────────────────────────────
  const decisionTime = bi?.createdAt ? new Date(bi.createdAt) : null;
  const snapTime = snap?.availableTime || snap?.asOfTime;
  const futureChecks = [
    {
      label: "快照时间 ≤ 决策时间",
      ok: snapTime && decisionTime ? new Date(snapTime) <= decisionTime : null,
      detail: `availableTime: ${fmtTime(snapTime) || NA} · 决策: ${fmtTime(bi?.createdAt) || NA}`,
    },
    {
      label: "因子证据无未来数据",
      ok: evidence.length > 0 && decisionTime ? evidence.every(e => {
        const at = (e as Record<string,unknown>).availableTime as string;
        return !at || new Date(at) <= decisionTime;
      }) : null,
      detail: evidence.length > 0 ? `${evidence.length} 条因子证据` : "后端未返回 factor_evidence",
    },
    {
      label: "风控状态一致性",
      ok: trace?.risk_blocked === dec?.risk_veto,
      detail: `trace.risk_blocked=${trace?.risk_blocked ?? "—"} · decision.risk_veto=${dec?.risk_veto ?? "—"}`,
    },
    {
      label: "意图→成交链路一致",
      ok: d?.execution_result?.paperOrderGenerated ? (d?.paper_trades?.length || 0) > 0 : null,
      detail: `order_intent: ${d?.order_intent?.orderIntentId || "—"} · paper_trades: ${d?.paper_trades?.length || 0} · exec: ${d?.execution_result?.paperOrderGenerated ?? "—"}`,
    },
  ];

  // ── Agent output completeness ──────────────────────────────────────────────
  const agentCompleteness = roleRows.map((e) => {
    const hasOpinion = !!(e.opinion);
    const hasChain = !!(e.data_source_chain);
    const hasOutput = !!(e.summary || e.reasoning || e.output);
    return { key: e.key, label: e.label || e.role || e.key, hasOpinion, hasChain, hasOutput, dataSourceChain: e.data_source_chain || null };
  });

  // ── Reproducibility ───────────────────────────────────────────────────────
  const snapshotGroupCount = inputSnapshotGroupCount;
  const factorTraceCount = firstUsefulNumber(trace?.factor_snapshots, snap?.factorsCount, inputMaterials.factorsCount, Object.keys(inputFactorSnapshot).length);
  const signalTraceCount = firstUsefulNumber(trace?.signal_events, snap?.signalsCount, inputMaterials.signalsCount, inputRecentSignals.length);
  const reproItems = [
    { label: "快照 ID 组", ok: (snapshotGroupCount || 0) > 0, detail: snapshotGroupCount ? `${snapshotGroupCount} 组` : NA },
    { label: "因子快照 ID", ok: (factorTraceCount || 0) > 0, detail: factorTraceCount ? `${factorTraceCount} 条可精确复现` : NA },
    { label: "信号事件 ID", ok: (signalTraceCount || 0) > 0, detail: signalTraceCount ? `${signalTraceCount} 条可追溯` : NA },
    { label: "模型版本", ok: !!(bi?.model || bi?.agentGraph), detail: `model=${bi?.model || "—"} agentGraph=${bi?.agentGraph || "—"}` },
    { label: "schema", ok: !!d?.schema_version, detail: d?.schema_version || NA },
    { label: "审计时间线", ok: (d?.audit_timeline?.length || 0) > 0, detail: d?.audit_timeline?.length ? `${d.audit_timeline.length} 条` : NA },
  ];

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <>
      <AppTopNav activeSection="audit" title="决策证据链与可追溯中心" subtitle="能不能被证明 · 能不能回放 · 有没有违规" />
      <div className="container mx-auto px-4 py-4 space-y-5 max-w-7xl">

        {/* ── Records list ────────────────────────────────────────────────── */}
        <div className="flex flex-wrap items-center gap-2">
          <select value={filterSymbol} onChange={e => setFilterSymbol(e.target.value)} className="h-8 rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300">
            <option value="">全部标的</option>
            {["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","DOGEUSDT"].map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={fetchRecords} disabled={recordsLoading} className="h-8 gap-1 text-xs">
            <RefreshCw className={"h-3 w-3 " + (recordsLoading ? "animate-spin" : "")} />刷新
          </Button>
          {records.length > 0 && <span className="text-[10px] text-slate-500 ml-auto">{records.length} 条记录</span>}
        </div>
        {error && <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-400">{error}</div>}

        <Card className="border-slate-700/50 bg-slate-950/60">
          <CardHeader className="pb-2"><CardTitle className="text-sm">审计记录列表</CardTitle></CardHeader>
          <CardContent>
            {recordsLoading ? <p className="text-xs text-slate-500 py-4 text-center">加载中...</p>
              : records.length === 0 ? <p className="text-xs text-slate-500 py-4 text-center">暂无记录</p>
              : <div className="space-y-1 max-h-[250px] overflow-y-auto">
                {records.map(r => (
                  <div key={`${r.id}-${r.eventType}`} onClick={() => r.decisionId ? fetchDetail(Number(r.decisionId)) : null}
                    className={`rounded-lg border p-2 flex items-center justify-between gap-2 text-[11px] cursor-pointer ${selectedId === (r.decisionId ? Number(r.decisionId) : null) ? "border-cyan-500/50 bg-cyan-500/10" : "border-slate-800 bg-slate-900/30 hover:border-slate-700"}`}>
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-mono text-slate-600 text-[10px]">#{r.id || "—"}</span>
                      <Badge className="bg-slate-700/50 text-slate-400 text-[9px]">{r.eventType}</Badge>
                      <span className="text-slate-300 truncate">{r.symbol || "—"}</span>
                    </div>
                    <span className="text-slate-600 text-[10px] shrink-0">{fmtTime(r.createdAt) || "—"}</span>
                  </div>
                ))}
              </div>
            }
          </CardContent>
        </Card>

        {detailLoading && <p className="text-xs text-slate-500 py-8 text-center"><RefreshCw className="h-4 w-4 animate-spin inline mr-2" />加载审计详情...</p>}

        {d && !detailLoading && (
          <>
            {/* ═══ 1. Decision Identity ════════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60 overflow-hidden">
              <div className="h-1 bg-cyan-500" />
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Hash className="w-4 h-4 text-cyan-400" />#{bi?.decisionId || selectedId}
                  <span className="text-[10px] text-slate-500 font-normal">{bi?.symbol || "—"} · {fmtTime(bi?.createdAt) || "—"}</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {[
                    { l: "模型", v: bi?.modelVersion || bi?.model }, { l: "适配器", v: bi?.agentGraph },
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
              </CardContent>
            </Card>

            {/* ═══ 2. Unified Input Snapshot ════════════════════════════════ */}
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
                  <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/30 p-3">
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <p className="text-[11px] font-semibold text-slate-200">具体数据材料</p>
                      <Badge className="bg-slate-800 text-slate-400 text-[9px]">{inputMaterials.source || "audit input"}</Badge>
                    </div>
                    <div className="grid md:grid-cols-3 gap-2">
                      <div className="rounded border border-slate-800 bg-slate-950/40 p-2 min-w-0">
                        <p className="text-[9px] text-slate-500 mb-1">因子快照键值</p>
                        {Object.keys(inputFactorSnapshot).length > 0 ? (
                          <div className="space-y-1 max-h-[220px] overflow-auto pr-1">
                            {Object.entries(inputFactorSnapshot).map(([name, value]) => (
                              <div key={name} className="flex items-center justify-between gap-2 rounded bg-slate-900/70 px-2 py-1 text-[9px]">
                                <span className="text-slate-400 truncate">{name}</span>
                                <span className="text-slate-200 font-mono shrink-0">{formatValue(value)}</span>
                              </div>
                            ))}
                          </div>
                        ) : <p className="text-[10px] text-slate-600 italic">{NA}</p>}
                      </div>
                      <div className="rounded border border-slate-800 bg-slate-950/40 p-2 min-w-0">
                        <p className="text-[9px] text-slate-500 mb-1">近期信号</p>
                        {inputRecentSignals.length > 0 ? (
                          <div className="space-y-1 max-h-[220px] overflow-auto pr-1">
                            {inputRecentSignals.map((sig, idx) => (
                              <div key={`${sig.strategy || sig.source_strategy || "signal"}-${idx}`} className="rounded bg-slate-900/70 px-2 py-1 text-[9px] text-slate-300">
                                <span className="font-mono text-slate-500">#{idx + 1}</span>{" "}
                                {String(sig.strategy || sig.source_strategy || "strategy")} · {String(sig.type || sig.signal_type || "—")} · {formatValue(sig.conf ?? sig.confidence)}
                              </div>
                            ))}
                          </div>
                        ) : <p className="text-[10px] text-slate-600 italic">{NA}</p>}
                      </div>
                      <div className="rounded border border-slate-800 bg-slate-950/40 p-2 min-w-0">
                        <p className="text-[9px] text-slate-500 mb-1">Snapshot ID 组</p>
                        {Object.keys(inputSnapshotIds).length > 0 ? (
                          <pre className="max-h-[220px] overflow-auto whitespace-pre-wrap break-words text-[9px] leading-4 text-slate-300">{prettyJson(inputSnapshotIds)}</pre>
                        ) : <p className="text-[10px] text-slate-600 italic">{NA}</p>}
                      </div>
                    </div>
                  </div>
                </CardContent>
              )}
            </Card>

            {/* ═══ 3. Per-Agent Data Materials ══════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800/50 bg-slate-900/40 cursor-pointer" onClick={() => setShowRoles(!showRoles)}>
                <Layers className="w-4 h-4 text-cyan-400" />
                <p className="text-sm font-semibold text-white flex-1">Agent 输入材料 — 每个 AI 当时看到了什么</p>
                <Badge className="text-[10px]">{roleRows.length} 个</Badge>
                {showRoles ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
              </div>
              {showRoles && (
                <CardContent className="p-4 space-y-2">
                  {roleRows.length === 0 ? <p className="text-xs text-slate-500 py-4 text-center">后端未返回 role_outputs / agent_analysis</p>
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
                              {e.opinion ? <Badge className="bg-slate-700/50 text-slate-400 text-[9px]">{e.opinion}</Badge> : <span className="text-[9px] text-slate-600">{NA}</span>}
                              {e.confidence != null && <span className="text-[9px] text-slate-500">{formatPct(e.confidence)}</span>}
                              {e.risk_flag && <Badge className="bg-red-500/15 text-red-300 text-[9px]">risk</Badge>}
                            </div>
                          </div>
                          <div className="mt-2 rounded border border-slate-800 bg-slate-950/40 p-2">
                            <p className="text-[9px] text-slate-500 mb-1">输入 — 系统提供的数据管道</p>
                            {e.data_source_chain ? (
                              <p className="text-[10px] text-slate-300 font-mono">{e.data_source_chain}</p>
                            ) : (
                              <p className="text-[10px] text-slate-600 italic">后端未记录（data_source_chain 为空）</p>
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

            {/* ═══ 4. Agent Output Completeness ════════════════════════════ */}
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
                      <span className="flex items-center gap-1">{a.hasChain ? <CheckCircle className="w-3 h-3 text-green-400" /> : <XCircle className="w-3 h-3 text-slate-500" />}数据源</span>
                      <span className="flex items-center gap-1">{a.hasOutput ? <CheckCircle className="w-3 h-3 text-green-400" /> : <XCircle className="w-3 h-3 text-red-400" />}输出</span>
                    </div>
                  ))}
                </div>
                {agentCompleteness.length === 0 && <p className="text-xs text-slate-600 py-4 text-center">{NA}（agent_analysis）</p>}
              </CardContent>
            </Card>

            {/* ═══ 5. Future Function Check ════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800/50 bg-slate-900/40 cursor-pointer" onClick={() => setShowFutureCheck(!showFutureCheck)}>
                <Filter className="w-4 h-4 text-amber-400" />
                <p className="text-sm font-semibold text-white flex-1">未来函数检查</p>
                <Badge className={`text-[10px] ${futureChecks.some(c => c.ok === false) ? "bg-red-500/15 text-red-400" : futureChecks.some(c => c.ok === null) ? "bg-amber-500/15 text-amber-400" : "bg-green-500/15 text-green-400"}`}>
                  {futureChecks.filter(c => c.ok === false).length > 0 ? "有风险" : "通过"}
                </Badge>
                {showFutureCheck ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
              </div>
              {showFutureCheck && (
                <CardContent className="p-4 space-y-2">
                  {futureChecks.map((c, i) => (
                    <div key={i} className={`rounded-lg border p-2.5 flex items-start gap-2 ${c.ok === true ? "border-green-500/20 bg-green-500/5" : c.ok === false ? "border-red-500/20 bg-red-500/5" : "border-slate-800 bg-slate-900/30"}`}>
                      {c.ok === true ? <CheckCircle className="w-4 h-4 text-green-400 shrink-0 mt-0.5" /> : c.ok === false ? <XCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" /> : <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />}
                      <div>
                        <p className="text-[11px] font-semibold text-slate-300">{c.label}</p>
                        <p className="text-[10px] text-slate-500 mt-0.5">{c.detail}</p>
                      </div>
                    </div>
                  ))}
                </CardContent>
              )}
            </Card>

            {/* ═══ 6. Decision Chain ════════════════════════════════════════ */}
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
                      { l: "OrderIntent", ok: !!d?.order_intent?.orderIntentId, veto: dec?.risk_veto, d: d?.order_intent?.orderIntentId || (dec?.risk_veto ? "风控否决" : NA) },
                      { l: "风控检查", ok: d?.risk_guard?.passed === true, veto: d?.risk_guard?.passed === false, d: `passed=${d?.risk_guard?.passed} · ${d?.risk_guard?.blockedReason || "无"}` },
                      { l: "Paper Trade", ok: !!d?.execution_result?.paperOrderGenerated, veto: dec?.risk_veto, d: d?.execution_result?.paperOrderGenerated ? `${d.execution_result.orderId || "—"} @ ${d.execution_result.fillPrice || "—"}` : NA },
                      { l: "Audit", ok: (d?.audit_timeline?.length || 0) > 0, veto: false, d: d?.audit_timeline?.length ? `${d.audit_timeline.length} 条` : NA },
                    ].map(s => (
                      <div key={s.l} className={`rounded-xl border p-3 ${s.ok ? "border-green-500/30 bg-green-500/5" : s.veto ? "border-red-500/30 bg-red-500/5" : "border-slate-800 bg-slate-900/30"}`}>
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-[10px] text-slate-400 font-semibold">{s.l}</p>
                          {s.ok ? <CheckCircle className="w-3 h-3 text-green-400" /> : s.veto ? <Shield className="w-3 h-3 text-red-400" /> : <XCircle className="w-3 h-3 text-slate-500" />}
                        </div>
                        <p className="text-[10px] text-slate-500">{String(s.d)}</p>
                      </div>
                    ))}
                  </div>
                  {d?.order_intent?.reason && (
                    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-2">
                      <p className="text-[9px] text-slate-500 mb-1">OrderIntent reason</p>
                      <p className="text-[10px] text-slate-400">{d.order_intent.reason}</p>
                    </div>
                  )}
                </CardContent>
              )}
            </Card>

            {/* ═══ 7. Reproducibility ═══════════════════════════════════════ */}
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

            {/* ═══ 8. Replay Runs ═══════════════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <GitCompare className="w-4 h-4 text-cyan-400" />复跑结果
                  <Badge className="bg-slate-800 text-slate-400 text-[9px]">{replayRuns.length} 条</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 space-y-2">
                {replayRuns.length === 0 ? <p className="text-xs text-slate-600 py-2">{NA}（replay_runs）</p>
                  : replayRuns.map((run, index) => {
                    const diff = asRecord(run.diffSummary);
                    const actionChanged = diff.actionChanged === true;
                    const contextChanged = diff.contextHashChanged === true;
                    return (
                      <div key={`${run.id || "replay"}-${index}`} className="rounded-lg border border-slate-800 bg-slate-900/30 p-2.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge className={`${run.status === "completed" ? "bg-green-500/15 text-green-300" : run.status === "failed" ? "bg-red-500/15 text-red-300" : "bg-amber-500/15 text-amber-300"} text-[9px]`}>
                            {run.status || run.eventType || "replay"}
                          </Badge>
                          <span className="text-[10px] text-slate-400">source #{run.sourceDecisionId || "—"}</span>
                          <span className="text-[10px] text-slate-500">→</span>
                          {run.replayDecisionId ? (
                            <button onClick={() => fetchDetail(Number(run.replayDecisionId))} className="text-[10px] text-cyan-300 hover:text-cyan-200">
                              replay #{run.replayDecisionId}
                            </button>
                          ) : <span className="text-[10px] text-slate-500">replay —</span>}
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
                            <p className={`text-[10px] ${contextChanged ? "text-amber-300" : "text-slate-300"}`}>{contextChanged ? "changed" : "same/unknown"}</p>
                          </div>
                          <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
                            <p className="text-[9px] text-slate-500">风险否决</p>
                            <p className="text-[10px] text-slate-300">{String(diff.originalRiskVeto ?? "—")} → {String(diff.replayRiskVeto ?? "—")}</p>
                          </div>
                        </div>
                        {run.error && <p className="mt-2 text-[10px] text-red-300">{run.error}</p>}
                      </div>
                    );
                  })}
              </CardContent>
            </Card>

            {/* ═══ 9. Export ════════════════════════════════════════════════ */}
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
