"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, RotateCcw, Save, Shield, SquarePower, Undo2 } from "lucide-react";

import { AppTopNav } from "@/components/navigation/AppTopNav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type RiskConfig = Record<string, number | string[] | string>;

interface RiskConfigMetadata {
  schema_version: string;
  config: RiskConfig;
  kill_switch_active: boolean;
  source: string;
}

const NUMERIC_FIELDS = [
  { key: "MAX_SINGLE_POSITION_PCT", label: "单标的仓位上限", group: "仓位", max: 100 },
  { key: "MAX_TOTAL_EXPOSURE_PCT", label: "总风险敞口上限", group: "仓位", max: 500 },
  { key: "MAX_TOTAL_DRAWDOWN_PCT", label: "最大回撤熔断", group: "损失", max: 100 },
  { key: "MAX_DAILY_LOSS_PCT", label: "日内最大亏损", group: "损失", max: 100 },
  { key: "PRICE_DEVIATION_PCT", label: "价格偏离拦截", group: "订单", max: 100 },
  { key: "MAINTENANCE_MARGIN_RATE", label: "维持保证金率", group: "保证金", max: 100 },
  { key: "MARGIN_WARNING_LEVEL", label: "保证金预警线", group: "保证金", max: 100 },
  { key: "PRE_LIQUIDATION_LEVEL", label: "预清算拦截线", group: "保证金", max: 100 },
  { key: "VOLATILITY_TARGET_PCT", label: "目标日波动率", group: "波动率", max: 100 },
  { key: "MAX_VOLATILITY_THRESHOLD", label: "极端波动阈值", group: "波动率", max: 500 },
];

const MONEY_FIELDS = [
  { key: "MIN_ORDER_NOTIONAL", label: "最小订单金额", group: "订单", max: 1000000 },
];

const ENUM_FIELDS = [
  {
    key: "WAIT_ORDER_INTENT_POLICY",
    label: "WAIT 处理策略",
    options: [
      { value: "record_flat", label: "记录 flat intent" },
      { value: "skip", label: "仅审计跳过" },
    ],
  },
  {
    key: "RISK_FAILURE_ACTION",
    label: "风控失败动作",
    options: [
      { value: "block", label: "block" },
      { value: "reduce", label: "reduce" },
      { value: "warn", label: "warn" },
    ],
  },
];

function statusClass(active: boolean) {
  return active
    ? "border-rose-400/30 bg-rose-500/15 text-rose-200"
    : "border-emerald-400/30 bg-emerald-500/15 text-emerald-200";
}

function toPercent(value: unknown) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) return "";
  return String(Number((numberValue * 100).toFixed(4)));
}

function fromPercent(value: string, key: string) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) throw new Error(`${key} 不是有效数字`);
  return numberValue / 100;
}

function numberText(value: unknown) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) return "";
  return String(numberValue);
}

function fromNumber(value: string, key: string) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) throw new Error(`${key} 不是有效数字`);
  return numberValue;
}

function enumText(value: unknown, fallback: string) {
  return typeof value === "string" && value ? value : fallback;
}

function forbiddenText(config: RiskConfig | null) {
  const value = config?.FORBIDDEN_SYMBOLS;
  return Array.isArray(value) ? value.join(", ") : "";
}

function splitSymbols(value: string) {
  return value
    .split(",")
    .map((item) => item.trim().toUpperCase().replace("/", ""))
    .filter(Boolean);
}

