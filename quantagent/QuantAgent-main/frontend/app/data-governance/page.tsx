"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  CheckCircle2,
  Database,
  GitBranch,
  ListChecks,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
} from "lucide-react";

import { AppTopNav } from "@/components/navigation/AppTopNav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type JsonRecord = Record<string, unknown>;
type PreviewType = "bars" | "quotes" | "news" | "macro" | "fundamentals" | "corporate_actions" | "adjustment_factors";

interface GovernanceOverview {
  data?: {
    governance?: JsonRecord;
    coverage?: JsonRecord;
    storage_contract?: JsonRecord;
    quality?: JsonRecord;
    contracts?: JsonRecord;
  };
}

interface QualityPayload {
  data?: {
    thresholds?: JsonRecord;
    checks?: Array<{ id: string; status: string; detail: string }>;
  };
  meta?: JsonRecord;
}

interface RulesPayload {
  data?: Array<JsonRecord>;
  meta?: JsonRecord;
}

interface PreviewPayload {
  data?: Array<JsonRecord>;
  meta?: JsonRecord;
}

interface RuleDraft {
  rule_id: string;
  data_type: string;
  description: string;
  changed_data_store: string;
  version: string;
}

const emptyRule: RuleDraft = {
  rule_id: "",
  data_type: "bar",
  description: "",
  changed_data_store: "data/governance/changed_items",
  version: "1",
};

function asRecord(value: unknown): JsonRecord {
  return typeof value === "object" && value !== null ? (value as JsonRecord) : {};
}

function statusClass(status?: string) {
  if (status === "ready") return "border-emerald-400/30 bg-emerald-500/15 text-emerald-200";
  if (status === "partial") return "border-amber-400/30 bg-amber-500/15 text-amber-200";
  return "border-slate-400/25 bg-slate-500/15 text-slate-300";
}

