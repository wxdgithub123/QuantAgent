"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  RefreshCw, Wifi, WifiOff, Server, Container, Plug, Bot, AlertTriangle,
  CheckCircle, XCircle, ArrowLeft, Activity, BarChart, History, BarChart3, ShoppingCart, Wallet
} from "lucide-react";

interface ApiResponse<T = unknown> {
  connected: boolean;
  source: string;
  data: T | null;
  error: string | null;
  timestamp: string;
}

interface DockerData {
  docker_running: unknown;
  active_containers: unknown;
}

interface StatusData {
  status?: string;
  version?: string;
  [key: string]: unknown;
}

interface BotsData {
  source?: string;
  bots?: unknown;
  containers_fallback?: {
    containers?: { container_name: string; status: string; image: string; source: string }[];
    total?: number;
    note?: string;
  };
  mqtt_data?: unknown;
}

interface OrderData {
  source?: string;
  active_orders?: unknown;
  history_orders?: unknown;
}

interface PositionData {
  source?: string;
  positions?: unknown;
}

export default function HummingbotPage() {
  const [status, setStatus] = useState<ApiResponse<StatusData> | null>(null);
  const [docker, setDocker] = useState<ApiResponse<DockerData> | null>(null);
  const [connectors, setConnectors] = useState<ApiResponse | null>(null);
  const [portfolio, setPortfolio] = useState<ApiResponse | null>(null);
  const [bots, setBots] = useState<ApiResponse | null>(null);
  const [orders, setOrders] = useState<ApiResponse<OrderData> | null>(null);
  const [positions, setPositions] = useState<ApiResponse<PositionData> | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, dockerRes, connectorsRes, portfolioRes, botsRes, ordersRes, positionsRes] = await Promise.allSettled([
        fetch("/api/v1/hummingbot/status"),
        fetch("/api/v1/hummingbot/docker"),
        fetch("/api/v1/hummingbot/connectors"),
        fetch("/api/v1/hummingbot/portfolio"),
        fetch("/api/v1/hummingbot/bots"),
        fetch("/api/v1/hummingbot/orders"),
        fetch("/api/v1/hummingbot/positions"),
      ]);

      const parseResponse = async (result: PromiseSettledResult<Response>): Promise<ApiResponse | null> => {
        if (result.status === "rejected") {
          return {
            connected: false,
            source: "hummingbot-api",
            data: null,
            error: `请求失败: ${result.reason?.message || "网络错误"}`,
            timestamp: new Date().toISOString(),
          };
        }
        if (!result.value.ok) {
          return {
            connected: false,
            source: "hummingbot-api",
            data: null,
            error: `HTTP ${result.value.status}: ${result.value.statusText}`,
            timestamp: new Date().toISOString(),
          };
        }
        try {
          return await result.value.json();
        } catch {
          return {
            connected: false,
            source: "hummingbot-api",
            data: null,
            error: "响应解析失败",
            timestamp: new Date().toISOString(),
          };
        }
      };

      const [s, d, c, p, b, o, pos] = await Promise.all([
        parseResponse(statusRes),
        parseResponse(dockerRes),
        parseResponse(connectorsRes),
        parseResponse(portfolioRes),
        parseResponse(botsRes),
        parseResponse(ordersRes),
        parseResponse(positionsRes),
      ]);

      if (s) setStatus(s);
      if (d) setDocker(d);
      if (c) setConnectors(c);
      if (p) setPortfolio(p);
      if (b) setBots(b);
      if (o) setOrders(o as ApiResponse<OrderData>);
      if (pos) setPositions(pos as ApiResponse<PositionData>);
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // 辅助函数：计算 connectors 数量
  const getConnectorsCount = (data: unknown): number => {
    if (!data) return 0;
    if (Array.isArray(data)) return data.length;
    if (typeof data === "object" && data !== null) {
      const keys = Object.keys(data);
      if (keys.length > 0) {
        const firstValue = (data as Record<string, unknown>)[keys[0]];
        if (Array.isArray(firstValue)) return firstValue.length;
        return keys.length;
      }
    }
    return 0;
  };

  // 辅助函数：获取 connectors 列表
  const getConnectorsList = (data: unknown): string[] => {
    if (!data) return [];
    if (Array.isArray(data)) {
      return data.slice(0, 10).map((item) => String(item));
    }
    if (typeof data === "object" && data !== null) {
      const keys = Object.keys(data);
      if (keys.length > 0) {
        const firstValue = (data as Record<string, unknown>)[keys[0]];
        if (Array.isArray(firstValue)) {
          return firstValue.slice(0, 10).map((item) => String(item));
        }
        return keys.slice(0, 10);
      }
    }
    return [];
  };

  // 辅助函数：获取 bots 数量（兼容新格式）
  const getBotsCount = (data: unknown): number => {
    if (!data) return 0;

    // 兼容新格式：{ source, bots, containers_fallback }
    const d = data as Record<string, unknown>;

    // 如果有 containers_fallback，返回其中的容器数量
    if (d.containers_fallback) {
      const cf = d.containers_fallback as Record<string, unknown>;
      if (cf.total !== undefined) return cf.total as number;
      if (Array.isArray(cf.containers)) return cf.containers.length;
    }

    // 如果有 bots 数据
    if (d.bots) {
      const bots = d.bots;
      if (Array.isArray(bots)) return bots.length;
      if (typeof bots === "object") {
        const keys = Object.keys(bots);
        if (keys.length > 0) {
          const firstValue = (bots as Record<string, unknown>)[keys[0]];
          if (Array.isArray(firstValue)) return firstValue.length;
          return keys.length;
        }
      }
    }

    // 兼容旧格式（直接是数组）
    if (Array.isArray(data)) return data.length;

    // 兼容旧格式（是对象但没有 containers_fallback）
    if (typeof data === "object") {
      const keys = Object.keys(data);
      if (keys.length > 0) {
        const firstValue = (data as Record<string, unknown>)[keys[0]];
        if (Array.isArray(firstValue)) return firstValue.length;
        return keys.length;
      }
    }

    return 0;
  };

  // 辅助函数：获取 active containers 数量
  const getActiveContainersCount = (data: unknown): number => {
    if (!data) return 0;
    if (Array.isArray(data)) return data.length;
    if (typeof data === "object" && data !== null) {
      const keys = Object.keys(data);
      if (keys.length > 0) {
        const firstValue = (data as Record<string, unknown>)[keys[0]];
        if (Array.isArray(firstValue)) return firstValue.length;
        return keys.length;
      }
    }
    return 0;
  };

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-40">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link href="/dashboard" className="text-slate-400 hover:text-slate-100 transition-colors">
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div className="w-9 h-9 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-xl flex items-center justify-center">
                <Server className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-slate-100">Hummingbot 管理中心</h1>
                <p className="text-[10px] text-slate-400">Read-only Integration</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {/* Navigation */}
              <nav className="hidden md:flex items-center gap-1 mr-4">
                <Link href="/dashboard" className="px-2 py-1 text-xs text-slate-400 hover:text-slate-100 rounded hover:bg-slate-800">
                  仪表盘
                </Link>
                <Link href="/trades" className="px-2 py-1 text-xs text-slate-400 hover:text-slate-100 rounded hover:bg-slate-800">
                  交易流水
                </Link>
                <Link href="/analytics" className="px-2 py-1 text-xs text-slate-400 hover:text-slate-100 rounded hover:bg-slate-800">
                  性能分析
                </Link>
                <Link href="/backtest" className="px-2 py-1 text-xs text-slate-400 hover:text-slate-100 rounded hover:bg-slate-800">
                  回测
                </Link>
                <Link href="/replay" className="px-2 py-1 text-xs text-slate-400 hover:text-slate-100 rounded hover:bg-slate-800">
                  历史回放
                </Link>
                <Link href="/terminal" className="px-2 py-1 text-xs text-slate-400 hover:text-slate-100 rounded hover:bg-slate-800">
                  终端
                </Link>
                <Link href="/hummingbot" className="px-2 py-1 text-xs text-cyan-400 bg-cyan-500/10 rounded border border-cyan-500/20 font-medium">
                  <span className="flex items-center gap-1"><Server className="w-3 h-3" /> Hummingbot</span>
                </Link>
              </nav>
              <Badge variant="outline" className="bg-cyan-500/10 text-cyan-400 border-cyan-500/20">
                <Server className="w-3 h-3 mr-1" />
                只读模式
              </Badge>
              <Button
                size="sm"
                onClick={fetchAll}
                disabled={loading}
                className="h-8 bg-cyan-600 hover:bg-cyan-500 text-white text-xs"
              >
                <RefreshCw className={`w-3 h-3 mr-1 ${loading ? "animate-spin" : ""}`} />
                {loading ? "刷新中..." : "刷新"}
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        {/* Warning Banner */}
        <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-sm text-amber-300">
            <p className="font-semibold">当前页面为 Hummingbot API 只读集成测试页，不执行实盘交易操作。</p>
            <p className="text-amber-400/70 mt-1 text-xs">
              本模块仅用于查看连接状态和只读数据，不支持下单、撤单、启动/停止 bot 等操作。
            </p>
          </div>
        </div>

        {/* Last Refresh Time */}
        {lastRefresh && (
          <div className="mb-4 text-xs text-slate-500 flex items-center gap-1">
            <RefreshCw className="w-3 h-3" />
            最后刷新: {lastRefresh.toLocaleTimeString()}
          </div>
        )}

        {/* Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* API 连接状态 */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 flex items-center gap-2 text-base">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${status?.connected ? "bg-green-500/10 border border-green-500/20" : "bg-red-500/10 border border-red-500/20"}`}>
                  {status?.connected ? (
                    <Wifi className="w-4 h-4 text-green-400" />
                  ) : (
                    <WifiOff className="w-4 h-4 text-red-400" />
                  )}
                </div>
                API 连接状态
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading && !status ? (
                <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
                </div>
              ) : (
                <>
                  {/* Connection Status */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">连接状态</span>
                    <Badge
                      variant="outline"
                      className={
                        status?.connected
                          ? "bg-green-500/10 text-green-400 border-green-500/20"
                          : "bg-red-500/10 text-red-400 border-red-500/20"
                      }
                    >
                      {status?.connected ? (
                        <>
                          <CheckCircle className="w-3 h-3 mr-1" /> 已连接
                        </>
                      ) : (
                        <>
                          <XCircle className="w-3 h-3 mr-1" /> 未连接
                        </>
                      )}
                    </Badge>
                  </div>

                  {/* API URL */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">API 地址</span>
                    <span className="text-slate-300 text-xs font-mono">
                      {status?.source === "hummingbot-api" ? "http://localhost:8000" : "—"}
                    </span>
                  </div>

                  {/* Timestamp */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">响应时间</span>
                    <span className="text-slate-300 text-xs">
                      {status?.timestamp
                        ? new Date(status.timestamp).toLocaleTimeString()
                        : "—"}
                    </span>
                  </div>

                  {/* Error Message */}
                  {status?.error && (
                    <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                      <p className="text-red-400 text-xs">
                        <span className="font-semibold">错误:</span> {status.error}
                      </p>
                    </div>
                  )}

                  {/* Data Preview */}
                  {status?.data && (
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs mb-2">数据预览:</p>
                      <pre className="text-slate-300 text-xs overflow-x-auto max-h-32">
                        {JSON.stringify(status.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {/* Docker 状态 */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 flex items-center gap-2 text-base">
                <div className="w-8 h-8 bg-blue-500/10 rounded-lg flex items-center justify-center border border-blue-500/20">
                  <Container className="w-4 h-4 text-blue-400" />
                </div>
                Docker 状态
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading && !docker ? (
                <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
                </div>
              ) : docker?.error ? (
                <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-center">
                  <XCircle className="w-8 h-8 text-red-400 mx-auto mb-2" />
                  <p className="text-red-400 text-sm">{docker.error}</p>
                </div>
              ) : (
                <>
                  {/* Active Containers Count */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">活跃容器数量</span>
                    <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/20">
                      {getActiveContainersCount(docker?.data?.active_containers)} 个
                    </Badge>
                  </div>

                  {/* Docker Reachable */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">Docker 可达性</span>
                    <Badge
                      variant="outline"
                      className={
                        docker?.connected
                          ? "bg-green-500/10 text-green-400 border-green-500/20"
                          : "bg-red-500/10 text-red-400 border-red-500/20"
                      }
                    >
                      {docker?.connected ? "可达" : "不可达"}
                    </Badge>
                  </div>

                  {/* Raw Data */}
                  {docker?.data && (
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs mb-2">原始数据:</p>
                      <pre className="text-slate-300 text-xs overflow-x-auto max-h-40">
                        {JSON.stringify(docker.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {/* Connectors */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 flex items-center gap-2 text-base">
                <div className="w-8 h-8 bg-purple-500/10 rounded-lg flex items-center justify-center border border-purple-500/20">
                  <Plug className="w-4 h-4 text-purple-400" />
                </div>
                Connectors
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading && !connectors ? (
                <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
                </div>
              ) : connectors?.error ? (
                <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-center">
                  <XCircle className="w-8 h-8 text-red-400 mx-auto mb-2" />
                  <p className="text-red-400 text-sm">{connectors.error}</p>
                </div>
              ) : (
                <>
                  {/* Connectors Count */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">支持的 Connectors</span>
                    <Badge variant="outline" className="bg-purple-500/10 text-purple-400 border-purple-500/20">
                      {getConnectorsCount(connectors?.data)} 个
                    </Badge>
                  </div>

                  {/* Connector List */}
                  {getConnectorsList(connectors?.data).length > 0 ? (
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs mb-2">Connector 列表 (前10个):</p>
                      <div className="flex flex-wrap gap-2">
                        {getConnectorsList(connectors?.data).map((connector, idx) => (
                          <Badge
                            key={idx}
                            variant="outline"
                            className="bg-slate-700/50 text-slate-300 border-slate-600/50 text-xs"
                          >
                            {connector}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center text-slate-500 text-sm">
                      暂无 Connector 数据
                    </div>
                  )}

                  {/* Raw Data */}
                  {connectors?.data && (
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs mb-2">原始数据:</p>
                      <pre className="text-slate-300 text-xs overflow-x-auto max-h-40">
                        {JSON.stringify(connectors.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {/* Portfolio / 实盘资产 */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 flex items-center gap-2 text-base">
                <div className="w-8 h-8 bg-green-500/10 rounded-lg flex items-center justify-center border border-green-500/20">
                  <Bot className="w-4 h-4 text-green-400" />
                </div>
                实盘资产 (Portfolio)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading && !portfolio ? (
                <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
                </div>
              ) : portfolio?.error ? (
                <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                  <p className="text-amber-400 text-sm">{portfolio.error}</p>
                </div>
              ) : (
                <>
                  {/* Accounts */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">账户列表</span>
                    <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">
                      {portfolio?.data?.accounts?.length || 0} 个
                    </Badge>
                  </div>

                  {/* Account List */}
                  {portfolio?.data?.accounts && portfolio.data.accounts.length > 0 ? (
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs mb-2">账户:</p>
                      <div className="flex flex-wrap gap-2">
                        {portfolio.data.accounts.map((account: string, idx: number) => (
                          <Badge
                            key={idx}
                            variant="outline"
                            className="bg-green-500/10 text-green-400 border-green-500/20 text-xs"
                          >
                            {account}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center text-slate-500 text-sm">
                      暂无实盘账户资产数据，请在 Hummingbot 中配置交易所账户。
                    </div>
                  )}

                  {/* Portfolio State Summary */}
                  {portfolio?.data?.portfolio_state && Object.keys(portfolio.data.portfolio_state).length > 0 ? (
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs mb-2">Portfolio 状态 (数据来源: {portfolio.data.source || "—"}):</p>
                      <pre className="text-slate-300 text-xs overflow-x-auto max-h-40">
                        {JSON.stringify(portfolio.data.portfolio_state, null, 2)}
                      </pre>
                    </div>
                  ) : null}

                  {/* Raw Data */}
                  {portfolio?.data && (
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs mb-2">原始数据:</p>
                      <pre className="text-slate-300 text-xs overflow-x-auto max-h-40">
                        {JSON.stringify(portfolio.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {/* Bots */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 flex items-center gap-2 text-base">
                <div className="w-8 h-8 bg-cyan-500/10 rounded-lg flex items-center justify-center border border-cyan-500/20">
                  <Bot className="w-4 h-4 text-cyan-400" />
                </div>
                Bots 编排
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading && !bots ? (
                <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
                </div>
              ) : bots?.error ? (
                <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-amber-400 text-sm font-semibold">接口不可用</p>
                      <p className="text-amber-300/70 text-xs mt-1">{bots.error}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  {/* Bots Count */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">Bot 数量</span>
                    <Badge variant="outline" className="bg-cyan-500/10 text-cyan-400 border-cyan-500/20">
                      {getBotsCount(bots?.data)} 个
                    </Badge>
                  </div>

                  {/* Bots Status */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">Bots 状态</span>
                    <Badge
                      variant="outline"
                      className={
                        getBotsCount(bots?.data) > 0
                          ? "bg-green-500/10 text-green-400 border-green-500/20"
                          : "bg-slate-500/10 text-slate-400 border-slate-500/20"
                      }
                    >
                      {getBotsCount(bots?.data) > 0 ? "有运行中的 Bot" : "暂无运行中的 Bot"}
                    </Badge>
                  </div>

                  {/* Fallback Notice */}
                  {bots?.data?.source === "docker-containers" && bots?.data?.containers_fallback?.note && (
                    <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                      <p className="text-amber-400 text-xs">
                        <span className="font-semibold">⚠️ 降级数据源:</span> {bots.data.containers_fallback.note}
                      </p>
                    </div>
                  )}

                  {/* Docker Containers Fallback List */}
                  {bots?.data?.source === "docker-containers" && bots?.data?.containers_fallback?.containers?.length > 0 && (
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs mb-2">Hummingbot 相关容器:</p>
                      <div className="space-y-2">
                        {bots.data.containers_fallback.containers.map((container: { container_name: string; status: string; image: string; source: string }, idx: number) => (
                          <div key={idx} className="flex items-center justify-between p-2 bg-slate-900/50 rounded-lg">
                            <div>
                              <p className="text-slate-300 text-xs font-medium">{container.container_name}</p>
                              <p className="text-slate-500 text-[10px]">{container.image}</p>
                            </div>
                            <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/20 text-[10px]">
                              {container.status}
                            </Badge>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Raw Data */}
                  {bots?.data && bots?.data?.source !== "docker-containers" && (
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs mb-2">原始数据:</p>
                      <pre className="text-slate-300 text-xs overflow-x-auto max-h-40">
                        {JSON.stringify(bots.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {/* 实盘订单 */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 flex items-center gap-2 text-base">
                <div className="w-8 h-8 bg-orange-500/10 rounded-lg flex items-center justify-center border border-orange-500/20">
                  <ShoppingCart className="w-4 h-4 text-orange-400" />
                </div>
                实盘订单
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading && !orders ? (
                <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
                </div>
              ) : orders?.error ? (
                <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                  <p className="text-amber-400 text-sm">{orders.error}</p>
                </div>
              ) : (
                <>
                  {/* Orders Count */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">活跃订单</span>
                    <Badge variant="outline" className="bg-orange-500/10 text-orange-400 border-orange-500/20">
                      {(() => {
                        const activeOrders = orders?.data?.active_orders;
                        if (Array.isArray(activeOrders)) return `${activeOrders.length} 个`;
                        const historyOrders = orders?.data?.history_orders;
                        if (Array.isArray(historyOrders)) return `${historyOrders.length} 条(历史)`;
                        return "0 个";
                      })()}
                    </Badge>
                  </div>

                  {/* Data Source */}
                  {orders?.data?.source && (
                    <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <span className="text-slate-400 text-sm">数据来源</span>
                      <Badge variant="outline" className="bg-slate-700/50 text-slate-300 border-slate-600/50">
                        {orders.data.source === "orders_active" ? "活跃订单" : "历史订单"}
                      </Badge>
                    </div>
                  )}

                  {/* Orders Table */}
                  {(() => {
                    const activeOrders = orders?.data?.active_orders || orders?.data?.history_orders;
                    if (!activeOrders || (Array.isArray(activeOrders) && activeOrders.length === 0)) {
                      return (
                        <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center text-slate-500 text-sm">
                          暂无实盘订单
                        </div>
                      );
                    }
                    if (!Array.isArray(activeOrders)) {
                      return (
                        <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                          <pre className="text-slate-300 text-xs overflow-x-auto max-h-60">
                            {JSON.stringify(activeOrders, null, 2)}
                          </pre>
                        </div>
                      );
                    }
                    return (
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-slate-700">
                              <th className="text-left py-2 px-2 text-slate-400">交易所</th>
                              <th className="text-left py-2 px-2 text-slate-400">交易对</th>
                              <th className="text-left py-2 px-2 text-slate-400">方向</th>
                              <th className="text-left py-2 px-2 text-slate-400">类型</th>
                              <th className="text-right py-2 px-2 text-slate-400">价格</th>
                              <th className="text-right py-2 px-2 text-slate-400">数量</th>
                              <th className="text-left py-2 px-2 text-slate-400">状态</th>
                            </tr>
                          </thead>
                          <tbody>
                            {activeOrders.slice(0, 10).map((order: Record<string, unknown>, idx: number) => (
                              <tr key={idx} className="border-b border-slate-800 hover:bg-slate-800/30">
                                <td className="py-2 px-2 text-slate-300">{String(order.exchange || order.connector || "-")}</td>
                                <td className="py-2 px-2 text-slate-300">{String(order.symbol || order.trading_pair || order.tradingPair || "-")}</td>
                                <td className={`py-2 px-2 ${order.side === "BUY" ? "text-green-400" : "text-red-400"}`}>
                                  {String(order.side || "-")}
                                </td>
                                <td className="py-2 px-2 text-slate-300">{String(order.order_type || order.type || order.orderType || "-")}</td>
                                <td className="py-2 px-2 text-right text-slate-300">{order.price ? String(order.price) : "-"}</td>
                                <td className="py-2 px-2 text-right text-slate-300">{order.amount || order.quantity || order.amount_string ? String(order.amount || order.quantity || order.amount_string) : "-"}</td>
                                <td className="py-2 px-2">
                                  <Badge variant="outline" className={`text-[10px] ${
                                    order.status === "FILLED" ? "bg-green-500/10 text-green-400 border-green-500/20" :
                                    order.status === "CANCELLED" || order.status === "CANCELED" ? "bg-red-500/10 text-red-400 border-red-500/20" :
                                    order.status === "NEW" || order.status === "OPEN" ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                                    "bg-slate-500/10 text-slate-400 border-slate-500/20"
                                  }`}>
                                    {String(order.status || "-")}
                                  </Badge>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {activeOrders.length > 10 && (
                          <p className="text-slate-500 text-xs mt-2 text-center">显示前 10 条，共 {activeOrders.length} 条</p>
                        )}
                      </div>
                    );
                  })()}
                </>
              )}
            </CardContent>
          </Card>

          {/* 实盘持仓 */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 flex items-center gap-2 text-base">
                <div className="w-8 h-8 bg-emerald-500/10 rounded-lg flex items-center justify-center border border-emerald-500/20">
                  <Wallet className="w-4 h-4 text-emerald-400" />
                </div>
                实盘持仓
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading && !positions ? (
                <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
                </div>
              ) : positions?.error ? (
                <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                  <p className="text-amber-400 text-sm">{positions.error}</p>
                </div>
              ) : (
                <>
                  {/* Positions Count */}
                  <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <span className="text-slate-400 text-sm">持仓数量</span>
                    <Badge variant="outline" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                      {(() => {
                        const posData = positions?.data?.positions;
                        if (Array.isArray(posData)) return `${posData.length} 个`;
                        return "0 个";
                      })()}
                    </Badge>
                  </div>

                  {/* Positions Table */}
                  {(() => {
                    const posData = positions?.data?.positions;
                    if (!posData || (Array.isArray(posData) && posData.length === 0)) {
                      return (
                        <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center text-slate-500 text-sm">
                          暂无实盘持仓
                        </div>
                      );
                    }
                    if (!Array.isArray(posData)) {
                      return (
                        <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                          <pre className="text-slate-300 text-xs overflow-x-auto max-h-60">
                            {JSON.stringify(posData, null, 2)}
                          </pre>
                        </div>
                      );
                    }
                    return (
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-slate-700">
                              <th className="text-left py-2 px-2 text-slate-400">交易所</th>
                              <th className="text-left py-2 px-2 text-slate-400">交易对</th>
                              <th className="text-left py-2 px-2 text-slate-400">方向</th>
                              <th className="text-right py-2 px-2 text-slate-400">数量</th>
                              <th className="text-right py-2 px-2 text-slate-400">入场价</th>
                              <th className="text-right py-2 px-2 text-slate-400">标记价</th>
                              <th className="text-right py-2 px-2 text-slate-400">未实现盈亏</th>
                            </tr>
                          </thead>
                          <tbody>
                            {posData.slice(0, 10).map((pos: Record<string, unknown>, idx: number) => {
                              const pnl = pos.unrealized_pnl || pos.unrealizedPnl || pos.pnl;
                              const isProfit = typeof pnl === "number" && pnl >= 0;
                              return (
                                <tr key={idx} className="border-b border-slate-800 hover:bg-slate-800/30">
                                  <td className="py-2 px-2 text-slate-300">{String(pos.exchange || pos.connector || "-")}</td>
                                  <td className="py-2 px-2 text-slate-300">{String(pos.symbol || pos.trading_pair || pos.tradingPair || "-")}</td>
                                  <td className={`py-2 px-2 ${pos.side === "LONG" || pos.side === "BUY" ? "text-green-400" : "text-red-400"}`}>
                                    {String(pos.side || pos.position_side || "-")}
                                  </td>
                                  <td className="py-2 px-2 text-right text-slate-300">{pos.amount || pos.quantity || String(pos.amount || 0)}</td>
                                  <td className="py-2 px-2 text-right text-slate-300">{pos.entry_price || pos.entryPrice ? String(pos.entry_price || pos.entryPrice) : "-"}</td>
                                  <td className="py-2 px-2 text-right text-slate-300">{pos.mark_price || pos.markPrice ? String(pos.mark_price || pos.markPrice) : "-"}</td>
                                  <td className={`py-2 px-2 text-right ${isProfit ? "text-green-400" : "text-red-400"}`}>
                                    {pnl !== undefined ? String(pnl) : "-"}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                        {posData.length > 10 && (
                          <p className="text-slate-500 text-xs mt-2 text-center">显示前 10 条，共 {posData.length} 条</p>
                        )}
                      </div>
                    );
                  })()}
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Additional Info */}
        <div className="mt-6 p-4 bg-slate-900/50 border border-slate-800 rounded-xl">
          <h3 className="text-slate-300 text-sm font-semibold mb-3">集成说明</h3>
          <ul className="text-slate-400 text-xs space-y-2">
            <li className="flex items-start gap-2">
              <span className="text-cyan-400">1.</span>
              <span>本模块通过 QuantAgent 后端代理访问 Hummingbot API，不直接暴露认证信息。</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-cyan-400">2.</span>
              <span>所有接口均为只读，不执行真实下单、撤单、启动/停止 bot 等操作。</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-cyan-400">3.</span>
              <span>如果连接失败，请检查 Hummingbot API 是否启动以及环境变量配置。</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-cyan-400">4.</span>
              <span>如果 Docker 容器中运行，需要将 HUMMINGBOT_API_URL 改为 http://host.docker.internal:8000。</span>
            </li>
          </ul>
        </div>
      </main>
    </div>
  );
}
