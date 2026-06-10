"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bot,
  Brain,
  CheckCircle2,
  Database,
  Pencil,
  RefreshCw,
  Save,
  ServerCog,
  Settings2,
  Shield,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";

import { AppTopNav } from "@/components/navigation/AppTopNav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type JsonRecord = Record<string, unknown>;

interface ConfigOverview {
  data?: {
    sections?: Array<{ key: string; title: string; status: string; api: string }>;
    local_config?: JsonRecord;
    effective?: JsonRecord;
  };
}

interface TradingAgentsPayload {
  data?: {
    effective?: JsonRecord;
    local_overrides?: JsonRecord;
    role_configs?: Record<string, JsonRecord>;
    custom_agents?: Array<JsonRecord>;
    data_boundary?: JsonRecord;
  };
}

interface AgentDraft {
  agent_id: string;
  display_name: string;
  enabled: boolean;
  llm_provider: string;
  model: string;
  base_url: string;
  prompt: string;
  prompt_version: string;
  skill: string;
}

interface RoleDraft {
  enabled: boolean;
  llm_provider: string;
  model: string;
  base_url: string;
  prompt_version: string;
  prompt: string;
  skill: string;
}

interface TradingAgentsDraft {
  default_mode: string;
  llm_provider: string;
  model: string;
  base_url: string;
  max_runtime_seconds: string;
  background_run: boolean;
  prompt_version: string;
  output_language: string;
  save_full_output: boolean;
  write_audit: boolean;
}

type TradingAgentsSwitchKey = "background_run" | "save_full_output" | "write_audit";

const SECTION_ICONS: Record<string, typeof Settings2> = {
  tradingagents: Brain,
  custom_agents: Bot,
  data_sources: Database,
  factors_signals: SlidersHorizontal,
  risk: Shield,
  simulation: ServerCog,
  backtest_replay: RefreshCw,
  security: Shield,
};

const emptyDraft: AgentDraft = {
  agent_id: "",
  display_name: "",
  enabled: true,
  llm_provider: "",
  model: "",
  base_url: "",
  prompt: "",
  prompt_version: "custom.v1",
  skill: "",
};

const defaultTradingAgentsDraft: TradingAgentsDraft = {
  default_mode: "context_adapter",
  llm_provider: "",
  model: "",
  base_url: "",
  max_runtime_seconds: "300",
  background_run: true,
  prompt_version: "phase2.zh-CN.v1",
  output_language: "zh-CN",
  save_full_output: true,
  write_audit: true,
};

function statusClass(status?: string) {
  if (status === "ready") return "border-emerald-400/30 bg-emerald-500/15 text-emerald-200";
  if (status === "partial") return "border-amber-400/30 bg-amber-500/15 text-amber-200";
  return "border-slate-400/25 bg-slate-500/15 text-slate-300";
}

function valueText(value: unknown, fallback = "未配置") {
  if (value == null || value === "") return fallback;
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.length ? value.join("、") : fallback;
  return String(value);
}

function asRecord(value: unknown): JsonRecord {
  return typeof value === "object" && value !== null ? (value as JsonRecord) : {};
}