function valueText(value: unknown, fallback = "暂无") {
  if (value == null || value === "") return fallback;
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.length ? value.join("、") : fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function shortValue(value: unknown, max = 80) {
  const text = valueText(value, "");
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
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

export default function DataGovernancePage() {
  const [overview, setOverview] = useState<GovernanceOverview | null>(null);
  const [quality, setQuality] = useState<QualityPayload | null>(null);
  const [rules, setRules] = useState<RulesPayload | null>(null);
  const [preview, setPreview] = useState<PreviewPayload | null>(null);
  const [previewType, setPreviewType] = useState<PreviewType>("bars");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState("1h");
  const [draft, setDraft] = useState<RuleDraft>(emptyRule);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const loadPreview = useCallback(async (type = previewType) => {
    const params = new URLSearchParams({
      data_type: type,
      symbol,
      interval,
      limit: "20",
    });
    const data = await fetchJson<PreviewPayload>(`/api/v1/data-governance/preview?${params.toString()}`);
    setPreview(data);
  }, [interval, previewType, symbol]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [overviewData, qualityData, rulesData] = await Promise.all([
        fetchJson<GovernanceOverview>("/api/v1/data-governance/overview"),
        fetchJson<QualityPayload>("/api/v1/data-governance/quality"),
        fetchJson<RulesPayload>("/api/v1/data-governance/cleaning-rules"),
      ]);
      setOverview(overviewData);
      setQuality(qualityData);
      setRules(rulesData);
      await loadPreview();
      if (!overviewData && !qualityData && !rulesData) throw new Error("数据治理接口暂不可用");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [loadPreview]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const qualityData = asRecord(overview?.data?.quality);
  const coverage = asRecord(overview?.data?.coverage);
  const storageContract = asRecord(overview?.data?.storage_contract);
  const storageTables = asRecord(storageContract.tables);
  const storageTableNames = Object.keys(storageTables);
  const lifecycle = asRecord(storageContract.backup_and_lifecycle);
  const schedulerJobs = asStringArray(asRecord(storageContract.scheduler_contract).jobs);
  const previewRows = preview?.data || [];
  const checks = quality?.data?.checks || [];
  const cleaningRules = rules?.data || [];

  const providers = useMemo(() => {
    const rows = Array.isArray(coverage.market_bars) ? coverage.market_bars as JsonRecord[] : [];
    return Array.from(new Set(rows.map((row) => String(row.provider || "unknown")))).slice(0, 8);
  }, [coverage.market_bars]);

  async function saveRule() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const payload = {
        rule_id: draft.rule_id,
        data_type: draft.data_type,
        enabled: true,
        version: Number(draft.version || 1),
        description: draft.description,
        changed_data_store: draft.changed_data_store,
      };
      const res = await fetch("/api/v1/data-governance/cleaning-rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "清洗规则保存失败");
      setMessage("清洗规则版本已保存。");
      setDraft(emptyRule);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  function selectPreview(type: PreviewType) {
    setPreviewType(type);
    void loadPreview(type);
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppTopNav
        activeSection="data-governance"
        title="数据治理"
        subtitle="数据源、预览、清洗版本与血缘追溯"
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
          <Card className="border-white/10 bg-white/[0.04]">
            <CardContent className="p-4">
              <p className="flex items-center gap-2 text-xs text-muted-foreground"><Database className="h-4 w-4 text-cyan-200" />行情源组</p>
              <p className="mt-2 text-2xl font-semibold text-white">{valueText(qualityData.market_source_groups, "0")}</p>
              <p className="mt-1 text-xs text-muted-foreground">{providers.length ? providers.join("、") : "暂无 provider 记录"}</p>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/[0.04]">
            <CardContent className="p-4">
              <p className="flex items-center gap-2 text-xs text-muted-foreground"><Activity className="h-4 w-4 text-emerald-200" />宏观指标</p>
              <p className="mt-2 text-2xl font-semibold text-white">{valueText(qualityData.macro_indicator_count, "0")}</p>
              <p className="mt-1 text-xs text-muted-foreground">DuckDB macro_indicators</p>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/[0.04]">
            <CardContent className="p-4">
              <p className="flex items-center gap-2 text-xs text-muted-foreground"><ListChecks className="h-4 w-4 text-violet-200" />清洗规则</p>
              <p className="mt-2 text-2xl font-semibold text-white">{cleaningRules.length}</p>
              <p className="mt-1 text-xs text-muted-foreground">版本化保存，变更数据单独追溯</p>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/[0.04]">
            <CardContent className="p-4">
              <p className="flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck className="h-4 w-4 text-emerald-200" />PIT 规则</p>
              <p className="mt-2 text-lg font-semibold text-white">{valueText(qualityData.pit_rule, "available_time <= as_of_time")}</p>
              <p className="mt-1 text-xs text-muted-foreground">研究台/回测/Agent 共用</p>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[0.85fr_1.15fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <CheckCircle2 className="h-5 w-5 text-emerald-200" />
                质量检查
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {checks.map((check) => (
                <div key={check.id} className="rounded-lg border border-white/10 bg-black/20 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium text-white">{check.id}</p>
                    <Badge variant="outline" className={statusClass(check.status)}>{check.status}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{check.detail}</p>
                </div>
              ))}
              <div className="rounded-lg border border-cyan-400/20 bg-cyan-500/10 p-3 text-sm text-cyan-100">
                <Link href="/data-sources" className="hover:underline">查看数据源状态</Link>
                <span className="mx-2 text-cyan-300/50">/</span>
                <Link href="/config-center" className="hover:underline">进入配置中心</Link>
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <CardTitle className="flex items-center gap-2 text-white">
                  <Search className="h-5 w-5 text-cyan-200" />
                  数据预览
                </CardTitle>
                <div className="flex flex-wrap gap-2">
                  {(["bars", "quotes", "news", "macro", "fundamentals", "corporate_actions", "adjustment_factors"] as PreviewType[]).map((type) => (
                    <Button key={type} size="sm" variant={previewType === type ? "default" : "outline"} className="h-8" onClick={() => selectPreview(type)}>
                      {type}
                    </Button>
                  ))}
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-[1fr_0.7fr_auto]">
                <Input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} placeholder="BTCUSDT" />
                <Input value={interval} onChange={(event) => setInterval(event.target.value)} placeholder="1h" />
                <Button variant="outline" className="border-border" onClick={() => void loadPreview()}>
                  <RefreshCw className="mr-2 h-4 w-4" />
                  查询
                </Button>
              </div>
              <div className="overflow-x-auto rounded-lg border border-white/10">
                <table className="w-full min-w-[760px] text-left text-sm">
                  <thead className="bg-white/[0.03] text-xs text-muted-foreground">
                    <tr>
                      {Object.keys(previewRows[0] || { id: "", symbol: "", event_time: "", available_time: "", provider: "" }).slice(0, 8).map((key) => (
                        <th key={key} className="px-3 py-2">{key}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.length === 0 ? (
                      <tr><td className="px-3 py-6 text-muted-foreground" colSpan={8}>暂无本地数据。</td></tr>
                    ) : (
                      previewRows.slice(0, 20).map((row, index) => (
                        <tr key={String(row.id || row.url || index)} className="border-t border-white/10">
                          {Object.keys(previewRows[0] || {}).slice(0, 8).map((key) => (
                            <td key={key} className="max-w-[220px] px-3 py-2 text-muted-foreground">{shortValue(row[key])}</td>
                          ))}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-muted-foreground">来源：{valueText(preview?.meta?.source_endpoint)} · {valueText(preview?.meta?.pit_rule, "available_time <= as_of_time")}</p>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1fr_0.8fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Database className="h-5 w-5 text-cyan-200" />
                存储契约
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {storageTableNames.slice(0, 15).map((name) => {
                  const table = asRecord(storageTables[name]);
                  const indexes = Array.isArray(table.indexes) ? table.indexes : [];
                  return (
                    <div key={name} className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
                      <p className="font-medium text-white">{name}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{shortValue(table.purpose, 90)}</p>
                      <p className="mt-2 text-xs text-cyan-100">{Array.isArray(table.pit_fields) ? table.pit_fields.join(" / ") : valueText(storageContract.visibility_rule)}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{indexes.length} indexes</p>
                    </div>
                  );
                })}
              </div>
              <p className="text-xs text-muted-foreground">
                版本：{valueText(storageContract.schema_version)} · 引擎：{valueText(asRecord(storageContract.storage_engine).target)} · Agent：{valueText(storageContract.agent_input_policy)}
              </p>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <GitBranch className="h-5 w-5 text-emerald-200" />
                手动入库与生命周期
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="rounded-lg border border-emerald-400/20 bg-emerald-500/10 p-3">
                <p className="font-medium text-emerald-100">/api/v1/meta/ingest</p>
                <p className="mt-1 text-muted-foreground">dry-run / 本地 upsert / etl_job_log / data_lineage</p>
              </div>
              <div className="rounded-lg border border-cyan-400/20 bg-cyan-500/10 p-3">
                <p className="font-medium text-cyan-100">/api/v1/meta/refresh-financials</p>
                <p className="mt-1 text-muted-foreground">显式 OpenBB 获取 fundamentals/actions/adjustment factors，再进入本地 ingest。</p>
              </div>
              {schedulerJobs.length === 0 ? (
                <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-muted-foreground">调度合同暂未返回。</div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {schedulerJobs.map((job) => (
                    <Badge key={job} variant="outline" className="border-white/15 bg-white/[0.04] text-slate-200">{job}</Badge>
                  ))}
                </div>
              )}
              <div className="grid gap-2 sm:grid-cols-2">
                {Object.entries(lifecycle).map(([key, value]) => (
                  <div key={key} className="rounded-lg border border-white/10 bg-black/20 p-3">
                    <p className="text-xs text-muted-foreground">{key}</p>
                    <p className="mt-1 font-medium text-white">{valueText(value)}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <ListChecks className="h-5 w-5 text-violet-200" />
                清洗规则版本
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {cleaningRules.map((rule) => (
                <div key={String(rule.rule_id)} className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium text-white">{valueText(rule.rule_id)}</p>
                    <Badge variant="outline" className={statusClass(rule.enabled ? "ready" : "check")}>v{valueText(rule.version, "1")}</Badge>
                  </div>
                  <p className="mt-1 text-muted-foreground">{valueText(rule.description)}</p>
                  <p className="mt-1 text-xs text-muted-foreground">changed store: {valueText(rule.changed_data_store)}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Save className="h-5 w-5 text-cyan-200" />
                新增清洗规则
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <Label>Rule ID</Label>
                  <Input value={draft.rule_id} onChange={(event) => setDraft({ ...draft, rule_id: event.target.value })} placeholder="bar_gap_fill.v1" />
                </div>
                <div className="space-y-1">
                  <Label>数据类型</Label>
                  <Input value={draft.data_type} onChange={(event) => setDraft({ ...draft, data_type: event.target.value })} placeholder="bar/news/macro" />
                </div>
                <div className="space-y-1">
                  <Label>版本</Label>
                  <Input value={draft.version} onChange={(event) => setDraft({ ...draft, version: event.target.value })} placeholder="1" />
                </div>
                <div className="space-y-1">
                  <Label>变更数据存储</Label>
                  <Input value={draft.changed_data_store} onChange={(event) => setDraft({ ...draft, changed_data_store: event.target.value })} />
                </div>
                <div className="space-y-1 md:col-span-2">
                  <Label>说明</Label>
                  <Input value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="记录补空、异常值标记或单位标准化规则" />
                </div>
              </div>
              <Button onClick={() => void saveRule()} disabled={saving || !draft.rule_id}>
                <Save className="mr-2 h-4 w-4" />
                保存规则
              </Button>
            </CardContent>
          </Card>
        </section>

        <Card className="border-white/10 bg-white/[0.04]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-white">
              <GitBranch className="h-5 w-5 text-emerald-200" />
              数据血缘
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
              <p className="font-medium text-white">Bars</p>
              <p className="mt-1 text-muted-foreground">ClickHouse market_bars · provider/exchange/source_version/schema_version</p>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
              <p className="font-medium text-white">News</p>
              <p className="mt-1 text-muted-foreground">DuckDB news_articles · raw_payload_id/url/available_time</p>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
              <p className="font-medium text-white">Macro</p>
              <p className="mt-1 text-muted-foreground">DuckDB macro_indicators · indicator/timestamp/available_time</p>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
              <p className="font-medium text-white">Agent Context</p>
              <p className="mt-1 text-muted-foreground">context_hash/input_snapshot_ids/data_versions/as_of_time</p>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
