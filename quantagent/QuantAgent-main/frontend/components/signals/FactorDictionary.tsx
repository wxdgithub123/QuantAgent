"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Search, BookOpen, TrendingUp, Newspaper, Globe, Plus } from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────────────────

interface FactorCatalogItem {
  factorId?: string;
  factorName: string;
  displayName: string;
  category: string;
  formula?: string;
  dataSource?: string;
  updateFrequency?: string;
  availabilityStatus?: string;
  supportsPIT?: boolean;
  usedByStrategies?: string[];
  signalCount?: number;
  usedBySignals?: string[];
  snapshotCount?: number;
  symbolCount?: number;
  description?: string;
  calculation?: string;
  upstream_data?: string;
  provider_hint?: string;
  unit?: string;
}

interface FactorDefinitionRow {
  factor_name?: string;
  display_name: string;
  category: string;
  family?: string | null;
  description?: string;
  calculation?: string;
  upstream_data?: string;
  provider_hint?: string;
  snapshot_count?: number;
  symbol_count?: number;
}

const CATEGORY_FILTER_OPTIONS = [
  { value: "all", label: "全部分类" },
  { value: "技术指标因子", label: "技术因子" },
  { value: "行情基础因子", label: "行情基础" },
  { value: "波动率因子", label: "波动率" },
  { value: "收益率因子", label: "收益率" },
  { value: "成交量因子", label: "成交量" },
  { value: "新闻事件因子", label: "情绪/新闻" },
  { value: "宏观因子", label: "宏观因子" },
  { value: "加密特有因子", label: "加密特有" },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function availabilityLabel(s?: string) {
  if (s === "available") return "可用";
  if (s === "partial") return "部分";
  return "暂无";
}
function availabilityClass(s?: string) {
  if (s === "available") return "bg-emerald-500/15 text-emerald-400 border-emerald-500/25";
  if (s === "partial") return "bg-amber-500/15 text-amber-400 border-amber-500/25";
  return "bg-muted text-muted-foreground border-border";
}

// ─── Component ───────────────────────────────────────────────────────────────

export function FactorDictionary() {
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState<FactorCatalogItem[]>([]);
  const [definitions, setDefinitions] = useState<FactorDefinitionRow[]>([]);
  const [categoryFilter, setCategoryFilter] = useState("all");

  // ── 新增因子 Dialog ──
  const [showNewFactor, setShowNewFactor] = useState(false);
  const [newFactor, setNewFactor] = useState({ code: "", name: "", category: "技术指标因子", formula: "", params: "", description: "" });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAddFactor = async () => {
    if (!newFactor.code || !newFactor.name) { toast.error("因子代码和名称为必填"); return; }
    setIsSubmitting(true);
    try {
      // TODO: 后端接口就绪后调用 POST /api/v1/signals/factor-definitions
      const res = await fetch("/api/v1/signals/factor-definitions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          factor_name: newFactor.code.toLowerCase(),
          display_name: newFactor.name,
          category: newFactor.category,
          calculation: newFactor.formula,
          description: newFactor.description,
        }),
      });
      if (res.ok) {
        toast.success(`因子 ${newFactor.code} 已创建`);
        setShowNewFactor(false);
        // 关闭 dialog 后重新加载列表
      } else {
        throw new Error("API 返回错误");
      }
    } catch {
      // 后端未就绪：存入 localStorage 作为临时方案
      try {
        const existing = JSON.parse(localStorage.getItem("quantagent_custom_factors") || "[]");
        existing.push({ ...newFactor, code: newFactor.code.toLowerCase(), createdAt: new Date().toISOString() });
        localStorage.setItem("quantagent_custom_factors", JSON.stringify(existing));
        toast.success(`因子 ${newFactor.code} 已保存到本地（后端未就绪，TODO 接入）`);
        setShowNewFactor(false);
        setNewFactor({ code: "", name: "", category: "技术指标因子", formula: "", params: "", description: "" });
      } catch (lsErr) {
        toast.error(`保存失败: ${lsErr instanceof Error ? lsErr.message : "未知错误"}`);
      }
    } finally { setIsSubmitting(false); }
  };
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [catRes, defRes] = await Promise.all([
          fetch("/api/v1/signals/factor-catalog"),
          fetch("/api/v1/signals/factor-definitions"),
        ]);
        const catData = await catRes.json();
        const defData = await defRes.json();
        if (!cancelled) {
          setCatalog((catData.data || []).filter(Boolean));
          setDefinitions((defData.data || []).filter(Boolean));
        }
      } catch {
        /* silently fall back to empty */
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  // Derive stats
  const allCategories = definitions.map((d) => d.category).filter(Boolean);
  const techCount = allCategories.filter((c) => c === "技术指标因子").length;
  const sentimentCount = allCategories.filter((c) => c === "新闻事件因子").length;
  const macroCount = allCategories.filter((c) => c === "宏观因子").length;
  const totalDefs = definitions.length || catalog.length;

  // Merge catalog with definitions to enrich display
  const defMap = new Map<string, FactorDefinitionRow>();
  definitions.forEach((d) => {
    const key = (d.factor_name || "").toLowerCase();
    if (key) defMap.set(key, d);
  });

  const mergedItems: FactorCatalogItem[] = (catalog.length > 0 ? catalog : definitions.map<FactorCatalogItem>((d) => ({
    factorName: d.factor_name || "",
    displayName: d.display_name,
    category: d.category,
    formula: d.calculation || "",
    dataSource: d.upstream_data || "",
    updateFrequency: "",
    availabilityStatus: "available" as const,
    usedByStrategies: [],
    usedBySignals: [],
    supportsPIT: true,
    signalCount: d.snapshot_count || 0,
    description: d.description || "",
    snapshotCount: d.snapshot_count || 0,
  }))).filter((item) => {
    if (categoryFilter !== "all" && item.category !== categoryFilter) return false;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      const name = (item.factorName || "").toLowerCase();
      const display = (item.displayName || "").toLowerCase();
      if (!name.includes(q) && !display.includes(q)) return false;
    }
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-card border-border">
          <CardContent className="p-3">
            <div className="flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-blue-400" />
              <p className="text-xs text-muted-foreground">因子总数</p>
            </div>
            <p className="text-2xl font-bold text-foreground mt-1">
              {loading ? "..." : totalDefs}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">系统已注册的因子类型</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              <p className="text-xs text-muted-foreground">技术因子</p>
            </div>
            <p className="text-2xl font-bold text-emerald-400 mt-1">
              {loading ? "..." : techCount}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">技术指标 / 行情基础</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-3">
            <div className="flex items-center gap-2">
              <Newspaper className="w-4 h-4 text-purple-400" />
              <p className="text-xs text-muted-foreground">情绪因子</p>
            </div>
            <p className="text-2xl font-bold text-purple-400 mt-1">
              {loading ? "..." : sentimentCount}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">新闻 / 事件标签</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-3">
            <div className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-amber-400" />
              <p className="text-xs text-muted-foreground">宏观因子</p>
            </div>
            <p className="text-2xl font-bold text-amber-400 mt-1">
              {loading ? "..." : macroCount}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">CPI / 利率 / 货币</p>
          </CardContent>
        </Card>
      </div>

      {/* Search + Filter */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            placeholder="搜索因子名称或代码..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full h-9 pl-8 pr-3 rounded-lg border border-border bg-secondary text-foreground text-xs placeholder:text-muted-foreground focus:outline-none focus:border-blue-500/50"
          />
        </div>
        {/* 新增因子按钮 */}
        <Button
          size="sm"
          onClick={() => setShowNewFactor(true)}
          className="h-9 bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 hover:bg-emerald-500/20 text-xs"
        >
          <Plus className="w-3.5 h-3.5 mr-1" /> 新增因子
        </Button>
        <div className="flex flex-wrap gap-1.5">
          {CATEGORY_FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setCategoryFilter(opt.value)}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs border transition-colors",
                categoryFilter === opt.value
                  ? "bg-blue-500/15 text-blue-400 border-blue-500/30"
                  : "bg-secondary text-muted-foreground border-border hover:text-foreground"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Factor Grid */}
      {loading ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className="bg-card border-border">
              <CardContent className="p-4 space-y-3">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-2/3" />
                <Skeleton className="h-3 w-1/2" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : mergedItems.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="py-12 text-center">
            <BookOpen className="w-10 h-10 mx-auto mb-3 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">暂无因子字典数据</p>
            <p className="text-xs text-muted-foreground/60 mt-1">可能是数据库尚未初始化，请先运行一次信号管线</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {mergedItems.map((item, idx) => {
            const def = defMap.get((item.factorName || "").toLowerCase());
            const displayName = item.displayName || def?.display_name || item.factorName;
            const formula = item.formula || def?.calculation || "";
            const source = item.dataSource || def?.upstream_data || "";
            const strategies: string[] = item.usedByStrategies || item.usedBySignals || [];
            const sigCount = item.signalCount || item.snapshotCount || 0;

            return (
              <Card key={item.factorName || idx} className="bg-card border-border/70 hover:border-blue-500/20 transition-colors">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <h4 className="text-sm font-semibold text-foreground truncate">{displayName}</h4>
                        <Badge className="bg-blue-500/10 text-blue-300 border-blue-500/20 text-[10px]">
                          {item.category}
                        </Badge>
                      </div>
                      <p className="mt-0.5 font-mono text-[11px] text-blue-300/70 truncate">{item.factorName}</p>
                    </div>
                    <Badge className={cn("text-[10px] shrink-0", availabilityClass(item.availabilityStatus))}>
                      {availabilityLabel(item.availabilityStatus)}
                    </Badge>
                  </div>

                  <div className="mt-3 space-y-1.5 text-[11px] text-muted-foreground">
                    {formula && <p><span className="text-foreground/70">公式：</span>{formula}</p>}
                    {source && <p><span className="text-foreground/70">来源：</span>{source}</p>}
                    {item.description && <p className="leading-5">{item.description}</p>}
                  </div>

                  <div className="mt-3 flex items-center gap-3">
                    <div className="rounded-md bg-secondary/50 px-2 py-1 text-center">
                      <p className="text-[10px] text-muted-foreground">信号数</p>
                      <p className="font-mono text-xs text-foreground">{sigCount}</p>
                    </div>
                    <div className="rounded-md bg-secondary/50 px-2 py-1 text-center">
                      <p className="text-[10px] text-muted-foreground">引用策略</p>
                      <p className="font-mono text-xs text-foreground">{strategies.length || 0}</p>
                    </div>
                    {item.supportsPIT && (
                      <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[10px]">PIT</Badge>
                    )}
                  </div>

                  {strategies.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {strategies.slice(0, 5).map((s) => (
                        <Badge key={s} variant="outline" className="text-[10px] px-1.5 py-0 border-border text-muted-foreground">
                          {s}
                        </Badge>
                      ))}
                      {strategies.length > 5 && (
                        <span className="text-[10px] text-muted-foreground">+{strategies.length - 5} more</span>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <p className="text-[10px] text-muted-foreground/50">
        共 {mergedItems.length} 个因子类型
        {categoryFilter !== "all" && `（已筛选：${CATEGORY_FILTER_OPTIONS.find((o) => o.value === categoryFilter)?.label}）`}
      </p>

      {/* ── 新增因子 Dialog ── */}
      <Dialog open={showNewFactor} onOpenChange={setShowNewFactor}>
        <DialogContent className="bg-card border-border sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-foreground">新增因子</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              创建新的因子定义。后端接口就绪后会提交到数据库，当前保存到本地。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-muted-foreground">因子代码 *</Label>
                <Input
                  value={newFactor.code}
                  onChange={(e) => setNewFactor({ ...newFactor, code: e.target.value })}
                  placeholder="如 sma_99"
                  className="h-9 bg-secondary border-border text-xs mt-1"
                />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">因子名称 *</Label>
                <Input
                  value={newFactor.name}
                  onChange={(e) => setNewFactor({ ...newFactor, name: e.target.value })}
                  placeholder="如 99日均线"
                  className="h-9 bg-secondary border-border text-xs mt-1"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">分类</Label>
              <Select value={newFactor.category} onValueChange={(v) => setNewFactor({ ...newFactor, category: v })}>
                <SelectTrigger className="h-9 bg-secondary border-border text-xs mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  <SelectItem value="技术指标因子" className="text-xs">技术指标因子</SelectItem>
                  <SelectItem value="行情基础因子" className="text-xs">行情基础因子</SelectItem>
                  <SelectItem value="波动率因子" className="text-xs">波动率因子</SelectItem>
                  <SelectItem value="情绪新闻因子" className="text-xs">情绪/新闻因子</SelectItem>
                  <SelectItem value="宏观因子" className="text-xs">宏观因子</SelectItem>
                  <SelectItem value="加密特有因子" className="text-xs">加密特有因子</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">公式</Label>
              <Input
                value={newFactor.formula}
                onChange={(e) => setNewFactor({ ...newFactor, formula: e.target.value })}
                placeholder="如 SMA(close, 99)"
                className="h-9 bg-secondary border-border text-xs mt-1"
              />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">参数（可选）</Label>
              <Input
                value={newFactor.params}
                onChange={(e) => setNewFactor({ ...newFactor, params: e.target.value })}
                placeholder='如 {"period": 99}'
                className="h-9 bg-secondary border-border text-xs mt-1"
              />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">描述</Label>
              <Input
                value={newFactor.description}
                onChange={(e) => setNewFactor({ ...newFactor, description: e.target.value })}
                placeholder="因子用途说明"
                className="h-9 bg-secondary border-border text-xs mt-1"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="outline" size="sm" className="text-xs border-border" onClick={() => setShowNewFactor(false)}>
              取消
            </Button>
            <Button size="sm" className="text-xs bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/20" onClick={handleAddFactor} disabled={isSubmitting}>
              {isSubmitting ? "保存中..." : "保存因子"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
