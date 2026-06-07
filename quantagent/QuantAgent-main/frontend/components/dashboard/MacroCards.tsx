"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Globe, TrendingUp, Building2, Banknote, BarChart3, Percent } from "lucide-react";

interface MacroIndicator {
  name: string;
  value: number | string | null;
  unit?: string;
  date?: string;
}

const INDICATOR_CONFIG: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; format: (v: number) => string; unit: string }> = {
  fed_funds_rate: { label: "联邦基金利率", icon: Banknote, format: (v) => `${v.toFixed(2)}%`, unit: "%" },
  cpi: { label: "CPI 消费者物价指数", icon: TrendingUp, format: (v) => v.toFixed(1), unit: "" },
  core_cpi: { label: "核心 CPI", icon: TrendingUp, format: (v) => v.toFixed(1), unit: "" },
  unemployment: { label: "失业率", icon: Percent, format: (v) => `${v.toFixed(1)}%`, unit: "%" },
  treasury_10y: { label: "10年期美债收益率", icon: BarChart3, format: (v) => `${v.toFixed(2)}%`, unit: "%" },
  dollar_index: { label: "美元指数 DXY", icon: Globe, format: (v) => v.toFixed(2), unit: "" },
  inflation_expect: { label: "通胀预期", icon: TrendingUp, format: (v) => `${v.toFixed(2)}%`, unit: "%" },
  m2_money_supply: { label: "M2 货币供应", icon: Building2, format: (v) => `${(v / 1000).toFixed(1)}T`, unit: "B" },
  retail_sales: { label: "零售销售", icon: TrendingUp, format: (v) => `${(v / 1000).toFixed(1)}B`, unit: "" },
  industrial_production: { label: "工业生产指数", icon: Building2, format: (v) => v.toFixed(2), unit: "" },
  consumer_sentiment: { label: "消费者信心指数", icon: TrendingUp, format: (v) => v.toFixed(1), unit: "" },
  gdp: { label: "GDP", icon: Globe, format: (v) => `${(v / 1000).toFixed(2)}T`, unit: "B" },
};

export function MacroCards() {
  const [indicators, setIndicators] = useState<MacroIndicator[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const response = await fetch("/api/v1/market/macro");
        const data = await response.json();
        if (cancelled) return;
        const raw = data.indicators || {};
        const list: MacroIndicator[] = Object.entries(raw).map(([key, val]: [string, unknown]) => {
          const v = val as { value?: number; date?: string } | number | null;
          if (typeof v === "object" && v !== null) {
            return { name: key, value: v.value ?? null, date: v.date };
          }
          return { name: key, value: v as number | null };
        });
        setIndicators(list);
      } catch {
        if (!cancelled) setIndicators([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  // Sort: known indicators first, then by name
  const sorted = [...indicators].sort((a, b) => {
    const aConfig = INDICATOR_CONFIG[a.name];
    const bConfig = INDICATOR_CONFIG[b.name];
    if (aConfig && !bConfig) return -1;
    if (!aConfig && bConfig) return 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <Card className="border-border bg-card h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-foreground flex items-center gap-2">
          <Globe className="w-4 h-4 text-amber-400" />
          宏观指标
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="grid grid-cols-2 gap-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : sorted.length === 0 ? (
          <div className="py-6 text-center">
            <Globe className="w-8 h-8 mx-auto mb-2 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">暂无宏观数据</p>
            <p className="text-[10px] text-muted-foreground/60 mt-1">需要 L1 管线从 FRED/OECD 拉取</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 max-h-[460px] overflow-y-auto">
            {sorted.map((ind) => {
              const config = INDICATOR_CONFIG[ind.name];
              const Icon = config?.icon || TrendingUp;
              const displayName = config?.label || ind.name;
              const rawValue = ind.value;
              const valueDisplay = rawValue !== null && rawValue !== undefined
                ? (config ? config.format(Number(rawValue)) : String(rawValue))
                : "—";
              const unit = config?.unit || "";

              return (
                <div
                  key={ind.name}
                  className="rounded-lg border border-border/50 bg-secondary/20 p-2.5"
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <Icon className="w-3 h-3 text-amber-400/70" />
                    <p className="text-[10px] text-muted-foreground truncate">{displayName}</p>
                  </div>
                  <p className="text-sm font-bold text-foreground font-mono">
                    {valueDisplay}
                    {unit && <span className="text-[10px] text-muted-foreground ml-0.5">{unit}</span>}
                  </p>
                  {ind.date && (
                    <p className="text-[9px] text-muted-foreground/60 mt-0.5">
                      {new Date(ind.date).toLocaleDateString("zh-CN")}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
        <div className="mt-2 flex items-center gap-1">
          <Badge variant="outline" className="text-[9px] border-border text-muted-foreground">
            来源: FRED / OECD
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}
