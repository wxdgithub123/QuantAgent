"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import {
  Activity,
  BarChart,
  BarChart3,
  Brain,
  ChevronDown,
  Database,
  History,
  Layers,
  MessageSquareText,
  Server,
  Shield,
  Wallet,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

type ActiveSection =
  | "overview"
  | "data-sources"
  | "paper"
  | "decisions"
  | "analytics"
  | "trades"
  | "backtest"
  | "replay"
  | "audit"
  | "signals"
  | "agents"
  | "diagnostics"
  | "hummingbot"
  | "terminal"
  | "none";

interface AppTopNavProps {
  activeSection?: ActiveSection;
  title?: string;
  subtitle?: string;
  rightSlot?: ReactNode;
}

const PRIMARY_NAV_LINKS = [
  { href: "/dashboard", label: "总览", icon: BarChart3, activeKey: "overview" },
  { href: "/data-sources", label: "数据源", icon: Database, activeKey: "data-sources" },
  { href: "/dashboard?tab=positions", label: "模拟盘", icon: Wallet, activeKey: "paper" },
  { href: "/decisions", label: "决策中心", icon: Brain, activeKey: "decisions" },
] as const;

const MORE_NAV_GROUPS = [
  {
    title: "研究与复盘",
    links: [
      { href: "/analytics", label: "绩效分析", icon: BarChart, activeKey: "analytics", desc: "收益、回撤、归因和风险指标" },
      { href: "/backtest", label: "策略回测", icon: History, activeKey: "backtest", desc: "参数、回测任务" },
      { href: "/replay", label: "历史回放", icon: History, activeKey: "replay", desc: "决策复盘" },
      { href: "/audit", label: "回测审计", icon: Shield, activeKey: "audit", desc: "回测、回放、审计追踪与结果对比" },
      { href: "/signals", label: "因子/信号", icon: Layers, activeKey: "signals", desc: "标准化因子与信号" },
      { href: "/dashboard?tab=agents", label: "智能体面板", icon: Brain, activeKey: "agents", desc: "子 Agent 状态与手动分析" },
    ],
  },
  {
    title: "执行与运维",
    links: [
      { href: "/trades", label: "交易流水", icon: Activity, activeKey: "trades", desc: "模拟订单记录" },
      { href: "/dashboard?tab=diagnostics", label: "系统状态", icon: Database, activeKey: "diagnostics", desc: "数据链路、缓存与服务健康" },
      { href: "/hummingbot", label: "执行服务", icon: Server, activeKey: "hummingbot", desc: "Hummingbot 管理中心" },
      { href: "/hummingbot-testnet", label: "测试网机器人", icon: Server, activeKey: "hummingbot", desc: "Testnet Paper Bot" },
      { href: "/terminal", label: "对话分析", icon: MessageSquareText, activeKey: "terminal", desc: "自然语言分析入口" },
    ],
  },
];

export function AppTopNav({
  activeSection = "none",
  title = "QuantAgent OS",
  subtitle = "AI-Native Quantitative Trading",
  rightSlot,
}: AppTopNavProps) {
  const moreActive = MORE_NAV_GROUPS.some((group) =>
    group.links.some((item) => item.activeKey === activeSection)
  );

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-card/50 backdrop-blur-sm">
      <div className="container mx-auto px-4 py-3">
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-purple-600">
              <BarChart3 className="h-5 w-5 text-white" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-lg font-bold text-foreground">{title}</h1>
              <p className="truncate text-[10px] text-muted-foreground">{subtitle}</p>
            </div>
          </div>

          <nav className="hidden min-w-0 flex-1 items-center justify-center gap-2 overflow-hidden md:flex">
            {PRIMARY_NAV_LINKS.map((item) => {
              const Icon = item.icon;
              const isActive = activeSection === item.activeKey;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm whitespace-nowrap transition-all ${
                    isActive
                      ? "border border-cyan-400/30 bg-cyan-400/10 font-medium text-cyan-200 shadow-sm shadow-cyan-950/20"
                      : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className={`h-8 shrink-0 gap-1.5 rounded-full px-3 text-xs ${
                    moreActive
                      ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-200"
                      : "border-border bg-secondary/40 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <ChevronDown className="h-3.5 w-3.5" />
                  更多功能
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" sideOffset={8} className="w-80 border-border bg-card p-3">
                <div className="grid gap-3">
                  {MORE_NAV_GROUPS.map((group) => (
                    <div key={group.title} className="space-y-1">
                      <p className="px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        {group.title}
                      </p>
                      {group.links.map((item) => {
                        const Icon = item.icon;
                        return (
                          <Link
                            key={item.href}
                            href={item.href}
                            className={`flex items-start gap-2 rounded-lg px-2 py-2 text-sm transition-colors ${
                              item.activeKey === activeSection
                                ? "bg-cyan-400/10 text-cyan-200"
                                : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                            }`}
                          >
                            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                            <span>
                              <span className="block font-medium">{item.label}</span>
                              <span className="block text-[11px] text-muted-foreground/75">{item.desc}</span>
                            </span>
                          </Link>
                        );
                      })}
                    </div>
                  ))}
                </div>
              </PopoverContent>
            </Popover>
          </nav>

          <div className="flex md:hidden">
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className={`h-8 shrink-0 gap-1.5 rounded-full px-3 text-xs ${
                    moreActive
                      ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-200"
                      : "border-border bg-secondary/40 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <ChevronDown className="h-3.5 w-3.5" />
                  导航
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" sideOffset={8} className="w-80 border-border bg-card p-3">
                <div className="grid gap-3">
                  <div className="space-y-1">
                    <p className="px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      主入口
                    </p>
                    {PRIMARY_NAV_LINKS.map((item) => {
                      const Icon = item.icon;
                      const isActive = activeSection === item.activeKey;
                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          className={`flex items-center gap-2 rounded-lg px-2 py-2 text-sm transition-colors ${
                            isActive
                              ? "bg-cyan-400/10 font-medium text-cyan-200"
                              : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                          }`}
                        >
                          <Icon className="h-4 w-4 shrink-0" />
                          {item.label}
                        </Link>
                      );
                    })}
                  </div>
                  {MORE_NAV_GROUPS.map((group) => (
                    <div key={group.title} className="space-y-1">
                      <p className="px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        {group.title}
                      </p>
                      {group.links.map((item) => {
                        const Icon = item.icon;
                        return (
                          <Link
                            key={item.href}
                            href={item.href}
                            className={`flex items-start gap-2 rounded-lg px-2 py-2 text-sm transition-colors ${
                              item.activeKey === activeSection
                                ? "bg-cyan-400/10 text-cyan-200"
                                : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                            }`}
                          >
                            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                            <span>
                              <span className="block font-medium">{item.label}</span>
                              <span className="block text-[11px] text-muted-foreground/75">{item.desc}</span>
                            </span>
                          </Link>
                        );
                      })}
                    </div>
                  ))}
                </div>
              </PopoverContent>
            </Popover>
          </div>

          {rightSlot ? <div className="flex shrink-0 items-center gap-3">{rightSlot}</div> : null}
        </div>
      </div>
    </header>
  );
}