function boolValue(value: unknown, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

function inputValue(value: unknown) {
  if (value == null) return "";
  return String(value);
}

function roleDraftFromConfig(config: JsonRecord): RoleDraft {
  return {
    enabled: boolValue(config.enabled, true),
    llm_provider: inputValue(config.llm_provider),
    model: inputValue(config.model),
    base_url: inputValue(config.base_url),
    prompt_version: inputValue(config.prompt_version),
    prompt: inputValue(config.prompt),
    skill: inputValue(config.skill),
  };
}

function agentDraftFromRecord(agent: JsonRecord): AgentDraft {
  return {
    agent_id: inputValue(agent.agent_id),
    display_name: inputValue(agent.display_name),
    enabled: boolValue(agent.enabled, true),
    llm_provider: inputValue(agent.llm_provider),
    model: inputValue(agent.model),
    base_url: inputValue(agent.base_url),
    prompt: inputValue(agent.prompt),
    prompt_version: inputValue(agent.prompt_version) || "custom.v1",
    skill: inputValue(agent.skill),
  };
}

function tradingAgentsDraftFromConfig(config: JsonRecord): TradingAgentsDraft {
  return {
    default_mode: inputValue(config.default_mode) || "context_adapter",
    llm_provider: inputValue(config.llm_provider),
    model: inputValue(config.model),
    base_url: inputValue(config.base_url),
    max_runtime_seconds: inputValue(config.max_runtime_seconds) || "300",
    background_run: boolValue(config.background_run, true),
    prompt_version: inputValue(config.prompt_version) || "phase2.zh-CN.v1",
    output_language: inputValue(config.output_language) || "zh-CN",
    save_full_output: boolValue(config.save_full_output, true),
    write_audit: boolValue(config.write_audit, true),
  };
}

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export default function ConfigCenterPage() {
  const [overview, setOverview] = useState<ConfigOverview | null>(null);
  const [tradingAgents, setTradingAgents] = useState<TradingAgentsPayload | null>(null);
  const [tradingAgentsDraft, setTradingAgentsDraft] = useState<TradingAgentsDraft>(defaultTradingAgentsDraft);
  const [draft, setDraft] = useState<AgentDraft>(emptyDraft);
  const [roleDrafts, setRoleDrafts] = useState<Record<string, RoleDraft>>({});
  const [editingAgentId, setEditingAgentId] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingRole, setSavingRole] = useState("");
  const [deletingAgentId, setDeletingAgentId] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [overviewData, tradingAgentsData] = await Promise.all([
        fetchJson<ConfigOverview>("/api/v1/config-center/overview"),
        fetchJson<TradingAgentsPayload>("/api/v1/config-center/tradingagents"),
      ]);
      setOverview(overviewData);
      setTradingAgents(tradingAgentsData);
      setTradingAgentsDraft(tradingAgentsDraftFromConfig(asRecord(tradingAgentsData?.data?.local_overrides)));
      const nextRoleDrafts = Object.fromEntries(
        Object.entries(tradingAgentsData?.data?.role_configs || {}).map(([role, config]) => [role, roleDraftFromConfig(config)])
      );
      setRoleDrafts(nextRoleDrafts);
      if (!overviewData && !tradingAgentsData) throw new Error("配置中心接口暂不可用");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const sections = overview?.data?.sections || [];
  const effective = asRecord(tradingAgents?.data?.effective);
  const mode = asRecord(effective.mode);
  const llm = asRecord(effective.llm);
  const service = asRecord(effective.service);
  const dataBoundary = asRecord(tradingAgents?.data?.data_boundary);
  const customAgents = tradingAgents?.data?.custom_agents || [];

  const roleRows = useMemo(() => Object.entries(tradingAgents?.data?.role_configs || {}), [tradingAgents?.data?.role_configs]);
  const tradingAgentSwitches: Array<{ key: TradingAgentsSwitchKey; label: string; enabled: boolean }> = [
    { key: "background_run", label: "默认后台运行", enabled: tradingAgentsDraft.background_run },
    { key: "save_full_output", label: "保存完整输出", enabled: tradingAgentsDraft.save_full_output },
    { key: "write_audit", label: "写入审计", enabled: tradingAgentsDraft.write_audit },
  ];

  function updateRoleDraft(role: string, patch: Partial<RoleDraft>) {
    setRoleDrafts((current) => ({
      ...current,
      [role]: {
        ...(current[role] || roleDraftFromConfig(asRecord(tradingAgents?.data?.role_configs?.[role]))),
        ...patch,
      },
    }));
  }

  function updateTradingAgentsDraft(patch: Partial<TradingAgentsDraft>) {
    setTradingAgentsDraft((current) => ({ ...current, ...patch }));
  }

  async function saveTradingAgentsConfig() {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const timeout = Number(tradingAgentsDraft.max_runtime_seconds || 300);
      if (!Number.isFinite(timeout)) throw new Error("最大运行时间必须是数字");
      const payload = {
        tradingagents: {
          default_mode: tradingAgentsDraft.default_mode || "context_adapter",
          llm_provider: tradingAgentsDraft.llm_provider || null,
          model: tradingAgentsDraft.model || null,
          base_url: tradingAgentsDraft.base_url || null,
          max_runtime_seconds: timeout,
          background_run: tradingAgentsDraft.background_run,
          prompt_version: tradingAgentsDraft.prompt_version || "phase2.zh-CN.v1",
          output_language: tradingAgentsDraft.output_language || "zh-CN",
          save_full_output: tradingAgentsDraft.save_full_output,
          write_audit: tradingAgentsDraft.write_audit,
        },
      };
      const res = await fetch("/api/v1/config-center/tradingagents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "TradingAgents 配置保存失败");
      setMessage("TradingAgents 默认运行配置已保存。");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function saveAgent() {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const payload = {
        agent_id: draft.agent_id,
        display_name: draft.display_name || draft.agent_id,
        enabled: draft.enabled,
        llm_provider: draft.llm_provider || null,
        model: draft.model || null,
        base_url: draft.base_url || null,
        prompt: draft.prompt,
        prompt_version: draft.prompt_version || "custom.v1",
        skill: draft.skill,
        output_language: "zh-CN",
        save_full_output: true,
        write_audit: true,
      };
      const res = await fetch("/api/v1/config-center/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "自定义 Agent 保存失败");
      setMessage(editingAgentId ? "自定义 Agent 已更新。" : "自定义 Agent 已保存。");
      setDraft(emptyDraft);
      setEditingAgentId("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function saveRole(role: string) {
    const roleDraft = roleDrafts[role];
    if (!roleDraft) return;
    setSavingRole(role);
    setMessage("");
    setError("");
    try {
      const payload = {
        enabled: roleDraft.enabled,
        llm_provider: roleDraft.llm_provider || null,
        model: roleDraft.model || null,
        base_url: roleDraft.base_url || null,
        prompt_version: roleDraft.prompt_version,
        prompt: roleDraft.prompt,
        skill: roleDraft.skill,
      };
      const res = await fetch(`/api/v1/config-center/tradingagents/roles/${encodeURIComponent(role)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "角色配置保存失败");
      setMessage(`${role} 角色配置已保存。`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingRole("");
    }
  }

  async function deleteAgent(agentId: string) {
    if (!agentId) return;
    setDeletingAgentId(agentId);
    setMessage("");
    setError("");
    try {
      const res = await fetch(`/api/v1/config-center/agents/${encodeURIComponent(agentId)}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "自定义 Agent 删除失败");
      setMessage(`${agentId} 已删除。`);
      if (editingAgentId === agentId) {
        setDraft(emptyDraft);
        setEditingAgentId("");
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeletingAgentId("");
    }
  }

  function editAgent(agent: JsonRecord) {
    const agentDraft = agentDraftFromRecord(agent);
    setDraft(agentDraft);
    setEditingAgentId(agentDraft.agent_id);
    setMessage(`正在编辑 ${agentDraft.agent_id}`);
    setError("");
  }

  function newAgent() {
    setDraft(emptyDraft);
    setEditingAgentId("");
    setMessage("");
    setError("");
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppTopNav
        activeSection="config-center"
        title="配置中心"
        subtitle="TradingAgents、数据源、风控、回测与安全配置"
        rightSlot={
          <Button size="sm" variant="outline" className="border-border" onClick={() => void refresh()} disabled={loading || saving}>
            <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
            刷新
          </Button>
        }
      />

      <main className="container mx-auto space-y-6 px-4 py-6">
        {(error || message) && (
          <div className={cn("rounded-lg border p-3 text-sm", error ? "border-rose-500/30 bg-rose-500/10 text-rose-200" : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200")}>
            {error || message}
          </div>
        )}

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {sections.map((section) => {
            const Icon = SECTION_ICONS[section.key] || Settings2;
            return (
              <Card key={section.key} className="border-white/10 bg-white/[0.04]">
                <CardContent className="flex items-start gap-3 p-4">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-cyan-500/12 text-cyan-200">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium text-white">{section.title}</p>
                      <Badge variant="outline" className={statusClass(section.status)}>{section.status}</Badge>
                    </div>
                    <p className="mt-2 truncate text-xs text-muted-foreground">{section.api}</p>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="flex items-center gap-2 text-white">
                  <Brain className="h-5 w-5 text-cyan-200" />
                  TradingAgents 有效配置
                </CardTitle>
                <Button size="sm" onClick={() => void saveTradingAgentsConfig()} disabled={saving || loading}>
                  <Save className="mr-2 h-4 w-4" />
                  保存默认配置
                </Button>
              </div>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-3">
              <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                <p className="text-xs text-muted-foreground">默认模式</p>
                <p className="mt-2 text-lg font-semibold text-white">{valueText(mode.configured, "context_adapter")}</p>
                <p className="mt-1 text-xs text-muted-foreground">Full Graph Ready: {valueText(mode.fullGraphReady)}</p>
              </div>
              <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                <p className="text-xs text-muted-foreground">LLM</p>
                <p className="mt-2 text-lg font-semibold text-white">{valueText(llm.provider)}</p>
                <p className="mt-1 text-xs text-muted-foreground">{valueText(llm.model)} / {valueText(llm.baseUrl)}</p>
              </div>
              <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                <p className="text-xs text-muted-foreground">服务</p>
                <p className="mt-2 text-lg font-semibold text-white">{valueText(service.status)}</p>
                <p className="mt-1 text-xs text-muted-foreground">timeout {valueText(service.timeout_seconds)}s</p>
              </div>
              <div className="md:col-span-3 rounded-lg border border-emerald-400/20 bg-emerald-500/10 p-3 text-sm text-emerald-100">
                <CheckCircle2 className="mr-2 inline h-4 w-4" />
                {valueText(dataBoundary.agent_input_policy, "local_storage_only")}，{valueText(dataBoundary.pit_rule, "available_time <= as_of_time")}，外部绕过：{valueText(dataBoundary.externalFallbackAllowed)}
              </div>
              <div className="md:col-span-3 grid gap-3 rounded-lg border border-white/10 bg-black/20 p-3 md:grid-cols-3">
                <div className="space-y-1">
                  <Label className="text-xs">默认模式</Label>
                  <Input value={tradingAgentsDraft.default_mode} onChange={(e) => updateTradingAgentsDraft({ default_mode: e.target.value })} placeholder="context_adapter" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">LLM Provider</Label>
                  <Input value={tradingAgentsDraft.llm_provider} onChange={(e) => updateTradingAgentsDraft({ llm_provider: e.target.value })} placeholder="未填则沿用运行时默认" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">模型</Label>
                  <Input value={tradingAgentsDraft.model} onChange={(e) => updateTradingAgentsDraft({ model: e.target.value })} placeholder="gpt / deepseek / qwen" />
                </div>
                <div className="space-y-1 md:col-span-2">
                  <Label className="text-xs">Base URL</Label>
                  <Input value={tradingAgentsDraft.base_url} onChange={(e) => updateTradingAgentsDraft({ base_url: e.target.value })} placeholder="模型 API 地址" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">最大运行时间（秒）</Label>
                  <Input inputMode="numeric" value={tradingAgentsDraft.max_runtime_seconds} onChange={(e) => updateTradingAgentsDraft({ max_runtime_seconds: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Prompt 版本</Label>
                  <Input value={tradingAgentsDraft.prompt_version} onChange={(e) => updateTradingAgentsDraft({ prompt_version: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">输出语言</Label>
                  <Input value={tradingAgentsDraft.output_language} onChange={(e) => updateTradingAgentsDraft({ output_language: e.target.value })} />
                </div>
                <div className="grid gap-2 md:col-span-3 sm:grid-cols-3">
                  {tradingAgentSwitches.map(({ key, label, enabled }) => (
                    <Button
                      key={key}
                      type="button"
                      variant="outline"
                      className={cn("justify-start border-white/10", enabled ? "text-emerald-200" : "text-slate-300")}
                      onClick={() => updateTradingAgentsDraft({ [key]: !enabled })}
                    >
                      {enabled ? "启用" : "关闭"} · {label}
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Shield className="h-5 w-5 text-emerald-200" />
                关键配置入口
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 text-sm">
              <Link className="rounded-lg border border-white/10 px-3 py-2 text-cyan-100 hover:bg-white/10" href="/risk">RiskGuard 阈值与熔断</Link>
              <Link className="rounded-lg border border-white/10 px-3 py-2 text-cyan-100 hover:bg-white/10" href="/data-governance">数据治理与清洗规则</Link>
              <Link className="rounded-lg border border-white/10 px-3 py-2 text-cyan-100 hover:bg-white/10" href="/data-sources">OpenBB / 数据源状态</Link>
              <Link className="rounded-lg border border-white/10 px-3 py-2 text-cyan-100 hover:bg-white/10" href="/monitor">TradingAgents 运维监控</Link>
              <Link className="rounded-lg border border-white/10 px-3 py-2 text-cyan-100 hover:bg-white/10" href="/backtest">回测/回放参数</Link>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Bot className="h-5 w-5 text-violet-200" />
                Agent 角色配置
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {roleRows.map(([role, config]) => {
                const current = roleDrafts[role] || roleDraftFromConfig(config);
                const llmInfo = asRecord(config.effective_llm);
                const isSavingRole = savingRole === role;
                return (
                  <div key={role} className="rounded-lg border border-white/10 bg-black/20 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="font-medium text-white">{role}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          LLM: {valueText(llmInfo.provider)} / {valueText(llmInfo.model)} / 默认继承：{valueText(llmInfo.uses_default)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className={cn("h-8 border-white/10", current.enabled ? "text-emerald-200" : "text-slate-300")}
                          onClick={() => updateRoleDraft(role, { enabled: !current.enabled })}
                          disabled={Boolean(savingRole)}
                        >
                          {current.enabled ? "启用" : "关闭"}
                        </Button>
                        <Button size="sm" className="h-8" onClick={() => void saveRole(role)} disabled={Boolean(savingRole)}>
                          <Save className="mr-2 h-3.5 w-3.5" />
                          {isSavingRole ? "保存中" : "保存"}
                        </Button>
                      </div>
                    </div>
                    <div className="mt-3 grid gap-2 md:grid-cols-2">
                      <div className="space-y-1">
                        <Label className="text-xs">Prompt 版本</Label>
                        <Input value={current.prompt_version} onChange={(e) => updateRoleDraft(role, { prompt_version: e.target.value })} />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Skill</Label>
                        <Input value={current.skill} onChange={(e) => updateRoleDraft(role, { skill: e.target.value })} />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">LLM Provider</Label>
                        <Input value={current.llm_provider} onChange={(e) => updateRoleDraft(role, { llm_provider: e.target.value })} placeholder="未填则使用默认" />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">模型</Label>
                        <Input value={current.model} onChange={(e) => updateRoleDraft(role, { model: e.target.value })} placeholder="未填则使用默认" />
                      </div>
                      <div className="space-y-1 md:col-span-2">
                        <Label className="text-xs">Base URL</Label>
                        <Input value={current.base_url} onChange={(e) => updateRoleDraft(role, { base_url: e.target.value })} placeholder="未填则使用默认" />
                      </div>
                      <div className="space-y-1 md:col-span-2">
                        <Label className="text-xs">Prompt</Label>
                        <textarea
                          className="min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
                          value={current.prompt}
                          onChange={(e) => updateRoleDraft(role, { prompt: e.target.value })}
                          placeholder="角色级 Prompt 覆盖；留空则按 Prompt 版本加载"
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="flex items-center gap-2 text-white">
                  <Save className="h-5 w-5 text-cyan-200" />
                  自定义 Agent
                </CardTitle>
                <Button size="sm" variant="outline" className="border-border" onClick={newAgent} disabled={saving}>
                  新建
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {editingAgentId && (
                <div className="rounded-lg border border-cyan-400/20 bg-cyan-500/10 p-3 text-sm text-cyan-100">
                  正在编辑 {editingAgentId}；保存会覆盖同 ID 配置。
                </div>
              )}
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <Label>Agent ID</Label>
                  <Input value={draft.agent_id} onChange={(e) => setDraft({ ...draft, agent_id: e.target.value })} placeholder="macro_event_agent" />
                </div>
                <div className="space-y-1">
                  <Label>显示名</Label>
                  <Input value={draft.display_name} onChange={(e) => setDraft({ ...draft, display_name: e.target.value })} placeholder="宏观事件 Agent" />
                </div>
                <div className="space-y-1">
                  <Label>状态</Label>
                  <Button
                    type="button"
                    variant="outline"
                    className={cn("w-full justify-start border-white/10", draft.enabled ? "text-emerald-200" : "text-slate-300")}
                    onClick={() => setDraft({ ...draft, enabled: !draft.enabled })}
                  >
                    {draft.enabled ? "启用" : "关闭"}
                  </Button>
                </div>
                <div className="space-y-1">
                  <Label>Prompt 版本</Label>
                  <Input value={draft.prompt_version} onChange={(e) => setDraft({ ...draft, prompt_version: e.target.value })} placeholder="custom.v1" />
                </div>
                <div className="space-y-1">
                  <Label>LLM Provider</Label>
                  <Input value={draft.llm_provider} onChange={(e) => setDraft({ ...draft, llm_provider: e.target.value })} placeholder="未填则使用默认" />
                </div>
                <div className="space-y-1">
                  <Label>模型</Label>
                  <Input value={draft.model} onChange={(e) => setDraft({ ...draft, model: e.target.value })} placeholder="未填则使用默认" />
                </div>
                <div className="space-y-1 md:col-span-2">
                  <Label>Base URL</Label>
                  <Input value={draft.base_url} onChange={(e) => setDraft({ ...draft, base_url: e.target.value })} placeholder="未填则使用默认" />
                </div>
                <div className="space-y-1 md:col-span-2">
                  <Label>Prompt</Label>
                  <textarea
                    className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    value={draft.prompt}
                    onChange={(e) => setDraft({ ...draft, prompt: e.target.value })}
                    placeholder="只使用本地 AnalysisContext 和已入库新闻/宏观数据"
                  />
                </div>
                <div className="space-y-1 md:col-span-2">
                  <Label>Skill</Label>
                  <Input value={draft.skill} onChange={(e) => setDraft({ ...draft, skill: e.target.value })} placeholder="macro_event_analysis" />
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void saveAgent()} disabled={saving || !draft.agent_id}>
                  <Save className="mr-2 h-4 w-4" />
                  {editingAgentId ? "更新 Agent" : "保存 Agent"}
                </Button>
                {editingAgentId && (
                  <Button variant="outline" className="border-border" onClick={newAgent} disabled={saving}>
                    取消编辑
                  </Button>
                )}
              </div>
              <div className="space-y-2">
                {customAgents.length === 0 ? (
                  <p className="text-sm text-muted-foreground">暂无自定义 Agent。</p>
                ) : (
                  customAgents.map((agent) => {
                    const llmInfo = asRecord(agent.effective_llm);
                    return (
                      <div key={String(agent.agent_id)} className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium text-white">{valueText(agent.display_name)} · {valueText(agent.agent_id)}</span>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className={statusClass(agent.enabled ? "ready" : "check")}>{agent.enabled ? "启用" : "关闭"}</Badge>
                            <Button size="sm" variant="outline" className="h-8 border-border" onClick={() => editAgent(agent)}>
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-8 border-rose-500/30 text-rose-200 hover:bg-rose-500/10"
                              onClick={() => void deleteAgent(String(agent.agent_id))}
                              disabled={Boolean(deletingAgentId)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">LLM: {valueText(llmInfo.provider)} / {valueText(llmInfo.model)} / 默认继承：{valueText(llmInfo.uses_default)}</p>
                        <p className="mt-1 text-xs text-muted-foreground">Prompt: {valueText(agent.prompt_version)} · Skill: {valueText(agent.skill)}</p>
                      </div>
                    );
                  })
                )}
              </div>
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}
