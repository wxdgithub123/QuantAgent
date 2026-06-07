"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { AppTopNav } from "@/components/navigation/AppTopNav";
import {
  Brain, ChevronDown, ChevronUp, RefreshCw,
  AlertTriangle, CheckCircle, Clock, Shield, Zap,
  ArrowRight, ArrowDown, ArrowUp, Minus,
  Layers, ScrollText, Hash, Swords, Gavel, Target
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────
interface DecisionHistoryItem {
  id: number; symbol: string; timestamp: string; final_signal: string;
  confidence: number; risk_veto?: boolean; summary?: string;
  vote_breakdown?: { bullish?: number; bearish?: number; neutral?: number };
}

interface AgentAnalysisEntry {
  role?: string; label?: string; opinion?: string; confidence?: number | null;
  reasoning?: string; summary?: string; data_source_chain?: string;
  risk_flag?: string | boolean; key_points?: string[]; output?: string; available?: boolean;
}

interface DecisionDetail {
  basic_info?: {
    decisionId?: number; symbol?: string; action?: string; confidence?: number; status?: string; createdAt?: string;
    model?: string; agentGraph?: string; source?: string; contextId?: string; contextHash?: string; availableTime?: string;
    modelVersion?: string; graphMode?: string | null; configuredMode?: string | null; isFullGraph?: boolean | null;
    strongAcceptanceEligible?: boolean | null; modeNote?: string | null;
  };
  agent_analysis?: Record<string, AgentAnalysisEntry>;
  role_outputs?: Array<AgentAnalysisEntry>;
  decision?: { final_signal?: string; summary?: string; risk_veto?: boolean; confidence?: number; vote_breakdown?: Record<string, number>; bull_view?: string; bear_view?: string; position_advice?: Record<string, unknown>; risk_notes?: string };
  trace_summary?: { factor_snapshots?: number; signal_events?: number; news_events?: number; macro_events?: number; role_outputs?: number; order_intent_events?: number; paper_trades?: number; risk_blocked?: boolean; risk_unavailable?: boolean; synthetic_audit_events?: number; replay_runs?: number };
  risk_guard?: { passed?: boolean | null; riskUnavailable?: boolean; blockedReason?: string | null };
  execution_result?: { paperOrderGenerated?: boolean; orderId?: string | null; fillPrice?: number | null; orderStatus?: string };
  order_intent?: { orderIntentId?: string | null; action?: string; reason?: string };
  audit_timeline?: Array<Record<string, unknown>>;
  schema_version?: string;
  strictSnapshotReplay?: boolean;
  strictSnapshotReplayAvailable?: boolean;
  originalAgentDecisionAuditPresent?: boolean;
  riskUnavailable?: boolean;
  syntheticAuditCount?: number;
}

interface FullCoordinateJob {
  jobId: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  phase?: string;
  message?: string;
  error?: string;
  decisionId?: number;
}

type DecisionMode = "full" | "quick";

// ─── Helpers ──────────────────────────────────────────────────────────────────
const fmtPct = (v: number | null | undefined) => v != null ? (v * 100).toFixed(0) + "%" : "—";
const fmtTime = (t: string | undefined | null) => t ? new Date(t).toLocaleString("zh-CN") : "—";
const NA = "后端未返回该字段";
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
const compactText = (value: unknown, max = 150) => {
  const text = value == null ? "" : String(value);
  return text.length > max ? `${text.slice(0, max)}...` : text;
};
const normalizeLegacyFallbackText = (value?: string | null) => {
  if (!value) return value ?? null;
  return value
    .split("未找到明确的多头论点（LLM不可用）").join("旧记录未保存明确的多头辩论文稿")
    .split("未找到明确的空头论点（LLM不可用）").join("旧记录未保存明确的空头辩论文稿");
};
const wasLegacyDebateFallback = (value?: string | null) => {
  if (!value) return false;
  return value.includes("未找到明确的多头论点（LLM不可用）") || value.includes("未找到明确的空头论点（LLM不可用）");
};
const isInferredChain = (value?: string | null) => !!value && /推断|inferred|coordination_history/i.test(value);
const voteLabel = (key: string) => {
  if (key === "bullish") return "多头";
  if (key === "bearish") return "空头";
  return "中立";
};
const voteColorClass = (key: string) => {
  if (key === "bullish") return "bg-green-400";
  if (key === "bearish") return "bg-red-400";
  return "bg-slate-400";
};

const signalBadge = (s: string | undefined | null) => {
  const t = (s || "").toUpperCase();
  if (t === "BUY") return <Badge className="bg-green-500/15 text-green-400">买入 BUY</Badge>;
  if (t === "SELL") return <Badge className="bg-red-500/15 text-red-400">卖出 SELL</Badge>;
  return <Badge className="bg-slate-500/15 text-slate-400">观望 WAIT</Badge>;
};

const opinionBadge = (o: string | undefined | null) => {
  const t = (o || "").toLowerCase();
  if (t === "sell" || t === "bearish") return <Badge className="bg-red-500/15 text-red-400 text-[10px]">看空</Badge>;
  if (t === "buy" || t === "bullish") return <Badge className="bg-green-500/15 text-green-400 text-[10px]">看多</Badge>;
  if (t === "wait" || t === "hold") return <Badge className="bg-amber-500/15 text-amber-400 text-[10px]">观望</Badge>;
  return <Badge className="bg-slate-500/15 text-slate-400 text-[10px]">中性</Badge>;
};

const opinionIcon = (o: string | undefined | null) => {
  const t = (o || "").toLowerCase();
  if (t === "sell" || t === "bearish") return <ArrowDown className="w-4 h-4 text-red-400 shrink-0" />;
  if (t === "buy" || t === "bullish") return <ArrowUp className="w-4 h-4 text-green-400 shrink-0" />;
  return <Minus className="w-4 h-4 text-slate-500 shrink-0" />;
};

const graphModeLabel = (isFullGraph?: boolean | null, graphMode?: string | null) => {
  if (isFullGraph === true) return "完整图";
  if (isFullGraph === false) return "快速研究";
  return graphMode || "未知模式";
};

// ─── Stage definitions ─────────────────────────────────────────────────────────
const STAGES = [
  { key: "analysts", label: "分析师层", icon: Layers, desc: "市场/新闻/宏观/情绪独立分析" },
  { key: "debate", label: "多空辩论层", icon: Swords, desc: "多头与空头研究员交锋论证" },
  { key: "plan", label: "交易计划层", icon: Target, desc: "交易员综合研判，生成仓位计划" },
  { key: "risk", label: "风险管理层", icon: Shield, desc: "风控经理评估风险，决定是否否决" },
  { key: "coordinator", label: "最终协调层", icon: Gavel, desc: "综合各方意见做出最终决策" },
];

function classifyStage(key: string, label: string): string {
  const s = `${key} ${label}`.toLowerCase();
  if (/macro|news|market|sentiment|social|context|situation|技术|新闻|情绪|宏观|情景|上下文/.test(s)) return "analysts";
  if (/bull|bear|多头|空头/.test(s)) return "debate";
  if (/trader|portfolio|交易|组合|plan/.test(s)) return "plan";
  if (/risk|风控/.test(s)) return "risk";
  if (/final|judge|coordinator|裁决|协调|最终/.test(s)) return "coordinator";
  return "analysts";
}

export default function DecisionsPage() {
  const [history, setHistory] = useState<DecisionHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterSymbol, setFilterSymbol] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DecisionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [triggering, setTriggering] = useState(false);
  const [fullJobStatus, setFullJobStatus] = useState<string | null>(null);
  const [decisionMode, setDecisionMode] = useState<DecisionMode>("full");
  const [triggerSymbol, setTriggerSymbol] = useState("BTCUSDT");
  const symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"];

  const fetchHistory = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams(); params.set("limit", "20");
      if (filterSymbol) params.set("symbol", filterSymbol);
      const res = await fetch("/api/v1/coordination/history?" + params.toString());
      if (!res.ok) throw new Error("HTTP " + res.status);
      const rows = (await res.json()).data || [];
      setHistory(rows);
      return rows as DecisionHistoryItem[];
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "加载失败"); return []; }
    finally { setLoading(false); }
  }, [filterSymbol]);

  const fetchDetail = useCallback(async (id: number) => {
    setDetailLoading(true); setSelectedId(id); setExpanded({});
    try {
      const res = await fetch("/api/v1/audit/decisions/" + id);
      if (!res.ok) throw new Error("HTTP " + res.status);
      setDetail(await res.json());
    } catch { setDetail(null); }
    finally { setDetailLoading(false); }
  }, []);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);
  useEffect(() => { if (history.length > 0 && !selectedId) fetchDetail(history[0].id); }, [history, selectedId, fetchDetail]);

  const triggerDecision = async () => {
    setTriggering(true); setError(null);
    setFullJobStatus(decisionMode === "full" ? "完整 TradingAgentsGraph 已提交..." : "快速研究模式运行中...");
    try {
      if (decisionMode === "quick") {
        const res = await fetch(`/api/v1/market/coordinate/${triggerSymbol}?interval=1h&fast=true`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload = await res.json() as { decision_id?: number; decisionId?: number };
        const decisionId = payload.decision_id || payload.decisionId;
        const rows = await fetchHistory();
        const latest = decisionId ? rows.find(r => r.id === decisionId) : rows.find(r => r.symbol === triggerSymbol) || rows[0];
        if (decisionId) await fetchDetail(Number(decisionId));
        else if (latest) await fetchDetail(latest.id);
        setFullJobStatus(`快速研究模式已完成：#${decisionId || latest?.id || ""}`);
        return;
      }

      const res = await fetch(`/api/v1/market/coordinate/full/${triggerSymbol}?interval=1h`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const created = await res.json() as FullCoordinateJob;
      setFullJobStatus(`完整图任务运行中：${created.jobId.slice(0, 8)}`);

      let completed: FullCoordinateJob | null = null;
      for (let i = 0; i < 180; i++) {
        await new Promise(r => setTimeout(r, 5000));
        const statusRes = await fetch(`/api/v1/market/coordinate/full/jobs/${created.jobId}`);
        if (!statusRes.ok) throw new Error(`任务状态 HTTP ${statusRes.status}`);
        const job = await statusRes.json() as FullCoordinateJob;
        if (job.status === "failed") throw new Error(job.error || "完整图任务失败");
        setFullJobStatus(job.status === "running" ? `完整 TradingAgentsGraph 运行中：${job.phase || "running"}` : job.message || job.status);
        if (job.status === "completed") {
          completed = job;
          break;
        }
      }
      if (!completed) throw new Error("完整图任务仍在运行，请稍后刷新历史");

      const rows = await fetchHistory();
      const latest = completed.decisionId ? rows.find(r => r.id === completed?.decisionId) : rows.find(r => r.symbol === triggerSymbol) || rows[0];
      if (latest) await fetchDetail(latest.id);
      setFullJobStatus(`完整图已完成：#${completed.decisionId || latest?.id || ""}`);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "触发失败"); }
    finally { setTriggering(false); }
  };

  const toggle = (k: string) => setExpanded(p => ({ ...p, [k]: !p[k] }));

  // ── Derived data ───────────────────────────────────────────────────────────
  const d = detail;
  const bi = d?.basic_info;
  const dec = d?.decision;
  const aa = d?.agent_analysis || {};
  const isFullGraph = bi?.isFullGraph;
  const graphMode = bi?.graphMode || null;
  const graphModeText = graphModeLabel(isFullGraph, graphMode);
  const graphModeDetail = isFullGraph === true
    ? `完整 TradingAgentsGraph · ${graphMode || "full_graph"}`
    : isFullGraph === false
      ? `快速研究模式 · ${graphMode || "context_adapter"}`
      : "旧记录未保存执行模式";
  const bullView = normalizeLegacyFallbackText(dec?.bull_view || null);
  const bearView = normalizeLegacyFallbackText(dec?.bear_view || null);
  const decisionSummary = normalizeLegacyFallbackText(dec?.summary || null);
  const hasLegacyDebateFallback = wasLegacyDebateFallback(dec?.bull_view || null) || wasLegacyDebateFallback(dec?.bear_view || null);

  // Merge agent_analysis + role_outputs — role_outputs has the richest data
  const roleOutputs: AgentAnalysisEntry[] = d?.role_outputs || [];
  const allRoles: Array<{
    key: string; label: string; stage: string;
    opinion?: string; confidence: number | null;
    reasoning: string | null; summary: string | null;
    keyPoints: string[]; dataSourceChain: string | null; riskFlag: string | boolean | null;
  }> = [];

  // First, add from role_outputs (best data)
  for (const ro of roleOutputs) {
    allRoles.push({
      key: ro.role || `role-${allRoles.length}`,
      label: ro.label || ro.role || `角色 ${allRoles.length + 1}`,
      stage: classifyStage(ro.role || "", ro.label || ""),
      opinion: ro.opinion || undefined,
      confidence: ro.confidence ?? null,
      reasoning: normalizeLegacyFallbackText(ro.reasoning || null),
      summary: normalizeLegacyFallbackText(ro.summary || null),
      keyPoints: ro.key_points || [],
      dataSourceChain: ro.data_source_chain || null,
      riskFlag: ro.risk_flag || null,
    });
  }

  // Then add agents from agent_analysis that aren't already covered
  for (const [key, entry] of Object.entries(aa)) {
    const e = entry as AgentAnalysisEntry;
    // Skip if already covered by role_outputs
    const covered = allRoles.some(r => {
      const rl = (r.key || "").toLowerCase();
      const el = (e.role || key).toLowerCase();
      return rl.includes(el) || el.includes(rl) || r.label === (e.label || key);
    });
    if (covered) continue;

    const isSpecial = key === "macroAgent" || key === "riskAgent";
    // Skip empty synthetic agents (backend fallback when no matching role found)
    if (isSpecial && e.available === false && !e.output) continue;
    if (isSpecial && String(e.output || "").includes("暂无数据") && e.available === false) continue;

    allRoles.push({
      key,
      label: e.label || key,
      stage: classifyStage(key, e.label || key),
      opinion: isSpecial ? undefined : (e.opinion || undefined),
      confidence: isSpecial ? null : (e.confidence ?? null),
      reasoning: normalizeLegacyFallbackText(isSpecial ? (e.output || null) : (e.reasoning || null)),
      summary: normalizeLegacyFallbackText(isSpecial ? (e.output ? String(e.output).slice(0, 200) + (String(e.output).length > 200 ? "…" : "") : (e.available ? "数据可用 · 无输出摘要" : "数据不可用")) : (e.summary || null)),
      keyPoints: e.key_points || [],
      dataSourceChain: e.data_source_chain || null,
      riskFlag: e.risk_flag || null,
    });
  }

  const stageGroups: Record<string, typeof allRoles> = {};
  for (const r of allRoles) {
    if (!stageGroups[r.stage]) stageGroups[r.stage] = [];
    stageGroups[r.stage].push(r);
  }

  // Chain steps
  const trace = d?.trace_summary;
  const timeline = d?.audit_timeline || [];
  const syntheticAuditCount = firstUsefulNumber(trace?.synthetic_audit_events, d?.syntheticAuditCount, timeline.filter(item => item.synthetic).length) || 0;
  const hasSyntheticAudit = syntheticAuditCount > 0 || timeline.some(item => item.synthetic);
  const derivedOriginalAuditPresent = timeline.some(item => item.eventType === "AGENT_DECISION" && item.synthetic !== true && item.auditSource === "audit_logs");
  const originalAuditPresent = d?.originalAgentDecisionAuditPresent === true || (d?.originalAgentDecisionAuditPresent == null && derivedOriginalAuditPresent);
  const strictReplayAvailable = d?.strictSnapshotReplayAvailable === true || d?.strictSnapshotReplay === true;
  const riskUnavailable = d?.riskUnavailable === true || d?.risk_guard?.riskUnavailable === true || trace?.risk_unavailable === true || timeline.some(item => item.eventType === "RISK_CHECK_UNAVAILABLE" || item.riskUnavailable === true);
  const executionRiskBlocked = d?.risk_guard?.passed === false || trace?.risk_blocked === true || timeline.some(item => item.eventType === "RISK_BLOCKED");
  const isVeto = dec?.risk_veto || executionRiskBlocked;
  const finalAction = (bi?.action || dec?.final_signal || "").toUpperCase();
  const isNoAction = finalAction === "WAIT" || d?.order_intent?.orderIntentId === "NO_ACTION";
  const opinionCounts = allRoles.reduce<Record<string, number>>((acc, role) => {
    const key = String(role.opinion || "neutral").toLowerCase();
    const bucket = /buy|bull|long|看多/.test(key) ? "bullish" : /sell|bear|short|看空/.test(key) ? "bearish" : "neutral";
    acc[bucket] = (acc[bucket] || 0) + 1;
    return acc;
  }, {});
  const hasRoleDisagreement = (opinionCounts.bullish || 0) > 0 && (opinionCounts.bearish || 0) > 0;
  const trustItems = [
    { label: "执行模式", ok: isFullGraph === true, warn: isFullGraph !== true, detail: isFullGraph === true ? graphModeDetail : isFullGraph === false ? "快速研究不计入完整图强验收" : "旧记录无法判定完整图" },
    { label: "原始审计", ok: originalAuditPresent, warn: hasSyntheticAudit, detail: originalAuditPresent ? "audit_logs 已记录 AGENT_DECISION" : `缺原始记录 · synthetic ${syntheticAuditCount}` },
    { label: "严格回放", ok: strictReplayAvailable, warn: !strictReplayAvailable, detail: strictReplayAvailable ? "决策时点输入证据可用" : "旧记录缺严格快照/contextHash，复跑会降级" },
    { label: "RiskGuard", ok: !riskUnavailable && !executionRiskBlocked, warn: riskUnavailable, detail: riskUnavailable ? "风控不可用，已保守阻断" : executionRiskBlocked ? "风控阻断" : "未阻断" },
    { label: "角色共识", ok: allRoles.length > 0 && !hasRoleDisagreement, warn: hasRoleDisagreement, detail: allRoles.length ? `看多 ${opinionCounts.bullish || 0} · 看空 ${opinionCounts.bearish || 0} · 中性 ${opinionCounts.neutral || 0}` : NA },
  ];
  const chainSteps = [
    { label: "coordination_history", ok: !!bi, veto: false, info: bi ? `#${bi.decisionId} · ${bi.action || "—"} · conf ${fmtPct(bi.confidence)}` : NA },
    { label: "OrderIntent", ok: !!d?.order_intent?.orderIntentId || isNoAction, veto: isVeto, info: d?.order_intent?.orderIntentId === "NO_ACTION" || isNoAction ? "WAIT，无需下单意图" : d?.order_intent?.orderIntentId ? d.order_intent.orderIntentId : isVeto ? "风控否决" : NA },
    { label: "Paper Trade", ok: !!d?.execution_result?.paperOrderGenerated || isNoAction, veto: isVeto, info: d?.execution_result?.paperOrderGenerated ? `${d.execution_result.orderId || "—"} @ ${d.execution_result.fillPrice || "—"}` : isNoAction ? "WAIT，无需成交" : isVeto ? "风控否决" : NA },
    { label: "Audit 记录", ok: originalAuditPresent, veto: !originalAuditPresent, info: d?.audit_timeline?.length ? `${d.audit_timeline.length} 条 · synthetic ${syntheticAuditCount}` : NA },
  ];

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <>
      <AppTopNav activeSection="decisions" title="TradingAgents 决策中心" subtitle="AI 怎么想 · 为什么这么判断" />
      <div className="container mx-auto px-4 py-4 space-y-5 max-w-7xl">

        {/* ── Top Bar ────────────────────────────────────────────────────── */}
        <div className="flex flex-wrap items-center gap-2">
          <select value={filterSymbol} onChange={e => setFilterSymbol(e.target.value)} className="h-8 rounded border border-slate-700 bg-slate-900/60 px-2 text-xs text-slate-300">
            <option value="">全部</option>
            {symbols.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={fetchHistory} disabled={loading} className="h-8 gap-1 text-xs">
            <RefreshCw className={"h-3 w-3 " + (loading ? "animate-spin" : "")} />刷新
          </Button>
          <select value={triggerSymbol} onChange={e => setTriggerSymbol(e.target.value)} className="h-8 rounded border border-cyan-500/30 bg-cyan-500/10 px-2 text-xs text-cyan-300">
            {symbols.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <div className="inline-flex h-8 overflow-hidden rounded border border-slate-700 bg-slate-900/70">
            <button type="button" onClick={() => setDecisionMode("full")}
              className={`px-3 text-[10px] transition-colors ${decisionMode === "full" ? "bg-cyan-500/20 text-cyan-200" : "text-slate-400 hover:text-slate-200"}`}>
              完整多 Agent 图
            </button>
            <button type="button" onClick={() => setDecisionMode("quick")}
              className={`border-l border-slate-700 px-3 text-[10px] transition-colors ${decisionMode === "quick" ? "bg-amber-500/20 text-amber-200" : "text-slate-400 hover:text-slate-200"}`}>
              快速研究模式
            </button>
          </div>
          <Button size="sm" onClick={triggerDecision} disabled={triggering} className="h-8 gap-1 text-xs bg-cyan-600 hover:bg-cyan-500 text-white">
            <Zap className={"h-3 w-3 " + (triggering ? "animate-pulse" : "")} />{triggering ? "生成中..." : decisionMode === "full" ? "生成完整图决策" : "生成快速研究"}
          </Button>
          {history.length > 0 && <span className="text-[10px] text-slate-500 ml-auto">共 {history.length} 条</span>}
        </div>
        {error && <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-400">{error}</div>}
        {fullJobStatus && <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-3 text-xs text-cyan-300">{fullJobStatus}</div>}

        {/* ── Loading / Empty ────────────────────────────────────────────── */}
        {(loading || detailLoading) && !d && (
          <Card className="border-slate-700/50 bg-slate-950/60"><CardContent className="py-12 text-center">
            <RefreshCw className="h-6 w-6 animate-spin mx-auto text-slate-500 mb-3" /><p className="text-sm text-slate-400">加载决策数据...</p>
          </CardContent></Card>
        )}
        {!loading && history.length === 0 && (
          <Card className="border-2 border-cyan-400/30 bg-cyan-400/5"><CardContent className="py-16 text-center">
            <Brain className="h-10 w-10 mx-auto text-slate-600 mb-4" /><p className="text-slate-400 font-semibold mb-2">暂无 AI 决策记录</p>
            <p className="text-xs text-slate-500 mb-4">选择标的后点击生成决策，触发 TradingAgents AI 决策流程</p>
            <div className="flex items-center justify-center gap-2">
              <select value={triggerSymbol} onChange={e => setTriggerSymbol(e.target.value)} className="h-8 rounded border border-cyan-500/30 bg-cyan-500/10 px-2 text-xs text-cyan-300">
                {symbols.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <div className="inline-flex h-8 overflow-hidden rounded border border-slate-700 bg-slate-900/70">
                <button type="button" onClick={() => setDecisionMode("full")}
                  className={`px-3 text-[10px] ${decisionMode === "full" ? "bg-cyan-500/20 text-cyan-200" : "text-slate-400"}`}>
                  完整图
                </button>
                <button type="button" onClick={() => setDecisionMode("quick")}
                  className={`border-l border-slate-700 px-3 text-[10px] ${decisionMode === "quick" ? "bg-amber-500/20 text-amber-200" : "text-slate-400"}`}>
                  快速研究
                </button>
              </div>
              <Button size="sm" onClick={triggerDecision} disabled={triggering} className="h-8 gap-1 text-xs bg-cyan-600 hover:bg-cyan-500 text-white">
                <Zap className={"h-3 w-3 " + (triggering ? "animate-pulse" : "")} />{triggering ? "生成中..." : decisionMode === "full" ? "生成完整图" : "生成快速研究"}
              </Button>
            </div>
          </CardContent></Card>
        )}

        {d && (
          <>
            {/* ═══ 1. 最新 AI 决策总览 ═══════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60 overflow-hidden">
              <div className={`h-1 ${isVeto ? "bg-red-500" : (bi?.action || "").toUpperCase() === "SELL" ? "bg-red-500" : (bi?.action || "").toUpperCase() === "BUY" ? "bg-green-500" : "bg-slate-500"}`} />
              <CardHeader className="pb-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Hash className="w-4 h-4 text-cyan-400" />#{bi?.decisionId || selectedId} · {bi?.symbol || "—"}
                    <span className="text-[10px] text-slate-500 font-normal">{fmtTime(bi?.createdAt)}</span>
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    {signalBadge(bi?.action || dec?.final_signal)}
                    <Badge className={`${isFullGraph === true ? "bg-green-500/15 text-green-300" : isFullGraph === false ? "bg-amber-500/15 text-amber-300" : "bg-slate-500/15 text-slate-300"} text-[10px]`}>
                      {graphModeText}
                    </Badge>
                    <Badge variant="outline" className="border-slate-700 text-slate-400 text-[10px]">置信度 {fmtPct(bi?.confidence ?? dec?.confidence)}</Badge>
                    {isVeto && <Badge className="bg-red-500/15 text-red-400 text-[10px]">风控否决</Badge>}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Model version info */}
                <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
                  {[
                    { l: "模型", v: bi?.modelVersion || bi?.model },
                    { l: "适配器", v: bi?.agentGraph },
                    { l: "执行模式", v: graphModeDetail },
                    { l: "contextId", v: bi?.contextId },
                    { l: "contextHash", v: bi?.contextHash },
                    { l: "availableTime", v: fmtTime(bi?.availableTime) },
                  ].map(m => (
                    <div key={m.l} className="rounded border border-slate-800 bg-slate-900/40 p-1.5">
                      <p className="text-[9px] text-slate-500">{m.l}</p>
                      <p className={`text-[10px] truncate ${m.v && m.v !== NA ? "text-slate-300" : "text-slate-600 italic"}`}>{m.v || NA}</p>
                    </div>
                  ))}
                </div>
                {isFullGraph !== true && (
                  <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200">
                    <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
                    {isFullGraph === false ? "当前记录来自快速研究模式，可用于稳定/批量分析，不计入完整 TradingAgentsGraph 多 Agent 强验收。" : "当前旧记录未保存执行模式，无法证明它走过完整 TradingAgentsGraph。"}
                  </div>
                )}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                  {trustItems.map(item => {
                    const stateClass = item.ok && !item.warn
                      ? "border-green-500/30 bg-green-500/5"
                      : item.warn
                        ? "border-amber-500/30 bg-amber-500/5"
                        : "border-red-500/30 bg-red-500/5";
                    const Icon = item.ok && !item.warn ? CheckCircle : item.warn ? Clock : Shield;
                    return (
                      <div key={item.label} className={`rounded-lg border p-2 ${stateClass}`}>
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-[10px] font-semibold text-slate-300">{item.label}</p>
                          <Icon className={`h-3.5 w-3.5 ${item.ok && !item.warn ? "text-green-400" : item.warn ? "text-amber-400" : "text-red-400"}`} />
                        </div>
                        <p className="mt-1 text-[10px] text-slate-500">{item.detail}</p>
                      </div>
                    );
                  })}
                </div>
                {/* Summary */}
                <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
                  <p className="text-[10px] text-slate-500 mb-1">决策摘要</p>
                  {dec?.summary ? (
                    <p className="text-[11px] text-slate-300 leading-relaxed">{decisionSummary}</p>
                  ) : (
                    <p className="text-[11px] text-slate-600 italic">{NA}（summary）</p>
                  )}
                </div>
                {/* Vote breakdown */}
                {dec?.vote_breakdown && Object.keys(dec.vote_breakdown).length > 0 && (
                  <div className="flex items-center gap-4 text-[11px] text-slate-400">
                    {Object.entries(dec.vote_breakdown).map(([k, v]) => (
                      <span key={k} className="inline-flex items-center gap-1.5">
                        <span className={`h-2 w-2 rounded-full ${voteColorClass(k)}`} />
                        {voteLabel(k)} {typeof v === "number" ? (v * 100).toFixed(0) + "%" : String(v)}
                      </span>
                    ))}
                  </div>
                )}
                {/* Position advice */}
                {dec?.position_advice && Object.keys(dec.position_advice).length > 0 && (
                  <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
                    <div className="flex items-center gap-2 mb-2"><Target className="w-4 h-4 text-blue-400" /><p className="text-xs font-semibold text-blue-400">仓位建议</p></div>
                    {Object.entries(dec.position_advice).map(([k, v]) => {
                      if (k.startsWith("_")) return null;
                      if (Array.isArray(v) && v.length > 0) {
                        return (
                          <div key={k} className="rounded border border-slate-800 bg-slate-950/40 p-2 mb-2">
                            <p className="text-[9px] text-slate-500 mb-1">{k}（{v.length} 条）</p>
                            <div className="space-y-1 max-h-32 overflow-y-auto">
                              {v.map((item, i) => {
                                const it = item as Record<string,unknown>;
                                const itLabel = String(it.label || it.role || `#${i}`);
                                const itOpinion = String(it.opinion || "—");
                                const itConf = it.confidence != null ? Number(it.confidence) : null;
                                const itPhase = it.phase != null ? String(it.phase) : null;
                                return (
                                  <div key={i} className="text-[10px] text-slate-400 border-l-2 border-slate-700 pl-2">
                                    <span className="text-slate-300">{itLabel}</span>
                                    {" · "}<span className={itOpinion.toLowerCase()==="sell"?"text-red-400":itOpinion.toLowerCase()==="buy"?"text-green-400":"text-slate-400"}>{itOpinion}</span>
                                    {itConf != null && <span className="text-slate-600"> · conf {String((itConf*100).toFixed(0))}%</span>}
                                    {itPhase && <span className="text-slate-600"> · {itPhase}</span>}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      }
                      return (
                        <div key={k} className="rounded border border-slate-800 bg-slate-950/40 p-1.5 inline-block mr-2 mb-2">
                          <p className="text-[9px] text-slate-500">{k}</p>
                          <p className="text-[10px] text-slate-300 font-mono">{typeof v === "object" ? JSON.stringify(v).slice(0, 120) : String(v)}</p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ═══ 2. Agent Consensus Matrix ══════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60 overflow-hidden">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Layers className="w-4 h-4 text-cyan-400" />Agent 共识矩阵
                  {hasRoleDisagreement && <Badge className="bg-amber-500/15 text-amber-300 text-[10px]">存在分歧</Badge>}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {allRoles.length === 0 ? (
                  <p className="text-xs text-slate-600 py-4 text-center">后端未返回 role_outputs / agent_analysis</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[760px] text-left text-[11px]">
                      <thead className="text-[10px] text-slate-500">
                        <tr className="border-b border-slate-800">
                          <th className="py-2 pr-3 font-medium">角色</th>
                          <th className="py-2 pr-3 font-medium">阶段</th>
                          <th className="py-2 pr-3 font-medium">方向</th>
                          <th className="py-2 pr-3 font-medium">置信度</th>
                          <th className="py-2 pr-3 font-medium">风险</th>
                          <th className="py-2 pr-3 font-medium">数据源</th>
                          <th className="py-2 font-medium">核心摘要</th>
                        </tr>
                      </thead>
                      <tbody>
                        {allRoles.map(role => {
                          const stage = STAGES.find(item => item.key === role.stage);
                          const inferredSource = isInferredChain(role.dataSourceChain);
                          return (
                            <tr key={`${role.stage}-${role.key}`} className="border-b border-slate-900/80 align-top">
                              <td className="py-2 pr-3">
                                <p className="max-w-[140px] truncate font-semibold text-slate-200">{role.label}</p>
                                <p className="max-w-[140px] truncate font-mono text-[9px] text-slate-600">{role.key}</p>
                              </td>
                              <td className="py-2 pr-3 text-slate-400">{stage?.label || role.stage}</td>
                              <td className="py-2 pr-3">{role.opinion ? opinionBadge(role.opinion) : <span className="text-slate-600">{NA}</span>}</td>
                              <td className="py-2 pr-3 font-mono text-slate-300">{role.confidence != null ? fmtPct(role.confidence) : "—"}</td>
                              <td className="py-2 pr-3">
                                {role.riskFlag ? <Badge className="bg-amber-500/15 text-amber-300 text-[10px]">提示</Badge> : <span className="text-slate-600">—</span>}
                              </td>
                              <td className="py-2 pr-3">
                                {role.dataSourceChain ? (
                                  <Badge className={`${inferredSource ? "bg-amber-500/15 text-amber-300" : "bg-green-500/15 text-green-300"} text-[10px]`}>
                                    {inferredSource ? "推断" : "已记录"}
                                  </Badge>
                                ) : <span className="text-slate-600">缺失</span>}
                              </td>
                              <td className="py-2 text-slate-400">{compactText(role.summary || role.reasoning || NA, 180)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ═══ 3. TradingAgents 决策流程 ══════════════════════════════ */}
            <div>
              <h3 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
                <Layers className="w-4 h-4 text-cyan-400" /> TradingAgents 决策流程
              </h3>
              {allRoles.length === 0 ? (
                <p className="text-xs text-slate-600 py-8 text-center">后端未返回 agent_analysis 数据</p>
              ) : (
                <div className="space-y-4">
                  {STAGES.map(stage => {
                    const stageRoles = stageGroups[stage.key] || [];
                    if (stageRoles.length === 0) return null;
                    const Icon = stage.icon;
                    return (
                      <div key={stage.key} className="rounded-2xl border border-slate-700/50 bg-slate-950/60 overflow-hidden">
                        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-800/50 bg-slate-900/40">
                          <div className="w-8 h-8 rounded-lg bg-cyan-500/10 flex items-center justify-center"><Icon className="w-4 h-4 text-cyan-400" /></div>
                          <div className="flex-1"><p className="text-sm font-semibold text-white">{stage.label}</p><p className="text-[10px] text-slate-500">{stage.desc}</p></div>
                          <Badge variant="outline" className="border-slate-700 text-slate-400 text-[10px]">{stageRoles.length} 个角色</Badge>
                        </div>
                        <div className="p-3 space-y-2">
                          {stageRoles.map(role => {
                            const isExpanded = expanded[role.key] || false;
                            const hasDetail = !!(role.reasoning || role.keyPoints.length > 0);
                            return (
                              <div key={role.key} className={`rounded-xl border bg-slate-900/30 ${hasDetail ? "border-slate-800 hover:border-slate-700 cursor-pointer" : "border-slate-800/50"}`}
                                onClick={() => hasDetail && toggle(role.key)}>
                                <div className="p-3">
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-2 min-w-0">
                                      {opinionIcon(role.opinion)}
                                      <div className="min-w-0">
                                        <p className="text-xs font-semibold text-slate-200 truncate">{role.label}</p>
                                        <p className="text-[9px] text-slate-500 font-mono">{role.key} · 置信度 {role.confidence != null ? fmtPct(role.confidence) : "—"}</p>
                                      </div>
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                      {role.opinion ? opinionBadge(role.opinion) : <span className="text-[10px] text-slate-600">{NA}</span>}
                                      {role.riskFlag && <Badge className="bg-amber-500/15 text-amber-400 text-[10px]">风险</Badge>}
                                      {hasDetail && (isExpanded ? <ChevronUp className="w-3.5 h-3.5 text-slate-500" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-500" />)}
                                    </div>
                                  </div>
                                  {/* Summary */}
                                  {role.summary && <p className="mt-2 text-[11px] text-slate-400 leading-relaxed line-clamp-2">{role.summary}</p>}
                                  {/* Data scope (compact) */}
                                  <p className="mt-1 text-[9px] text-slate-600">
                                    数据管道：{role.dataSourceChain || "后端未记录"}
                                  </p>
                                </div>
                                {/* Expanded detail */}
                                {isExpanded && hasDetail && (
                                  <div className="border-t border-slate-800 bg-slate-950/40 px-4 py-3 space-y-3">
                                    {role.reasoning && (
                                      <div>
                                        <p className="text-[10px] text-slate-500 mb-1">完整分析</p>
                                        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 max-h-72 overflow-y-auto">
                                          <p className="text-[11px] text-slate-300 leading-relaxed whitespace-pre-wrap">{role.reasoning}</p>
                                        </div>
                                      </div>
                                    )}
                                    {role.keyPoints.length > 0 && (
                                      <div>
                                        <p className="text-[10px] text-slate-500 mb-1">关键论点（{role.keyPoints.length} 条）</p>
                                        <ul className="space-y-1">
                                          {role.keyPoints.map((kp, i) => (
                                            <li key={i} className="text-[11px] text-slate-400 flex items-start gap-2"><ArrowRight className="w-3 h-3 text-slate-600 mt-0.5 shrink-0" />{kp}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* ═══ 4. 多空辩论与最终裁决 ════════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60 overflow-hidden">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2"><Swords className="w-4 h-4 text-amber-400" />多空辩论与最终裁决</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-3">
                    <div className="flex items-center gap-2 mb-1"><ArrowUp className="w-4 h-4 text-green-400" /><p className="text-xs font-semibold text-green-400">多头观点</p></div>
                    {bullView ? <p className="text-[11px] text-slate-300 leading-relaxed whitespace-pre-wrap">{bullView}</p>
                      : <p className="text-[11px] text-slate-600 italic">后端未生成独立多头辩论文本，多空观点分散在各角色分析中</p>}
                  </div>
                  <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3">
                    <div className="flex items-center gap-2 mb-1"><ArrowDown className="w-4 h-4 text-red-400" /><p className="text-xs font-semibold text-red-400">空头观点</p></div>
                    {bearView ? <p className="text-[11px] text-slate-300 leading-relaxed whitespace-pre-wrap">{bearView}</p>
                      : <p className="text-[11px] text-slate-600 italic">后端未生成独立空头辩论文本，多空观点分散在各角色分析中</p>}
                  </div>
                </div>
                {hasLegacyDebateFallback && (
                  <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200">
                    这条旧样例记录没有保存标准多空辩论文稿，页面展示兼容说明；不代表当前 TradingAgents/LLM 服务不可用。
                  </div>
                )}

                {/* Risk ruling */}
                <div className={`rounded-xl border p-3 ${isVeto ? "border-red-500/30 bg-red-500/10" : "border-amber-500/20 bg-amber-500/5"}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <Shield className={`w-4 h-4 ${isVeto ? "text-red-400" : "text-amber-400"}`} />
                    <p className="text-xs font-semibold text-white">风险裁决</p>
                    <Badge className={isVeto ? "bg-red-500/15 text-red-400 text-[10px]" : "bg-amber-500/15 text-amber-400 text-[10px]"}>{isVeto ? "已否决" : (d?.risk_guard?.passed === true ? "已通过" : "未裁决")}</Badge>
                  </div>
                  {d?.risk_guard?.blockedReason ? <p className="text-[11px] text-red-300">{d.risk_guard.blockedReason}</p>
                    : dec?.risk_notes ? <p className="text-[11px] text-slate-400">{dec.risk_notes}</p>
                    : <p className="text-[11px] text-slate-600 italic">{NA}（risk_notes）</p>}
                </div>

                {/* Final coordinator opinion */}
                <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-3">
                  <div className="flex items-center gap-2 mb-1"><Gavel className="w-4 h-4 text-purple-400" /><p className="text-xs font-semibold text-purple-400">最终协调意见</p></div>
                  {decisionSummary ? <p className="text-[11px] text-slate-300 leading-relaxed">{decisionSummary}</p>
                    : <p className="text-[11px] text-slate-600 italic">{NA}</p>}
                  {d?.order_intent?.reason && (
                    <div className="mt-2 rounded border border-slate-800 bg-slate-950/40 p-2">
                      <p className="text-[9px] text-slate-500">OrderIntent 原因</p>
                      <p className="text-[10px] text-slate-400">{d.order_intent.reason}</p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* ═══ 5. 决策链路追踪 ═══════════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2"><ScrollText className="w-4 h-4 text-cyan-400" />决策链路追踪</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {chainSteps.map(s => (
                    <div key={s.label} className={`rounded-xl border p-3 ${s.ok ? "border-green-500/30 bg-green-500/5" : s.veto ? "border-red-500/30 bg-red-500/5" : "border-slate-800 bg-slate-900/30"}`}>
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-[9px] text-slate-500">{s.label}</p>
                        {s.ok ? <CheckCircle className="w-3 h-3 text-green-400" /> : s.veto ? <Shield className="w-3 h-3 text-red-400" /> : <Minus className="w-3 h-3 text-slate-500" />}
                      </div>
                      <p className="text-[10px] text-slate-400">{s.info}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* ═══ 6. 决策历史 ═══════════════════════════════════════════ */}
            <Card className="border-slate-700/50 bg-slate-950/60">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">决策历史 <span className="text-[10px] text-slate-500 font-normal">最近 20 条 · 点击切换</span></CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {history.map(item => (
                    <div key={item.id} onClick={() => fetchDetail(item.id)}
                      className={`rounded-xl border p-3 cursor-pointer transition-colors ${selectedId === item.id ? "border-cyan-500/50 bg-cyan-500/10" : "border-slate-800 bg-slate-900/30 hover:border-slate-700"}`}>
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-[10px] font-mono text-slate-600">#{item.id}</span>
                          <span className="text-xs font-semibold text-slate-200">{item.symbol}</span>
                          {signalBadge(item.final_signal)}
                          {item.risk_veto && <Badge className="bg-red-500/15 text-red-400 text-[10px]">否决</Badge>}
                        </div>
                        <span className="text-[10px] text-slate-500 shrink-0">{fmtTime(item.timestamp)}</span>
                      </div>
                      {item.summary && <p className="mt-1.5 text-[11px] text-slate-400 line-clamp-2">{item.summary}</p>}
                      <div className="flex items-center gap-3 mt-1 text-[10px] text-slate-500">
                        <span>置信度 {fmtPct(item.confidence)}</span>
                        {item.vote_breakdown && (
                          <span className="inline-flex items-center gap-2">
                            <span className="inline-flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-green-400" />{(item.vote_breakdown.bullish ?? 0) * 100}%</span>
                            <span className="inline-flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-red-400" />{(item.vote_breakdown.bearish ?? 0) * 100}%</span>
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </>
  );
}
