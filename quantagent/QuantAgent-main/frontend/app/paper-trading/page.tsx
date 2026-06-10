"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  CheckCircle2,
  ExternalLink,
  FileJson,
  RefreshCw,
  Shield,
  TrendingUp,
  Wallet,
  XCircle,
} from "lucide-react";

import { AppTopNav } from "@/components/navigation/AppTopNav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type JsonRecord = Record<string, unknown>;

interface WorkbenchPayload {
  schema_version?: string;
  generated_at?: string;
  mode?: JsonRecord;
  data_boundary?: JsonRecord;
  account?: {
    status?: string;
    summary?: JsonRecord;
  };
  order_intents?: {
    status?: string;
    items?: JsonRecord[];
    total?: number;
  };
  risk_guard?: {
    status?: string;
    risk_status?: JsonRecord;
    config?: JsonRecord;
  };
  orders?: {
    status?: string;
    items?: JsonRecord[];
    total?: number;
  };
  positions?: {
    status?: string;
    items?: JsonRecord[];
    total?: number;
  };
  pnl?: {
    status?: string;
    summary?: JsonRecord;
    equity_curve?: {
      points?: Array<{ t?: string; v?: number; drawdown?: number }>;
      source?: string;
    };
  };
  execution_chain?: {
    chain?: string[];
    stages?: Array<{ key: string; label: string; count: number }>;
    counts?: JsonRecord;
    closed_loop_ready?: boolean;
  };
  apis?: JsonRecord;
  errors?: Array<{ section?: string; message?: string }>;
}

function asRecord(value: unknown): JsonRecord {
  return typeof value === "object" && value !== null ? (value as JsonRecord) : {};
}