export default function RiskConfigPage() {
  const [metadata, setMetadata] = useState<RiskConfigMetadata | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [forbiddenSymbols, setForbiddenSymbols] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/v1/risk/config-metadata", { cache: "no-store" });
      if (!response.ok) throw new Error("风控配置加载失败");
      const data = (await response.json()) as RiskConfigMetadata;
      setMetadata(data);
      setDraft(
        Object.fromEntries([
          ...NUMERIC_FIELDS.map((field) => [field.key, toPercent(data.config[field.key])]),
          ...MONEY_FIELDS.map((field) => [field.key, numberText(data.config[field.key])]),
          ...ENUM_FIELDS.map((field) => [field.key, enumText(data.config[field.key], String(field.options[0]?.value || ""))]),
        ]),
      );
      setForbiddenSymbols(forbiddenText(data.config));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const groupedFields = useMemo(() => {
    const groups: Record<string, typeof NUMERIC_FIELDS> = {};
    NUMERIC_FIELDS.forEach((field) => {
      groups[field.group] = [...(groups[field.group] || []), field];
    });
    return Object.entries(groups);
  }, []);

  async function saveConfig() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const payload: Record<string, number | string[] | string> = {};
      for (const field of NUMERIC_FIELDS) {
        payload[field.key] = fromPercent(draft[field.key] || "0", field.label);
      }
      for (const field of MONEY_FIELDS) {
        payload[field.key] = fromNumber(draft[field.key] || "0", field.label);
      }
      for (const field of ENUM_FIELDS) {
        payload[field.key] = draft[field.key] || String(field.options[0]?.value || "");
      }
      payload.FORBIDDEN_SYMBOLS = splitSymbols(forbiddenSymbols);

      const response = await fetch("/api/v1/risk/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "风控配置保存失败");
      setMessage("RiskGuard 配置已保存并写入审计。");
      await loadConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function resetConfig() {
    if (!window.confirm("重置 RiskGuard 热更新配置，恢复 settings 默认值？")) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/v1/risk/config/reset", { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "风控配置重置失败");
      setMessage("RiskGuard 配置已恢复默认值。");
      await loadConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function setKillSwitch(active: boolean) {
    const action = active ? "触发全局熔断" : "解除全局熔断";
    if (!window.confirm(`${action}？这会影响模拟盘新增订单。`)) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const path = active ? "/api/v1/risk/kill-switch/trigger" : "/api/v1/risk/kill-switch/reset";
      const response = await fetch(path, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || `${action}失败`);
      setMessage(active ? "全局熔断已触发。" : "全局熔断已解除。");
      await loadConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  const killSwitchActive = Boolean(metadata?.kill_switch_active);
  const fieldCompleteness = [...NUMERIC_FIELDS, ...MONEY_FIELDS, ...ENUM_FIELDS].filter((field) => {
    const value = draft[field.key];
    return typeof value === "string" && value.trim() !== "";
  }).length;
  const totalEditableFields = NUMERIC_FIELDS.length + MONEY_FIELDS.length + ENUM_FIELDS.length;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppTopNav
        activeSection="risk"
        title="风控配置"
        subtitle="RiskGuard 阈值、禁用标的与熔断"
        rightSlot={
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="border-border" onClick={() => void loadConfig()} disabled={loading || saving}>
              <RotateCcw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
              刷新
            </Button>
            <Button size="sm" onClick={() => void saveConfig()} disabled={saving || loading}>
              <Save className="mr-2 h-4 w-4" />
              保存
            </Button>
          </div>
        }
      />

      <main className="container mx-auto space-y-6 px-4 py-6">
        {(error || message) && (
          <div
            className={cn(
              "rounded-2xl border p-4 text-sm",
              error ? "border-rose-500/30 bg-rose-500/10 text-rose-200" : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
            )}
          >
            {error || message}
          </div>
        )}

        <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-white">
                    <Shield className="h-5 w-5 text-emerald-200" />
                    RiskGuard 状态
                  </CardTitle>
                  <p className="mt-2 text-xs text-muted-foreground">配置版本：{metadata?.schema_version || "risk_config.v1"}</p>
                </div>
                <Badge className={statusClass(killSwitchActive)}>{killSwitchActive ? "熔断中" : "允许交易"}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <p className="text-xs text-muted-foreground">字段覆盖</p>
                  <p className="mt-2 text-2xl font-semibold text-white">{fieldCompleteness}/{totalEditableFields}</p>
                  <p className="mt-1 text-xs text-muted-foreground">百分比字段按 0-100 输入，保存时转成后端 ratio。</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <p className="text-xs text-muted-foreground">禁用标的</p>
                  <p className="mt-2 truncate text-lg font-semibold text-white" title={forbiddenSymbols || "无"}>
                    {forbiddenSymbols || "无"}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">例如 BTCUSDT, DOGEUSDT</p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  className="border-rose-400/30 bg-rose-500/10 text-rose-100 hover:bg-rose-500/20"
                  onClick={() => void setKillSwitch(true)}
                  disabled={saving || killSwitchActive}
                >
                  <SquarePower className="mr-2 h-4 w-4" />
                  触发熔断
                </Button>
                <Button
                  variant="outline"
                  className="border-emerald-400/30 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/20"
                  onClick={() => void setKillSwitch(false)}
                  disabled={saving || !killSwitchActive}
                >
                  <Undo2 className="mr-2 h-4 w-4" />
                  解除熔断
                </Button>
                <Button variant="outline" className="border-border" onClick={() => void resetConfig()} disabled={saving}>
                  <AlertTriangle className="mr-2 h-4 w-4" />
                  恢复默认
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="text-white">禁止交易标的</CardTitle>
              <p className="text-xs text-muted-foreground">命中列表时，RiskGuard 会在下单前返回 FORBIDDEN_SYMBOL。</p>
            </CardHeader>
            <CardContent>
              <Label htmlFor="forbidden-symbols" className="mb-2 text-xs text-muted-foreground">
                逗号分隔
              </Label>
              <Input
                id="forbidden-symbols"
                value={forbiddenSymbols}
                onChange={(event) => setForbiddenSymbols(event.target.value)}
                placeholder="DOGEUSDT, SHIBUSDT"
                className="border-white/10 bg-black/20 font-mono"
              />
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          {groupedFields.map(([group, fields]) => (
            <Card key={group} className="border-white/10 bg-white/[0.04]">
              <CardHeader>
                <CardTitle className="text-white">{group}阈值</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                {fields.map((field) => (
                  <div key={field.key} className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <Label htmlFor={field.key} className="text-xs text-muted-foreground">
                        {field.label}
                      </Label>
                      <span className="font-mono text-[11px] text-muted-foreground">0-{field.max}%</span>
                    </div>
                    <div className="relative">
                      <Input
                        id={field.key}
                        inputMode="decimal"
                        value={draft[field.key] || ""}
                        onChange={(event) => setDraft((current) => ({ ...current, [field.key]: event.target.value }))}
                        className="border-white/10 bg-black/20 pr-9 font-mono"
                      />
                      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">%</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="text-white">订单执行契约</CardTitle>
              <p className="text-xs text-muted-foreground">低于最小金额的 OrderIntent 会被 RiskGuard 阻断并写入审计。</p>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              {MONEY_FIELDS.map((field) => (
                <div key={field.key} className="space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <Label htmlFor={field.key} className="text-xs text-muted-foreground">
                      {field.label}
                    </Label>
                    <span className="font-mono text-[11px] text-muted-foreground">0-{field.max}</span>
                  </div>
                  <Input
                    id={field.key}
                    inputMode="decimal"
                    value={draft[field.key] || ""}
                    onChange={(event) => setDraft((current) => ({ ...current, [field.key]: event.target.value }))}
                    className="border-white/10 bg-black/20 font-mono"
                  />
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="text-white">失败与 WAIT 策略</CardTitle>
              <p className="text-xs text-muted-foreground">风控失败在模拟执行中始终有效阻断，reduce/warn 仅作为审计意图保留。</p>
            </CardHeader>
            <CardContent className="grid gap-4">
              {ENUM_FIELDS.map((field) => (
                <div key={field.key} className="space-y-2">
                  <Label className="text-xs text-muted-foreground">{field.label}</Label>
                  <div className="flex flex-wrap gap-2">
                    {field.options.map((option) => (
                      <Button
                        key={option.value}
                        type="button"
                        variant="outline"
                        className={cn(
                          "border-white/10",
                          draft[field.key] === option.value ? "bg-emerald-500/15 text-emerald-100" : "text-slate-300",
                        )}
                        onClick={() => setDraft((current) => ({ ...current, [field.key]: option.value }))}
                      >
                        {option.label}
                      </Button>
                    ))}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </section>

        {loading && (
          <div className="fixed bottom-6 right-6 rounded-full border border-white/10 bg-black/60 px-4 py-2 text-sm text-slate-300 shadow-xl backdrop-blur">
            <RotateCcw className="mr-2 inline h-4 w-4 animate-spin" />
            正在加载风控配置
          </div>
        )}
      </main>
    </div>
  );
}
