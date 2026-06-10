"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  Activity,
  BarChart3,
  Brain,
  ChevronDown,
  Database,
  History,
  Home,
  Layers,
  MessageSquareText,
  Server,
  Shield,
  Wallet,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import Breadcrumb from "@/components/navigation/Breadcrumb";

type ActiveSection =
  | "overview"
  | "data-sources"
  | "data-governance"
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
  | "hummingbot-testnet"
  | "terminal"
  | "strategies"
  | "strategies-monitor"
  | "profiles"
  | "monitor"
  | "risk"
  | "config-center"
  | "home"
  | "none"

interface AppTopNavProps {
  activeSection?: ActiveSection;
  title?: string;
  subtitle?: string;
  rightSlot?: ReactNode;
}

const PRIMARY_NAV_LINKS = [
  { href: "/", label: "首页", icon: Home, activeKey: "home" as const },
  { href: "/dashboard", label: "总览", icon: BarChart3, activeKey: "overview" as const },
  { href: "/data-sources", label: "数据源", icon: Database, activeKey: "data-sources" as const },
  { href: "/decisions", label: "决策中心", icon: Brain, activeKey: "decisions" as const },
];

const MORE_NAV_GROUPS = [
  {
    title: "量化研究",
    links: [
      { href: "/signals", label: "因子/信号", icon: Layers, activeKey: "signals" as const, desc: "技术因子与策略信号" },
      { href: "/backtest", label: "策略回测", icon: History, activeKey: "backtest" as const, desc: "历史回测与参数优化" },
      { href: "/strategies", label: "策略库", icon: Activity, activeKey: "strategies" as const, desc: "策略模板与监控" },
      { href: "/replay", label: "历史回放", icon: History, activeKey: "replay" as const, desc: "时间轴回放与复盘" },
      { href: "/analytics", label: "绩效分析", icon: BarChart3, activeKey: "analytics" as const, desc: "收益、回撤与风险指标" },
    ],
  },
  {
    title: "交易执行",
    links: [
      { href: "/paper-trading", label: "模拟交易", icon: Wallet, activeKey: "paper" as const, desc: "OrderIntent、风控与模拟成交" },
      { href: "/trades", label: "交易流水", icon: Activity, activeKey: "trades" as const, desc: "成交记录查询" },
      { href: "/hummingbot", label: "执行服务", icon: Server, activeKey: "hummingbot" as const, desc: "Hummingbot 机器人管理" },
      { href: "/hummingbot-testnet", label: "测试网", icon: Server, activeKey: "hummingbot-testnet" as const, desc: "Testnet 纸交易" },
    ],
  },
  {
    title: "审计与工具",
    links: [
      { href: "/audit", label: "审计台", icon: Shield, activeKey: "audit" as const, desc: "决策追踪与合规审计" },
      { href: "/config-center", label: "配置中心", icon: Server, activeKey: "config-center" as const, desc: "Agent、数据源与系统配置" },
      { href: "/data-governance", label: "数据治理", icon: Database, activeKey: "data-governance" as const, desc: "数据预览、清洗与血缘" },
      { href: "/risk", label: "风控配置", icon: Shield, activeKey: "risk" as const, desc: "RiskGuard 阈值与熔断" },
      { href: "/profiles", label: "策略方案", icon: Layers, activeKey: "profiles" as const, desc: "策略配置方案管理" },
      { href: "/terminal", label: "对话分析", icon: MessageSquareText, activeKey: "terminal" as const, desc: "自然语言交互分析" },
      { href: "/dashboard?tab=diagnostics", label: "系统状态", icon: Database, activeKey: "diagnostics" as const, desc: "数据链路与服务健康" },
    ],
  },
];

export function AppTopNav({
  activeSection = "none",
  title = "QuantAgent OS",
  subtitle = "AI驱动量化交易平台",
  rightSlot,
}: AppTopNavProps) {
  const pathname = usePathname();
  const moreActive = MORE_NAV_GROUPS.some((group) =>
    group.links.some((item) => item.activeKey === activeSection)
  );

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-border bg-card/50 backdrop-blur-sm">
      <div className="container mx-auto px-4 py-3">
        <div className="flex items-center justify-between gap-4">
          {/* Logo & Title */}
          <Link href="/" className="flex min-w-0 items-center gap-3 hover:opacity-80 transition-opacity">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-purple-600">
              <BarChart3 className="h-5 w-5 text-white" />
            </div>
            <div className="min-w-0 hidden sm:block">
              <h1 className="truncate text-lg font-bold text-foreground">{title}</h1>
              <p className="truncate text-[10px] text-muted-foreground">{subtitle}</p>
            </div>
          </Link>

          {/* Desktop Nav */}
          <nav className="hidden min-w-0 flex-1 items-center justify-center gap-1 overflow-hidden md:flex">
            {PRIMARY_NAV_LINKS.map((item) => {
              const Icon = item.icon;
              const isActive = activeSection === item.activeKey || (item.href === "/" && pathname === "/");
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
                  更多
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

          {/* Mobile Nav */}
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
                      const isActive = activeSection === item.activeKey || (item.href === "/" && pathname === "/");
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
    <Breadcrumb />
    </>
  );
}