function text(value: unknown, fallback = "—") {
  if (value == null || value === "") return fallback;
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function num(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function money(value: unknown) {
  const parsed = num(value, NaN);
  if (!Number.isFinite(parsed)) return "—";
  return parsed.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function pct(value: unknown) {
  const parsed = num(value, NaN);
  if (!Number.isFinite(parsed)) return "—";
  const shown = Math.abs(parsed) <= 1 ? parsed * 100 : parsed;
  return `${shown.toFixed(2)}%`;
}

function statusClass(status?: unknown) {
  const value = String(status || "").toLowerCase();
  if (["ready", "ok", "filled", "executed", "passed", "created"].includes(value)) {
    return "border-emerald-400/30 bg-emerald-500/15 text-emerald-200";
  }
  if (["blocked", "rejected", "error", "unavailable"].includes(value)) {
    return "border-rose-400/30 bg-rose-500/15 text-rose-200";
  }
  return "border-slate-400/25 bg-slate-500/15 text-slate-300";
}

function sparkline(points: Array<{ v?: number }>) {
  if (!points.length) return "";
  const values = points.map((point) => num(point.v)).filter((value) => Number.isFinite(value));
  if (!values.length) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = 320;
  const height = 72;
  const span = max - min || 1;
  return values
    .map((value, index) => {
      const x = values.length === 1 ? width : (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

async function fetchWorkbench(symbol: string, limit: number): Promise<WorkbenchPayload> {
  const params = new URLSearchParams({ limit: String(limit), exchange_id: "okx" });
  if (symbol.trim()) params.set("symbol", symbol.trim().toUpperCase());
  const res = await fetch(`/api/v1/trading/workbench?${params.toString()}`, { cache: "no-store" });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || "模拟交易台加载失败");
  return data as WorkbenchPayload;
}

export default function PaperTradingWorkbenchPage() {
  const [symbol, setSymbol] = useState("");
  const [payload, setPayload] = useState<WorkbenchPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPayload(await fetchWorkbench(symbol, 30));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const account = asRecord(payload?.account?.summary);
  const mode = asRecord(payload?.mode);
  const boundary = asRecord(payload?.data_boundary);
  const pnl = asRecord(payload?.pnl?.summary);
  const riskStatus = asRecord(payload?.risk_guard?.risk_status);
  const riskConfig = asRecord(payload?.risk_guard?.config);
  const intentRows = payload?.order_intents?.items || [];
  const orderRows = payload?.orders?.items || [];
  const positionRows = payload?.positions?.items || [];
  const chain = payload?.execution_chain;
  const points = useMemo(() => payload?.pnl?.equity_curve?.points || [], [payload?.pnl?.equity_curve?.points]);
  const line = useMemo(() => sparkline(points), [points]);

  const topCards = [
    { label: "总权益", value: `$${money(account.total_equity)}`, detail: `现金 $${money(account.cash_balance)}` },
    { label: "持仓价值", value: `$${money(account.position_value)}`, detail: `${text(account.open_positions, "0")} 个持仓` },
    { label: "未实现 PnL", value: `$${money(account.unrealized_pnl)}`, detail: `已实现 $${money(pnl.realized_pnl)}` },
    { label: "审计事件", value: text(payload?.order_intents?.total, "0"), detail: "OrderIntent / RiskGuard / PaperOrder" },
  ];

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppTopNav
        activeSection="paper"
        title="模拟交易台"
        subtitle="OrderIntent → RiskGuard → PaperOrder → PnL → AuditRecord"
        rightSlot={
          <div className="flex items-center gap-2">
            <Input
              className="h-9 w-32 border-border bg-background font-mono text-xs"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="BTCUSDT"
            />
            <Button size="sm" variant="outline" className="border-border" onClick={() => void refresh()} disabled={loading}>
              <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
              刷新
            </Button>
          </div>
        }
      />

      <main className="container mx-auto space-y-6 px-4 py-6">
        {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {topCards.map((card) => (
            <Card key={card.label} className="border-white/10 bg-white/[0.04]">
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">{card.label}</p>
                <p className="mt-2 text-2xl font-semibold text-white">{card.value}</p>
                <p className="mt-1 text-xs text-muted-foreground">{card.detail}</p>
              </CardContent>
            </Card>
          ))}
        </section>

        <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Wallet className="h-5 w-5 text-cyan-200" />
                账户 / 模式
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
              <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                <p className="text-xs text-muted-foreground">账户模式</p>
                <p className="mt-2 font-semibold text-white">{text(mode.account_mode, "paper")}</p>
              </div>
              <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                <p className="text-xs text-muted-foreground">实盘下单</p>
                <p className="mt-2 font-semibold text-white">{text(mode.real_ordering_enabled, "否")}</p>
              </div>
              <div className="rounded-lg border border-emerald-400/20 bg-emerald-500/10 p-3 sm:col-span-2">
                <CheckCircle2 className="mr-2 inline h-4 w-4 text-emerald-200" />
                {text(boundary.execution_mode, "paper_trading_only")}，OrderIntent 必需：{text(boundary.order_intent_required)}，RiskGuard 必需：{text(boundary.risk_guard_required)}，审计：{text(boundary.audit_mutability, "append_only")}
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <TrendingUp className="h-5 w-5 text-emerald-200" />
                PnL / 资金曲线
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-28 rounded-lg border border-white/10 bg-black/20 p-3">
                {line ? (
                  <svg viewBox="0 0 320 72" className="h-full w-full" role="img" aria-label="equity curve">
                    <polyline fill="none" stroke="rgb(34 211 238)" strokeWidth="2.5" points={line} />
                  </svg>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">暂无资金曲线</div>
                )}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">数据源：{text(payload?.pnl?.equity_curve?.source)}</p>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <FileJson className="h-5 w-5 text-violet-200" />
                OrderIntent 列表
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {intentRows.length ? intentRows.map((row) => {
                const risk = asRecord(row.risk);
                const links = asRecord(row.links);
                return (
                  <div key={`${text(row.audit_id)}-${text(row.action)}`} className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-white">{text(row.orderIntentId, "NO_ACTION")}</span>
                      <Badge variant="outline" className={statusClass(row.stage)}>{text(row.stage)}</Badge>
                    </div>
                    <div className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                      <div>{text(row.symbol)} · {text(row.side)} · 仓位 {pct(row.positionRatio)}</div>
                      <div>风控：{text(risk.passed)} · {text(risk.rule)}</div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Link href={text(links.audit, "/audit")}>
                        <Button size="sm" variant="outline" className="h-7 border-border text-xs">
                          <ExternalLink className="mr-1 h-3 w-3" />
                          审计
                        </Button>
                      </Link>
                      {row.decisionId ? (
                        <Link href={text(links.decision, "/decisions")}>
                          <Button size="sm" variant="outline" className="h-7 border-border text-xs">决策</Button>
                        </Link>
                      ) : null}
                    </div>
                  </div>
                );
              }) : <p className="text-sm text-muted-foreground">暂无 OrderIntent 审计事件。</p>}
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Shield className="h-5 w-5 text-emerald-200" />
                RiskGuard 检查区
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                  <p className="text-xs text-muted-foreground">全局熔断</p>
                  <p className="mt-2 font-semibold text-white">{text(riskStatus.kill_switch_active, "否")}</p>
                </div>
                <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                  <p className="text-xs text-muted-foreground">总敞口上限</p>
                  <p className="mt-2 font-semibold text-white">{pct(riskConfig.MAX_TOTAL_EXPOSURE_PCT)}</p>
                </div>
              </div>
              <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-muted-foreground">
                <div>单笔仓位：{pct(riskConfig.MAX_SINGLE_POSITION_PCT)}</div>
                <div>日最大亏损：{pct(riskConfig.MAX_DAILY_LOSS_PCT)}</div>
                <div>禁止标的：{Array.isArray(riskConfig.FORBIDDEN_SYMBOLS) ? riskConfig.FORBIDDEN_SYMBOLS.join("、") || "无" : "无"}</div>
              </div>
              <Link href="/risk">
                <Button size="sm" variant="outline" className="border-border">
                  风控配置
                </Button>
              </Link>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Activity className="h-5 w-5 text-cyan-200" />
                模拟订单 / 成交记录
              </CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr>
                    <th className="pb-2">订单</th>
                    <th className="pb-2">标的</th>
                    <th className="pb-2">方向</th>
                    <th className="pb-2">价格</th>
                    <th className="pb-2">PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {orderRows.length ? orderRows.map((order) => (
                    <tr key={text(order.orderId, text(order.order_id))} className="border-t border-white/10">
                      <td className="py-2 font-mono text-white">{text(order.orderId, text(order.order_id))}</td>
                      <td className="py-2 text-muted-foreground">{text(order.symbol)}</td>
                      <td className="py-2 text-muted-foreground">{text(order.side)}</td>
                      <td className="py-2 text-muted-foreground">${money(order.fillPrice || order.price)}</td>
                      <td className="py-2 text-muted-foreground">${money(order.pnl || order.realizedPnl)}</td>
                    </tr>
                  )) : (
                    <tr><td colSpan={5} className="py-4 text-muted-foreground">暂无模拟订单。</td></tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/[0.04]">
            <CardHeader>
              <CardTitle className="text-white">持仓面板</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {positionRows.length ? positionRows.map((position) => (
                <div key={text(position.symbol)} className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-white">{text(position.symbol)} · {text(position.side)}</span>
                    <Badge variant="outline" className={statusClass(position.riskStatus)}>{text(position.riskStatus, "normal")}</Badge>
                  </div>
                  <div className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                    <div>数量：{text(position.quantity)}</div>
                    <div>均价：${money(position.avgEntryPrice || position.avg_price)}</div>
                    <div>标记价：${money(position.markPrice || position.mark_price)}</div>
                    <div>PnL：${money(position.unrealizedPnl || position.pnl)} / {pct(position.unrealizedPnlPct || position.pnl_pct)}</div>
                  </div>
                </div>
              )) : <p className="text-sm text-muted-foreground">暂无持仓。</p>}
            </CardContent>
          </Card>
        </section>

        <Card className="border-white/10 bg-white/[0.04]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-white">
              {chain?.closed_loop_ready ? <CheckCircle2 className="h-5 w-5 text-emerald-200" /> : <XCircle className="h-5 w-5 text-slate-400" />}
              执行链详情
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-5">
              {(chain?.stages || []).map((stage) => (
                <div key={stage.key} className="rounded-lg border border-white/10 bg-black/20 p-3 text-center">
                  <p className="text-xs text-muted-foreground">{stage.label}</p>
                  <p className="mt-2 text-xl font-semibold text-white">{stage.count}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-sm text-muted-foreground">{(chain?.chain || ["OrderIntent", "RiskGuard", "PaperOrder", "PnL", "AuditRecord"]).join(" → ")}</p>
          </CardContent>
        </Card>

        {payload?.errors?.length ? (
          <Card className="border-amber-500/20 bg-amber-500/10">
            <CardContent className="space-y-1 p-4 text-sm text-amber-100">
              {payload.errors.map((item) => <div key={`${item.section}-${item.message}`}>{text(item.section)}：{text(item.message)}</div>)}
            </CardContent>
          </Card>
        ) : null}
      </main>
    </div>
  );
}
