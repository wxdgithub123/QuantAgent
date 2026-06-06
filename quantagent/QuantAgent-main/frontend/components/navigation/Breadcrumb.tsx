"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";
import { Fragment } from "react";

// Breadcrumb label map — friendly Chinese names for every route
const BREADCRUMB_LABELS: Record<string, string> = {
  "dashboard": "总览",
  "data-sources": "数据源",
  "signals": "因子/信号",
  "decisions": "决策中心",
  "backtest": "策略回测",
  "replay": "历史回放",
  "audit": "审计台",
  "analytics": "绩效分析",
  "trades": "交易流水",
  "hummingbot": "执行服务",
  "hummingbot-testnet": "测试网",
  "terminal": "对话分析",
  "profiles": "策略方案",
  "strategies": "策略库",
  "monitor": "策略监控",
  "monitor-page": "系统监控",
};

// Routes that should be hidden from breadcrumb (intermediate segments)
const HIDDEN_SEGMENTS = new Set(["app", "api"]);

export default function Breadcrumb() {
  const pathname = usePathname();

  // Skip breadcrumb on home page
  if (pathname === "/") return null;

  const segments = pathname.split("/").filter(Boolean);

  // Build breadcrumb items
  const items: { label: string; href: string }[] = [
    { label: "首页", href: "/" },
  ];

  let currentPath = "";
  for (const seg of segments) {
    if (HIDDEN_SEGMENTS.has(seg)) continue;
    currentPath += `/${seg}`;
    const label = BREADCRUMB_LABELS[seg] || seg;
    items.push({ label, href: currentPath });
  }

  if (items.length <= 1) return null;

  return (
    <nav aria-label="面包屑导航" className="px-4 py-2">
      <ol className="flex items-center gap-1 text-xs text-muted-foreground flex-wrap">
        {items.map((item, i) => {
          const isLast = i === items.length - 1;
          return (
            <Fragment key={item.href}>
              {i > 0 && <ChevronRight className="h-3 w-3 shrink-0" />}
              <li>
                {isLast ? (
                  <span className="text-foreground font-medium">{item.label}</span>
                ) : (
                  <Link
                    href={item.href}
                    className="hover:text-foreground transition-colors"
                  >
                    {item.label}
                  </Link>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
