"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { BarChart3, FileJson, FileSearch, GitBranch, History, Layers, ShieldCheck } from "lucide-react";

type LinkageLinks = Record<string, string | undefined>;

interface LinkagePayload {
  identity?: {
    symbol?: string;
    interval?: string;
    as_of_time?: string | null;
    context_hash?: string | null;
  };
  pit?: {
    rule?: string;
    agent_input_policy?: string;
    external_fallback_allowed?: boolean;
  };
  links?: LinkageLinks;
}

interface WorkbenchLinkBarProps {
  source: "research" | "backtest" | "audit" | "replay" | "decision" | "workbench";
  symbol?: string | null;
  interval?: string | null;
  asOfTime?: string | null;
  decisionId?: string | number | null;
  auditId?: string | number | null;
  backtestId?: string | number | null;
  replaySessionId?: string | null;
  orderIntentId?: string | null;
  orderId?: string | null;
  contextHash?: string | null;
  className?: string;
}

const linkLabels: Array<{ key: keyof LinkageLinks; label: string; icon: typeof BarChart3 }> = [
  { key: "research", label: "研究台", icon: BarChart3 },
  { key: "backtest", label: "回测台", icon: Layers },
  { key: "replay", label: "回放台", icon: History },
  { key: "audit", label: "审计台", icon: FileSearch },
  { key: "replay_package_api", label: "重放包", icon: FileJson },
];

function shortHash(value?: string | null) {
  if (!value) return "未绑定";
  return value.length > 18 ? `${value.slice(0, 14)}...` : value;
}

function formatTime(value?: string | null) {
  if (!value) return "latest";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

export function WorkbenchLinkBar({
  source,
  symbol,
  interval,
  asOfTime,
  decisionId,
  auditId,
  backtestId,
  replaySessionId,
  orderIntentId,
  orderId,
  contextHash,
  className = "",
}: WorkbenchLinkBarProps) {
  const [payload, setPayload] = useState<LinkagePayload | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (symbol) params.set("symbol", String(symbol));
    if (interval) params.set("interval", String(interval));
    if (asOfTime) params.set("as_of_time", String(asOfTime));
    if (decisionId) params.set("decision_id", String(decisionId));
    if (auditId) params.set("audit_id", String(auditId));
    if (backtestId) params.set("backtest_id", String(backtestId));
    if (replaySessionId) params.set("replay_session_id", replaySessionId);
    if (orderIntentId) params.set("order_intent_id", orderIntentId);
    if (orderId) params.set("order_id", orderId);
    if (contextHash) params.set("context_hash", contextHash);
    params.set("source", source);
    return params.toString();
  }, [asOfTime, auditId, backtestId, contextHash, decisionId, interval, orderId, orderIntentId, replaySessionId, source, symbol]);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/v1/linkage/context?${query}`)
      .then((res) => res.ok ? res.json() : null)
      .then((json) => {
        if (!cancelled) setPayload(json?.data || null);
      })
      .catch(() => {
        if (!cancelled) setPayload(null);
      });
    return () => { cancelled = true; };
  }, [query]);

  const identity = payload?.identity || {};
  const pit = payload?.pit || {};
  const links = payload?.links || {};
  const activeAsOf = identity.as_of_time || asOfTime || null;

  return (
    <Card className={`border-cyan-500/20 bg-cyan-500/5 ${className}`}>
      <CardContent className="flex flex-col gap-3 p-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="border-cyan-500/30 bg-cyan-500/10 text-cyan-200">
              {identity.symbol || symbol || "BTCUSDT"} · {identity.interval || interval || "1h"}
            </Badge>
            <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-200">
              <ShieldCheck className="mr-1 h-3 w-3" />
              {pit.agent_input_policy || "local_storage_only"}
            </Badge>
            <Badge className="border-slate-600 bg-slate-900/70 text-slate-300">
              fallback {pit.external_fallback_allowed ? "on" : "off"}
            </Badge>
          </div>
          <div className="mt-2 grid gap-1 text-[11px] text-muted-foreground sm:grid-cols-3">
            <span>PIT: {pit.rule || "available_time <= as_of_time"}</span>
            <span>as_of: {formatTime(activeAsOf)}</span>
            <span className="inline-flex min-w-0 items-center gap-1">
              <GitBranch className="h-3 w-3 shrink-0" />
              <span className="truncate">{shortHash(identity.context_hash || contextHash)}</span>
            </span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {linkLabels.map(({ key, label, icon: Icon }) => {
            const href = links[key];
            if (!href) return null;
            return (
              <Button key={key} asChild size="sm" variant="outline" className="h-8 border-cyan-500/25 bg-background/60 px-2 text-xs">
                <Link href={href} target={key.endsWith("_api") ? "_blank" : undefined}>
                  <Icon className="mr-1 h-3.5 w-3.5" />
                  {label}
                </Link>
              </Button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
