"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  RefreshCw, Wifi, WifiOff, Server, Container, Plug, Bot, AlertTriangle,
  CheckCircle, XCircle, ArrowLeft, Activity, BarChart, History, BarChart3, ShoppingCart, Wallet,
  ShieldCheck, FileJson, Copy, Check, Play, AlertCircle
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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

interface PaperBotPreviewResponse {
  valid: boolean;
  source: string;
  mode: string;
  live_trading: boolean;
  testnet: boolean;
  data: {
    config_preview: {
      bot_name: string;
      mode: string;
      live_trading: boolean;
      testnet: boolean;
      uses_real_exchange_account: boolean;
      requires_api_key: boolean;
      strategy_type: string;
      trading_pair: string;
      paper_initial_balance: number;
      order_amount: number;
      risk: {
        stop_loss_pct: number;
        take_profit_pct: number;
        max_runtime_minutes: number;
      };
      strategy_params: Record<string, unknown>;
      notes: string[];
    };
    warnings: string[];
  } | null;
  error: string | null;
  timestamp: string;
}

interface PaperBotStartResponse {
  submitted: boolean;
  remote_confirmed: boolean;
  source: string;
  mode: string;
  live_trading: boolean;
  testnet: boolean;
  data: {
    paper_bot_id: string;
    bot_name: string;
    strategy_type: string;
    trading_pair: string;
    local_status: string;
    remote_confirmed: boolean;
    hummingbot_bot_id?: string;
    started_at: string;
    hummingbot_response?: Record<string, unknown>;
    config?: Record<string, unknown>;
  } | null;
  error: string | null;
  timestamp: string;
}

interface PaperBotFormData {
  bot_name: string;
  strategy_type: string;
  trading_pair: string;
  paper_initial_balance: number;
  order_amount: number;
  max_runtime_minutes: number;
  spread_pct: number;
  grid_spacing_pct: number;
  grid_levels: number;
  stop_loss_pct: number;
  take_profit_pct: number;
}

interface PaperBot {
  paper_bot_id: string;
  bot_name: string;
  strategy_type: string;
  trading_pair: string;
  mode: string;
  live_trading: boolean;
  testnet: boolean;
  local_status: string;
  remote_status: string;
  matched_remote_bot: boolean;
  matched_by: string;
  hummingbot_bot_id?: string;
  started_at: string;
  runtime_seconds: number;
  last_error?: string;
  config?: Record<string, unknown>;
  hummingbot_status_raw?: Record<string, unknown>;
}

interface PaperBotOrdersResponse {
  connected: boolean;
  source: string;
  data: {
    paper_bot_id: string;
    orders: Record<string, unknown>[];
    filter_note?: string;
  } | null;
  error: string | null;
}

interface PaperBotPositionsResponse {
  connected: boolean;
  source: string;
  data: {
    paper_bot_id: string;
    positions: Record<string, unknown>[];
    filter_note?: string;
  } | null;
  error: string | null;
}

interface PaperBotPortfolioResponse {
  connected: boolean;
  source: string;
  data: {
    paper_bot_id: string;
    portfolio: Record<string, unknown> | null;
    filter_note?: string;
  } | null;
  error: string | null;
}

interface PaperBotLogsResponse {
  connected: boolean;
  source: string;
  data: {
    paper_bot_id: string;
    logs_available: boolean;
    lines: string[];
    message?: string;
  } | null;
  error: string | null;
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

  // Paper Bot 监控
  const [paperBots, setPaperBots] = useState<{ bots: PaperBot[] } | null>(null);
  const [paperBotsLoading, setPaperBotsLoading] = useState(false);
  const [selectedPaperBot, setSelectedPaperBot] = useState<PaperBot | null>(null);
  const [paperBotDetail, setPaperBotDetail] = useState<Record<string, unknown> | null>(null);
  const [paperBotOrders, setPaperBotOrders] = useState<PaperBotOrdersResponse | null>(null);
  const [paperBotPositions, setPaperBotPositions] = useState<PaperBotPositionsResponse | null>(null);
  const [paperBotPortfolio, setPaperBotPortfolio] = useState<PaperBotPortfolioResponse | null>(null);
  const [paperBotLogs, setPaperBotLogs] = useState<PaperBotLogsResponse | null>(null);

  // 停止 Paper Bot
  const [showStopDialog, setShowStopDialog] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopResult, setStopResult] = useState<Record<string, unknown> | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    try {
      const [statusRes, dockerRes, connectorsRes, portfolioRes, botsRes, ordersRes, positionsRes] = await Promise.allSettled([
        fetch("/api/v1/hummingbot/status", { signal: controller.signal }),
        fetch("/api/v1/hummingbot/docker", { signal: controller.signal }),
        fetch("/api/v1/hummingbot/connectors", { signal: controller.signal }),
        fetch("/api/v1/hummingbot/portfolio", { signal: controller.signal }),
        fetch("/api/v1/hummingbot/bots", { signal: controller.signal }),
        fetch("/api/v1/hummingbot/orders", { signal: controller.signal }),
        fetch("/api/v1/hummingbot/positions", { signal: controller.signal }),
      ]);
      clearTimeout(timeoutId);

      const parseResponse = async (result: PromiseSettledResult<Response>): Promise<ApiResponse> => {
        if (result.status === "rejected" || result.status === "rejected") {
          const reason = result.reason;
          const isAbort = reason?.name === "AbortError" || reason?.message?.includes("aborted");
          return {
            connected: false,
            source: "hummingbot-api",
            data: null,
            error: isAbort ? "请求超时（15秒）" : `请求失败: ${reason?.message || "网络错误"}`,
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
          const json = await result.value.json();
          return json || {
            connected: false,
            source: "hummingbot-api",
            data: null,
            error: "响应为空",
            timestamp: new Date().toISOString(),
          };
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

      setStatus(s);
      setDocker(d);
      setConnectors(c);
      setPortfolio(p);
      setBots(b);
      setOrders(o as ApiResponse<OrderData>);
      setPositions(pos as ApiResponse<PositionData>);
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // ── Paper Bot 监控函数 ──────────────────────────────────────────────────

  const fetchPaperBots = useCallback(async () => {
    setPaperBotsLoading(true);
    try {
      const response = await fetch("/api/v1/hummingbot/paper-bots");
      if (response.ok) {
        const data = await response.json();
        setPaperBots(data.data);
      }
    } catch (err) {
      console.error("Failed to fetch paper bots:", err);
    } finally {
      setPaperBotsLoading(false);
    }
  }, []);

  const fetchPaperBotDetail = useCallback(async (paperBotId: string) => {
    try {
      const response = await fetch(`/api/v1/hummingbot/paper-bots/${paperBotId}`);
      if (response.ok) {
        const data = await response.json();
        setPaperBotDetail(data.data);
      }
    } catch (err) {
      console.error("Failed to fetch paper bot detail:", err);
    }
  }, []);

  const fetchPaperBotOrders = useCallback(async (paperBotId: string) => {
    try {
      const response = await fetch(`/api/v1/hummingbot/paper-bots/${paperBotId}/orders`);
      if (response.ok) {
        const data = await response.json();
        setPaperBotOrders(data);
      }
    } catch (err) {
      console.error("Failed to fetch paper bot orders:", err);
    }
  }, []);

  const fetchPaperBotPositions = useCallback(async (paperBotId: string) => {
    try {
      const response = await fetch(`/api/v1/hummingbot/paper-bots/${paperBotId}/positions`);
      if (response.ok) {
        const data = await response.json();
        setPaperBotPositions(data);
      }
    } catch (err) {
      console.error("Failed to fetch paper bot positions:", err);
    }
  }, []);

  const fetchPaperBotPortfolio = useCallback(async (paperBotId: string) => {
    try {
      const response = await fetch(`/api/v1/hummingbot/paper-bots/${paperBotId}/portfolio`);
      if (response.ok) {
        const data = await response.json();
        setPaperBotPortfolio(data);
      }
    } catch (err) {
      console.error("Failed to fetch paper bot portfolio:", err);
    }
  }, []);

  const fetchPaperBotLogs = useCallback(async (paperBotId: string) => {
    try {
      const response = await fetch(`/api/v1/hummingbot/paper-bots/${paperBotId}/logs`);
      if (response.ok) {
        const data = await response.json();
        setPaperBotLogs(data);
      }
    } catch (err) {
      console.error("Failed to fetch paper bot logs:", err);
    }
  }, []);

  const handleStopBot = useCallback(async () => {
    if (!selectedPaperBot) return;

    setStopping(true);
    setStopResult(null);

    try {
      const response = await fetch(`/api/v1/hummingbot/paper-bots/${selectedPaperBot.paper_bot_id}/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });

      const result = await response.json();
      setStopResult(result);

      if (result.stopped) {
        await fetchPaperBots();
        if (selectedPaperBot) {
          await fetchPaperBotDetail(selectedPaperBot.paper_bot_id);
          await fetchPaperBotOrders(selectedPaperBot.paper_bot_id);
          await fetchPaperBotPositions(selectedPaperBot.paper_bot_id);
          await fetchPaperBotPortfolio(selectedPaperBot.paper_bot_id);
          await fetchPaperBotLogs(selectedPaperBot.paper_bot_id);
        }
      }
    } catch (err) {
      setStopResult({
        stopped: false,
        source: "quantagent",
        mode: "paper",
        live_trading: false,
        testnet: false,
        data: null,
        error: `请求失败: ${err instanceof Error ? err.message : "网络错误"}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setStopping(false);
      setShowStopDialog(false);
    }
  }, [selectedPaperBot, fetchPaperBots, fetchPaperBotDetail, fetchPaperBotOrders, fetchPaperBotPositions, fetchPaperBotPortfolio, fetchPaperBotLogs]);

  // 初始加载 Paper Bots
  useEffect(() => {
    fetchPaperBots();
  }, [fetchPaperBots]);

  // 当选中 Paper Bot 时，获取详情并设置轮询
  useEffect(() => {
    if (!selectedPaperBot) {
      setPaperBotDetail(null);
      setPaperBotOrders(null);
      setPaperBotPositions(null);
      setPaperBotPortfolio(null);
      setPaperBotLogs(null);
      return;
    }

    // 获取详情
    fetchPaperBotDetail(selectedPaperBot.paper_bot_id);
    fetchPaperBotOrders(selectedPaperBot.paper_bot_id);
    fetchPaperBotPositions(selectedPaperBot.paper_bot_id);
    fetchPaperBotPortfolio(selectedPaperBot.paper_bot_id);
    fetchPaperBotLogs(selectedPaperBot.paper_bot_id);

    // 设置轮询（每 10 秒刷新）
    const interval = setInterval(() => {
      fetchPaperBotDetail(selectedPaperBot.paper_bot_id);
      fetchPaperBotOrders(selectedPaperBot.paper_bot_id);
      fetchPaperBotPositions(selectedPaperBot.paper_bot_id);
      fetchPaperBotPortfolio(selectedPaperBot.paper_bot_id);
      fetchPaperBotLogs(selectedPaperBot.paper_bot_id);
    }, 10000);

    return () => clearInterval(interval);
  }, [selectedPaperBot, fetchPaperBotDetail, fetchPaperBotOrders, fetchPaperBotPositions, fetchPaperBotPortfolio, fetchPaperBotLogs]);

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

  // 辅助函数：获取真实 Bot 数量（只统计 active_bots + disconnected_bots）
  const getBotsCount = (data: unknown): number => {
    if (!data) return 0;
    const d = data as Record<string, unknown>;

    // 优先使用 containers_fallback（Docker 容器降级方案）
    if (d.containers_fallback) {
      const cf = d.containers_fallback as Record<string, unknown>;
      if (cf.total !== undefined) return cf.total as number;
      if (Array.isArray(cf.containers)) return cf.containers.length;
    }

    // 尝试从 bots 对象中提取 active_bots 和 disconnected_bots
    if (d.bots) {
      const bots = d.bots;

      // 如果直接是数组（旧格式兼容），直接返回长度
      if (Array.isArray(bots)) return bots.length;

      // 如果是对象，检查是否有 active_bots 或 disconnected_bots
      if (typeof bots === "object") {
        const botsObj = bots as Record<string, unknown>;

        // 统计 active_bots 和 disconnected_bots 的长度
        let count = 0;
        const activeBots = botsObj.active_bots;
        const disconnectedBots = botsObj.disconnected_bots;

        if (Array.isArray(activeBots)) count += activeBots.length;
        if (Array.isArray(disconnectedBots)) count += disconnectedBots.length;

        if (count > 0) return count;

        // 如果既没有 active_bots 也没有 disconnected_bots，说明不是 Bot 数据
        // 不再把 broker_host、client_state 等元数字段算作 Bot 数量
        // 这种情况返回 0，让卡片正确显示"暂无运行中的 Bot"
      }
    }

    // 旧格式兼容：直接是数组
    if (Array.isArray(data)) return data.length;

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
            <p className="font-semibold">当前页面为 Hummingbot Paper Bot 模拟交易页面，使用虚拟资金，不执行实盘交易。</p>
            <p className="text-amber-400/70 mt-1 text-xs">
              仅支持 Paper Bot 启动/停止，不支持下单、撤单（模拟 Bot 由前端记录，真实 Bot 由 Hummingbot 管理）。
            </p>
          </div>
        </div>

        {/* Paper Bot Configuration Section */}
        <PaperBotSection onStartSuccess={fetchPaperBots} />

        {/* Paper Bot Monitor Section */}
        <PaperBotMonitorSection
          paperBots={paperBots}
          paperBotsLoading={paperBotsLoading}
          selectedPaperBot={selectedPaperBot}
          onSelectPaperBot={setSelectedPaperBot}
          onRefresh={fetchPaperBots}
          paperBotDetail={paperBotDetail}
          paperBotOrders={paperBotOrders}
          paperBotPositions={paperBotPositions}
          paperBotPortfolio={paperBotPortfolio}
          paperBotLogs={paperBotLogs}
          stopResult={stopResult}
          onStopClick={() => setShowStopDialog(true)}
        />

        {/* Stop Paper Bot Confirmation Dialog */}
        {showStopDialog && selectedPaperBot && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 max-w-md w-full mx-4">
              <h3 className="text-lg font-bold text-slate-100 mb-4">确认停止 Hummingbot Paper Bot？</h3>
              <div className="space-y-3 mb-6">
                <p className="text-slate-300 text-sm">当前操作仅停止 Paper Bot：</p>
                <ul className="text-slate-400 text-xs space-y-1 ml-4">
                  <li>• 使用虚拟资金</li>
                  <li>• 不会执行真实交易</li>
                  <li>• 不会撤单</li>
                  <li>• 不会平仓</li>
                  <li>• 不会影响真实交易所账户</li>
                  <li>• 不支持 Testnet</li>
                  <li>• 不支持 Live</li>
                </ul>
              </div>
              <div className="flex justify-end gap-3">
                <Button
                  variant="outline"
                  onClick={() => setShowStopDialog(false)}
                  disabled={stopping}
                  className="text-slate-300"
                >
                  取消
                </Button>
                <Button
                  onClick={handleStopBot}
                  disabled={stopping}
                  className="bg-red-600 hover:bg-red-500 text-white"
                >
                  {stopping ? (
                    <>
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                      停止中...
                    </>
                  ) : (
                    <>
                      <Activity className="w-4 h-4 mr-2" />
                      确认停止 Paper Bot
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

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
                Hummingbot 实盘资产（只读）
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
                    <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center">
                      <Bot className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                      <p className="text-slate-400 text-sm">暂无实盘账户资产数据</p>
                      <p className="text-slate-500 text-xs mt-1">请先在 Hummingbot 中配置交易所账户。</p>
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
                      {getBotsCount(bots?.data) > 0 ? "有运行中的 Bot" : "暂无运行中的 Hummingbot Bot"}
                    </Badge>
                  </div>

                  {/* Empty state for no bots */}
                  {getBotsCount(bots?.data) === 0 && !bots?.error && (
                    <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center">
                      <Bot className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                      <p className="text-slate-400 text-sm">暂无运行中的 Hummingbot Bot</p>
                      <p className="text-slate-500 text-xs mt-1">请先在 Hummingbot 中启动 Bot。</p>
                    </div>
                  )}

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
                Hummingbot 实盘订单（只读）
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
                        <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center">
                          <ShoppingCart className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                          <p className="text-slate-400 text-sm">暂无实盘订单</p>
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
                Hummingbot 实盘持仓（只读）
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
                        <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center">
                          <Wallet className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                          <p className="text-slate-400 text-sm">暂无实盘持仓</p>
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

// ── Paper Bot Section Component ──────────────────────────────────────────────────

interface PaperBotSectionProps {
  onStartSuccess?: () => void;
}

function PaperBotSection({ onStartSuccess }: PaperBotSectionProps) {
  const [formData, setFormData] = useState<PaperBotFormData>({
    bot_name: "",
    strategy_type: "grid",
    trading_pair: "BTC-USDT",
    paper_initial_balance: 10000,
    order_amount: 100,
    max_runtime_minutes: 120,
    spread_pct: 0.5,
    grid_spacing_pct: 0.5,
    grid_levels: 20,
    stop_loss_pct: 3,
    take_profit_pct: 5,
  });

  const [previewResult, setPreviewResult] = useState<PaperBotPreviewResponse | null>(null);
  const [startResult, setStartResult] = useState<PaperBotStartResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [copied, setCopied] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const updateField = (field: keyof PaperBotFormData, value: string | number) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // 清除字段错误
    if (errors[field]) {
      setErrors(prev => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.bot_name || formData.bot_name.length < 3) {
      newErrors.bot_name = "Bot 名称至少 3 个字符";
    } else if (!/^[a-zA-Z0-9_-]+$/.test(formData.bot_name)) {
      newErrors.bot_name = "只能包含字母、数字、下划线和中划线";
    }

    if (formData.order_amount > formData.paper_initial_balance) {
      newErrors.order_amount = "单笔订单金额不能大于初始资金";
    }

    if (formData.strategy_type === "grid") {
      if (!formData.grid_spacing_pct || formData.grid_spacing_pct <= 0) {
        newErrors.grid_spacing_pct = "网格间距必须大于 0";
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validateForm()) return;

    setLoading(true);
    setPreviewResult(null);

    try {
      const response = await fetch("/api/v1/hummingbot/paper-bots/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      const result = await response.json();
      setPreviewResult(result);
    } catch (err) {
      setPreviewResult({
        valid: false,
        source: "quantagent",
        mode: "paper",
        live_trading: false,
        testnet: false,
        data: null,
        error: `请求失败: ${err instanceof Error ? err.message : "网络错误"}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (previewResult?.data) {
      navigator.clipboard.writeText(JSON.stringify(previewResult.data.config_preview, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleStartBot = async () => {
    setStarting(true);
    setStartResult(null);

    try {
      const response = await fetch("/api/v1/hummingbot/paper-bots/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      const result = await response.json();
      setStartResult(result);

      // 启动成功后通知父组件刷新 Paper Bot 列表
      if (result.started && onStartSuccess) {
        onStartSuccess();
      }
    } catch (err) {
      setStartResult({
        started: false,
        source: "quantagent",
        mode: "paper",
        live_trading: false,
        testnet: false,
        data: null,
        error: `请求失败: ${err instanceof Error ? err.message : "网络错误"}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setStarting(false);
      setShowConfirmDialog(false);
    }
  };

  return (
    <div className="mb-8">
      {/* Section Header */}
      <div className="mb-4">
        <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
          <div className="w-8 h-8 bg-green-500/10 rounded-lg flex items-center justify-center border border-green-500/20">
            <Play className="w-4 h-4 text-green-400" />
          </div>
          创建 Hummingbot Paper Bot
        </h2>
        <p className="text-slate-400 text-xs mt-1 ml-10">
          生成配置预览后可启动 Paper Bot，使用虚拟资金模拟运行，不执行真实交易。
        </p>
      </div>

      {/* Security Notice */}
      <div className="mb-6 p-4 bg-green-500/10 border border-green-500/20 rounded-xl">
        <div className="flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
          <div className="text-sm text-green-300">
            <p className="font-semibold">安全提示</p>
            <ul className="mt-2 space-y-1 text-green-400/70 text-xs">
              <li>• 使用虚拟资金模拟运行</li>
              <li>• 不执行真实下单</li>
              <li>• 不连接真实交易所账户</li>
              <li>• 不需要 API Key</li>
              <li>• 不支持 Testnet</li>
              <li>• 不支持 Live</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Form Card */}
      <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50 mb-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-slate-100 text-base">配置参数</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Bot Name */}
            <div className="space-y-1">
              <Label htmlFor="bot_name" className="text-slate-300 text-xs">
                Bot 名称 <span className="text-red-400">*</span>
              </Label>
              <Input
                id="bot_name"
                placeholder="paper_grid_btc_001"
                value={formData.bot_name}
                onChange={e => updateField("bot_name", e.target.value)}
                className={`bg-slate-800 border-slate-700 text-slate-100 text-sm ${
                  errors.bot_name ? "border-red-500" : ""
                }`}
              />
              {errors.bot_name && (
                <p className="text-red-400 text-[10px]">{errors.bot_name}</p>
              )}
            </div>

            {/* Strategy Type */}
            <div className="space-y-1">
              <Label htmlFor="strategy_type" className="text-slate-300 text-xs">
                策略类型 <span className="text-red-400">*</span>
              </Label>
              <select
                id="strategy_type"
                value={formData.strategy_type}
                onChange={e => updateField("strategy_type", e.target.value)}
                className="w-full h-9 px-3 bg-slate-800 border border-slate-700 rounded-md text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
              >
                <option value="grid">Grid (网格交易)</option>
                <option value="position_executor">Position Executor (仓位执行)</option>
              </select>
            </div>

            {/* Trading Pair */}
            <div className="space-y-1">
              <Label htmlFor="trading_pair" className="text-slate-300 text-xs">
                交易对 <span className="text-red-400">*</span>
              </Label>
              <select
                id="trading_pair"
                value={formData.trading_pair}
                onChange={e => updateField("trading_pair", e.target.value)}
                className="w-full h-9 px-3 bg-slate-800 border border-slate-700 rounded-md text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
              >
                <option value="BTC-USDT">BTC-USDT</option>
                <option value="ETH-USDT">ETH-USDT</option>
                <option value="SOL-USDT">SOL-USDT</option>
                <option value="BNBUSDT">BNB-USDT</option>
                <option value="DOGEUSDT">DOGE-USDT</option>
              </select>
            </div>

            {/* Paper Initial Balance */}
            <div className="space-y-1">
              <Label htmlFor="paper_initial_balance" className="text-slate-300 text-xs">
                Paper 初始资金 <span className="text-red-400">*</span>
              </Label>
              <Input
                id="paper_initial_balance"
                type="number"
                min={1}
                max={1000000}
                value={formData.paper_initial_balance}
                onChange={e => updateField("paper_initial_balance", Number(e.target.value))}
                className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
              />
              <p className="text-slate-500 text-[10px]">建议不超过 1,000,000</p>
            </div>

            {/* Order Amount */}
            <div className="space-y-1">
              <Label htmlFor="order_amount" className="text-slate-300 text-xs">
                单笔订单金额 <span className="text-red-400">*</span>
              </Label>
              <Input
                id="order_amount"
                type="number"
                min={1}
                value={formData.order_amount}
                onChange={e => updateField("order_amount", Number(e.target.value))}
                className={`bg-slate-800 border-slate-700 text-slate-100 text-sm ${
                  errors.order_amount ? "border-red-500" : ""
                }`}
              />
              {errors.order_amount && (
                <p className="text-red-400 text-[10px]">{errors.order_amount}</p>
              )}
              <p className="text-slate-500 text-[10px]">建议不超过初始资金的 50%</p>
            </div>

            {/* Max Runtime */}
            <div className="space-y-1">
              <Label htmlFor="max_runtime_minutes" className="text-slate-300 text-xs">
                最大运行时间 (分钟)
              </Label>
              <Input
                id="max_runtime_minutes"
                type="number"
                min={1}
                max={10080}
                value={formData.max_runtime_minutes}
                onChange={e => updateField("max_runtime_minutes", Number(e.target.value))}
                className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
              />
              <p className="text-slate-500 text-[10px]">最大 10080 分钟 (7天)</p>
            </div>

            {/* Stop Loss */}
            <div className="space-y-1">
              <Label htmlFor="stop_loss_pct" className="text-slate-300 text-xs">
                止损比例 stop_loss_pct
              </Label>
              <Input
                id="stop_loss_pct"
                type="number"
                min={0}
                max={50}
                step={0.1}
                value={formData.stop_loss_pct}
                onChange={e => updateField("stop_loss_pct", Number(e.target.value))}
                className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
              />
              <p className="text-slate-500 text-[10px]">0 表示不启用止损</p>
            </div>

            {/* Take Profit */}
            <div className="space-y-1">
              <Label htmlFor="take_profit_pct" className="text-slate-300 text-xs">
                止盈比例 take_profit_pct
              </Label>
              <Input
                id="take_profit_pct"
                type="number"
                min={0}
                max={100}
                step={0.1}
                value={formData.take_profit_pct}
                onChange={e => updateField("take_profit_pct", Number(e.target.value))}
                className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
              />
              <p className="text-slate-500 text-[10px]">0 表示不启用止盈</p>
            </div>

            {/* Strategy-specific fields */}
            {formData.strategy_type === "position_executor" && (
              <>
                {/* Spread */}
                <div className="space-y-1">
                  <Label htmlFor="spread_pct" className="text-slate-300 text-xs">
                    价差 spread_pct
                  </Label>
                  <Input
                    id="spread_pct"
                    type="number"
                    min={0}
                    max={20}
                    step={0.1}
                    value={formData.spread_pct}
                    onChange={e => updateField("spread_pct", Number(e.target.value))}
                    className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
                  />
                  <p className="text-slate-500 text-[10px]">0-20%，仅 position_executor 使用</p>
                </div>
              </>
            )}

            {formData.strategy_type === "grid" && (
              <>
                {/* Grid Spacing */}
                <div className="space-y-1">
                  <Label htmlFor="grid_spacing_pct" className="text-slate-300 text-xs">
                    网格间距 grid_spacing_pct <span className="text-red-400">*</span>
                  </Label>
                  <Input
                    id="grid_spacing_pct"
                    type="number"
                    min={0.01}
                    max={20}
                    step={0.01}
                    value={formData.grid_spacing_pct}
                    onChange={e => updateField("grid_spacing_pct", Number(e.target.value))}
                    className={`bg-slate-800 border-slate-700 text-slate-100 text-sm ${
                      errors.grid_spacing_pct ? "border-red-500" : ""
                    }`}
                  />
                  {errors.grid_spacing_pct && (
                    <p className="text-red-400 text-[10px]">{errors.grid_spacing_pct}</p>
                  )}
                  <p className="text-slate-500 text-[10px]">0.01-20%，仅 grid 使用</p>
                </div>

                {/* Grid Levels */}
                <div className="space-y-1">
                  <Label htmlFor="grid_levels" className="text-slate-300 text-xs">
                    网格层数 grid_levels
                  </Label>
                  <Input
                    id="grid_levels"
                    type="number"
                    min={2}
                    max={200}
                    value={formData.grid_levels}
                    onChange={e => updateField("grid_levels", Number(e.target.value))}
                    className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
                  />
                  <p className="text-slate-500 text-[10px]">2-200，默认 20</p>
                </div>
              </>
            )}
          </div>

          {/* Submit Button */}
          <div className="mt-6 flex items-center gap-4">
            <Button
              onClick={handleSubmit}
              disabled={loading}
              className="bg-green-600 hover:bg-green-500 text-white"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  生成中...
                </>
              ) : (
                <>
                  <FileJson className="w-4 h-4 mr-2" />
                  生成 Paper Bot 配置预览
                </>
              )}
            </Button>
            {loading && (
              <p className="text-slate-400 text-xs">正在生成配置预览...</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Preview Result */}
      {previewResult && (
        <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-slate-100 text-base flex items-center gap-2">
                <FileJson className="w-4 h-4 text-cyan-400" />
                Paper Bot 配置预览
                {previewResult.valid ? (
                  <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20 ml-2">
                    <CheckCircle className="w-3 h-3 mr-1" />
                    有效
                  </Badge>
                ) : (
                  <Badge variant="outline" className="bg-red-500/10 text-red-400 border-red-500/20 ml-2">
                    <XCircle className="w-3 h-3 mr-1" />
                    无效
                  </Badge>
                )}
              </CardTitle>
              {previewResult.valid && previewResult.data && (
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopy}
                    className="h-8 text-xs"
                  >
                    {copied ? (
                      <>
                        <Check className="w-3 h-3 mr-1" />
                        已复制
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3 mr-1" />
                        复制 JSON
                      </>
                    )}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => setShowConfirmDialog(true)}
                    className="h-8 bg-blue-600 hover:bg-blue-500 text-white text-xs"
                  >
                    <Play className="w-3 h-3 mr-1" />
                    启动 Paper Bot
                  </Button>
                </div>
              )}
            </div>
            {previewResult.valid && previewResult.data && (
              <p className="text-green-400/70 text-xs mt-1">
                仅启动 Paper Bot，不执行真实交易。
              </p>
            )}
          </CardHeader>
          <CardContent>
            {previewResult.error ? (
              /* Error Display */
              <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-red-400 text-sm font-semibold">生成失败</p>
                    <p className="text-red-300/70 text-xs mt-1">{previewResult.error}</p>
                  </div>
                </div>
              </div>
            ) : previewResult.data ? (
              /* Success Display */
              <div className="space-y-4">
                {/* Mode Indicators */}
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">
                    <CheckCircle className="w-3 h-3 mr-1" />
                    mode: {previewResult.data.config_preview.mode}
                  </Badge>
                  <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">
                    <CheckCircle className="w-3 h-3 mr-1" />
                    live_trading: {String(previewResult.data.config_preview.live_trading)}
                  </Badge>
                  <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">
                    <CheckCircle className="w-3 h-3 mr-1" />
                    testnet: {String(previewResult.data.config_preview.testnet)}
                  </Badge>
                </div>

                {/* Warnings */}
                {previewResult.data.warnings && previewResult.data.warnings.length > 0 && (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                    {previewResult.data.warnings.map((warning, i) => (
                      <p key={i} className="text-amber-300 text-xs flex items-start gap-2">
                        <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
                        {warning}
                      </p>
                    ))}
                  </div>
                )}

                {/* JSON Preview */}
                <div className="p-4 bg-slate-950 rounded-lg border border-slate-800 overflow-x-auto">
                  <pre className="text-slate-300 text-xs font-mono whitespace-pre-wrap">
                    {JSON.stringify(previewResult.data.config_preview, null, 2)}
                  </pre>
                </div>

                {/* Notes */}
                {previewResult.data.config_preview.notes && (
                  <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <p className="text-slate-400 text-xs mb-2 font-semibold">说明：</p>
                    <ul className="space-y-1">
                      {previewResult.data.config_preview.notes.map((note, i) => (
                        <li key={i} className="text-slate-400 text-xs flex items-start gap-2">
                          <span className="text-cyan-400">•</span>
                          {note}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* Start Result */}
      {startResult && (
        <Card className={`bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50 ${
          startResult.submitted ? "border-blue-500/30" : "border-red-500/30"
        }`}>
          <CardHeader className="pb-2">
            <CardTitle className="text-slate-100 text-base flex items-center gap-2">
              <Play className={`w-4 h-4 ${startResult.submitted ? "text-blue-400" : "text-red-400"}`} />
              Paper Bot 启动结果
              {startResult.submitted && !startResult.remote_confirmed && (
                <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/20 ml-2">
                  <CheckCircle className="w-3 h-3 mr-1" />
                  已提交（待对账）
                </Badge>
              )}
              {startResult.submitted && startResult.remote_confirmed && (
                <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20 ml-2">
                  <CheckCircle className="w-3 h-3 mr-1" />
                  已提交且远端已确认
                </Badge>
              )}
              {!startResult.submitted && (
                <Badge variant="outline" className="bg-red-500/10 text-red-400 border-red-500/20 ml-2">
                  <XCircle className="w-3 h-3 mr-1" />
                  提交失败
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {startResult.error ? (
              /* Error Display */
              <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-red-400 text-sm font-semibold">启动失败</p>
                    <p className="text-red-300/70 text-xs mt-1">{startResult.error}</p>
                  </div>
                </div>
              </div>
            ) : startResult.data ? (
              /* Success Display */
              <div className="space-y-4">
                {/* Status Info */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <p className="text-slate-400 text-xs">Paper Bot ID</p>
                    <p className="text-slate-100 text-xs font-mono mt-1">{startResult.data.paper_bot_id}</p>
                  </div>
                  <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <p className="text-slate-400 text-xs">Bot 名称</p>
                    <p className="text-slate-100 text-xs mt-1">{startResult.data.bot_name}</p>
                  </div>
                  <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <p className="text-slate-400 text-xs">策略类型</p>
                    <p className="text-slate-100 text-xs mt-1">{startResult.data.strategy_type}</p>
                  </div>
                  <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <p className="text-slate-400 text-xs">交易对</p>
                    <p className="text-slate-100 text-xs mt-1">{startResult.data.trading_pair}</p>
                  </div>
                </div>

                {/* Status Badges */}
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge
                    variant="outline"
                    className={
                      startResult.data.local_status === "submitted" ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                      "bg-slate-500/10 text-slate-400 border-slate-500/20"
                    }
                  >
                    本地状态: {startResult.data.local_status}
                  </Badge>
                  <Badge
                    variant="outline"
                    className={
                      startResult.data.remote_confirmed ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-slate-500/10 text-slate-400 border-slate-500/20"
                    }
                  >
                    远端已确认: {String(startResult.data.remote_confirmed)}
                  </Badge>
                  <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">
                    mode: {startResult.mode}
                  </Badge>
                  <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">
                    live_trading: {String(startResult.live_trading)}
                  </Badge>
                </div>

                {/* Remote Confirmation Notice */}
                {startResult.data.remote_confirmed ? (
                  <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
                    <p className="text-green-300 text-xs">
                      <span className="font-semibold">Hummingbot 已确认启动 Paper Bot。</span>
                      该 Bot 已在 Hummingbot 远端运行。
                    </p>
                  </div>
                ) : (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                    <p className="text-amber-300 text-xs">
                      <span className="font-semibold">Paper Bot 本地记录已创建。</span>
                      当前 Hummingbot API 尚未确认该 Bot 已真正运行（remote_confirmed=false）。
                      请点击刷新按钮，通过对账检测远端状态。
                    </p>
                  </div>
                )}

                {/* Started At */}
                <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                  <p className="text-slate-400 text-xs">创建时间</p>
                  <p className="text-slate-100 text-xs mt-1">
                    {new Date(startResult.data.started_at).toLocaleString()}
                  </p>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-bold text-slate-100 mb-4">确认启动 Hummingbot Paper Bot？</h3>
            <div className="space-y-3 mb-6">
              <p className="text-slate-300 text-sm">当前仅启动 Paper Bot：</p>
              <ul className="text-slate-400 text-xs space-y-1 ml-4">
                <li>• 使用虚拟资金</li>
                <li>• 不连接真实交易所账户</li>
                <li>• 不执行真实交易</li>
                <li>• 不需要 API Key</li>
                <li>• 不支持 Testnet</li>
                <li>• 不支持 Live</li>
              </ul>
            </div>
            <div className="flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={() => setShowConfirmDialog(false)}
                className="text-slate-300"
              >
                取消
              </Button>
              <Button
                onClick={handleStartBot}
                disabled={starting}
                className="bg-blue-600 hover:bg-blue-500 text-white"
              >
                {starting ? (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                    启动中...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 mr-2" />
                    确认启动
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Paper Bot Monitor Section moved to HummingbotPage ──

// ── Paper Bot 监控区域组件 ──────────────────────────────────────────────────

interface PaperBotMonitorSectionProps {
  paperBots: { bots: PaperBot[] } | null;
  paperBotsLoading: boolean;
  selectedPaperBot: PaperBot | null;
  onSelectPaperBot: (bot: PaperBot | null) => void;
  onRefresh: () => void;
  paperBotDetail: Record<string, unknown> | null;
  paperBotOrders: PaperBotOrdersResponse | null;
  paperBotPositions: PaperBotPositionsResponse | null;
  paperBotPortfolio: PaperBotPortfolioResponse | null;
  paperBotLogs: PaperBotLogsResponse | null;
  stopResult: Record<string, unknown> | null;
  onStopClick: () => void;
}

function PaperBotMonitorSection({
  paperBots,
  paperBotsLoading,
  selectedPaperBot,
  onSelectPaperBot,
  onRefresh,
  paperBotDetail,
  paperBotOrders,
  paperBotPositions,
  paperBotPortfolio,
  paperBotLogs,
  stopResult,
  onStopClick,
}: PaperBotMonitorSectionProps) {
  return (
    <div className="mb-8">
      {/* Section Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-500/10 rounded-lg flex items-center justify-center border border-blue-500/20">
              <Activity className="w-4 h-4 text-blue-400" />
            </div>
            Hummingbot Paper Bot 运行监控
          </h2>
          <p className="text-slate-400 text-xs mt-1 ml-10">
            当前仅展示 Paper Bot 运行状态和模拟数据，不执行真实交易。
          </p>
        </div>
        <Button
          size="sm"
          onClick={onRefresh}
          disabled={paperBotsLoading}
          className="h-8 bg-blue-600 hover:bg-blue-500 text-white text-xs"
        >
          <RefreshCw className={`w-3 h-3 mr-1 ${paperBotsLoading ? "animate-spin" : ""}`} />
          刷新
        </Button>
      </div>

      {/* Paper Bot 列表 */}
      <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50 mb-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-slate-100 text-base flex items-center gap-2">
            <Bot className="w-4 h-4 text-blue-400" />
            Paper Bot 列表
            {paperBots?.bots && (
              <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/20 ml-2">
                {paperBots.bots.length} 个
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {paperBotsLoading && !paperBots ? (
            <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
              <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
            </div>
          ) : !paperBots?.bots || paperBots.bots.length === 0 ? (
            <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center">
              <Bot className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-slate-400 text-sm">当前还没有真正运行的 Hummingbot Paper Bot。</p>
              <p className="text-slate-500 text-xs mt-1">请先生成配置预览，并在下一步启动 Paper Bot。</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-2 px-3 text-slate-400">Bot 名称</th>
                    <th className="text-left py-2 px-3 text-slate-400">策略类型</th>
                    <th className="text-left py-2 px-3 text-slate-400">交易对</th>
                    <th className="text-left py-2 px-3 text-slate-400">本地状态</th>
                    <th className="text-left py-2 px-3 text-slate-400">远端状态</th>
                    <th className="text-left py-2 px-3 text-slate-400">运行时长</th>
                    <th className="text-left py-2 px-3 text-slate-400">启动时间</th>
                    <th className="text-left py-2 px-3 text-slate-400">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {paperBots.bots.map((bot) => (
                    <tr
                      key={bot.paper_bot_id}
                      className={`border-b border-slate-800 hover:bg-slate-800/30 cursor-pointer ${
                        selectedPaperBot?.paper_bot_id === bot.paper_bot_id ? "bg-blue-500/10" : ""
                      }`}
                      onClick={() => onSelectPaperBot(bot)}
                    >
                      <td className="py-2 px-3 text-slate-300 font-mono">{bot.bot_name}</td>
                      <td className="py-2 px-3 text-slate-300">{bot.strategy_type}</td>
                      <td className="py-2 px-3 text-slate-300">{bot.trading_pair}</td>
                      <td className="py-2 px-3">
                        <Badge
                          variant="outline"
                          className={
                            bot.local_status === "running" ? "bg-green-500/10 text-green-400 border-green-500/20" :
                            bot.local_status === "starting" ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                            bot.local_status === "submitted" ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                            bot.local_status === "stopped" ? "bg-slate-500/10 text-slate-400 border-slate-500/20" :
                            bot.local_status === "error" ? "bg-red-500/10 text-red-400 border-red-500/20" :
                            "bg-amber-500/10 text-amber-400 border-amber-500/20"
                          }
                        >
                          {bot.local_status}
                        </Badge>
                      </td>
                      <td className="py-2 px-3">
                        <Badge
                          variant="outline"
                          className={
                            bot.remote_status === "running" ? "bg-green-500/10 text-green-400 border-green-500/20" :
                            bot.remote_status === "not_detected" ? "bg-slate-500/10 text-slate-400 border-slate-500/20" :
                            "bg-amber-500/10 text-amber-400 border-amber-500/20"
                          }
                        >
                          {bot.remote_status === "running" ? "已检测到" :
                           bot.remote_status === "not_detected" ? "未检测到" :
                           bot.remote_status}
                          {bot.matched_by && bot.matched_by !== "none" && (
                            <span className="text-slate-400 ml-1">via {bot.matched_by}</span>
                          )}
                        </Badge>
                      </td>
                      <td className="py-2 px-3 text-slate-300">
                        {formatRuntime(bot.runtime_seconds)}
                      </td>
                      <td className="py-2 px-3 text-slate-400">
                        {bot.started_at ? new Date(bot.started_at).toLocaleString() : "-"}
                      </td>
                      <td className="py-2 px-3">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectPaperBot(bot);
                          }}
                          className="h-6 text-[10px]"
                        >
                          查看详情
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Paper Bot 详情 */}
      {selectedPaperBot && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 详情卡片 */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 text-base flex items-center gap-2">
                <Bot className="w-4 h-4 text-blue-400" />
                Paper Bot 详情
              </CardTitle>
            </CardHeader>
            <CardContent>
              {paperBotDetail ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs">Paper Bot ID</p>
                      <p className="text-slate-100 text-xs font-mono mt-1">
                        {(paperBotDetail as Record<string, unknown>)?.paper_bot_id as string || "-"}
                      </p>
                    </div>
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs">Bot 名称</p>
                      <p className="text-slate-100 text-xs mt-1">
                        {(paperBotDetail as Record<string, unknown>)?.bot_name as string || "-"}
                      </p>
                    </div>
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs">策略类型</p>
                      <p className="text-slate-100 text-xs mt-1">
                        {(paperBotDetail as Record<string, unknown>)?.strategy_type as string || "-"}
                      </p>
                    </div>
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs">交易对</p>
                      <p className="text-slate-100 text-xs mt-1">
                        {(paperBotDetail as Record<string, unknown>)?.trading_pair as string || "-"}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">
                      mode: {(paperBotDetail as Record<string, unknown>)?.mode as string || "-"}
                    </Badge>
                    <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">
                      live_trading: {String((paperBotDetail as Record<string, unknown>)?.live_trading)}
                    </Badge>
                    <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">
                      testnet: {String((paperBotDetail as Record<string, unknown>)?.testnet)}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={
                        (paperBotDetail as Record<string, unknown>)?.local_status === "running" ? "bg-green-500/10 text-green-400 border-green-500/20" :
                        (paperBotDetail as Record<string, unknown>)?.local_status === "starting" ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                        (paperBotDetail as Record<string, unknown>)?.local_status === "submitted" ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                        (paperBotDetail as Record<string, unknown>)?.local_status === "stopped" ? "bg-slate-500/10 text-slate-400 border-slate-500/20" :
                        "bg-amber-500/10 text-amber-400 border-amber-500/20"
                      }
                    >
                      本地状态: {(paperBotDetail as Record<string, unknown>)?.local_status as string || "-"}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={
                        (paperBotDetail as Record<string, unknown>)?.remote_status === "running" ? "bg-green-500/10 text-green-400 border-green-500/20" :
                        "bg-slate-500/10 text-slate-400 border-slate-500/20"
                      }
                    >
                      远端状态: {(paperBotDetail as Record<string, unknown>)?.remote_status as string || "-"}
                    </Badge>
                  </div>

                  {/* 对账信息 */}
                  <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                    <p className="text-slate-400 text-xs mb-2 font-semibold">对账信息</p>
                    <div className="grid grid-cols-2 gap-2 text-[10px]">
                      <div>
                        <span className="text-slate-500">matched_remote_bot: </span>
                        <span className={(paperBotDetail as Record<string, unknown>)?.matched_remote_bot ? "text-green-400" : "text-slate-400"}>
                          {String((paperBotDetail as Record<string, unknown>)?.matched_remote_bot ?? false)}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500">matched_by: </span>
                        <span className="text-slate-300">{(paperBotDetail as Record<string, unknown>)?.matched_by as string || "-"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">hummingbot_bot_id: </span>
                        <span className="text-slate-300">{(paperBotDetail as Record<string, unknown>)?.hummingbot_bot_id as string || "-"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">last_remote_check: </span>
                        <span className="text-slate-300">
                          {(paperBotDetail as Record<string, unknown>)?.last_remote_check_at
                            ? new Date((paperBotDetail as Record<string, unknown>)?.last_remote_check_at as string).toLocaleTimeString()
                            : "-"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* 停止按钮 - 仅本地状态为 submitted/starting/running 时显示 */}
                  {(paperBotDetail as Record<string, unknown>)?.mode === "paper" &&
                   (paperBotDetail as Record<string, unknown>)?.live_trading === false &&
                   (paperBotDetail as Record<string, unknown>)?.testnet === false &&
                   ["submitted", "starting", "running"].includes((paperBotDetail as Record<string, unknown>)?.local_status as string) && (
                    <div className="mt-3">
                      <Button
                        size="sm"
                        onClick={onStopClick}
                        className="h-7 text-[10px] bg-red-600 hover:bg-red-500 text-white"
                      >
                        <Activity className="w-3 h-3 mr-1" />
                        停止 Paper Bot
                      </Button>
                    </div>
                  )}

                  {/* 停止结果展示 */}
                  {stopResult && (
                    <div className="mt-3 space-y-2">
                      {stopResult.stopped ? (
                        <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
                          <p className="text-green-400 text-xs">
                            <span className="font-semibold">成功:</span> Paper Bot 已停止。
                          </p>
                        </div>
                      ) : (
                        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                          <p className="text-red-400 text-xs">
                            <span className="font-semibold">失败:</span> {String(stopResult.error || "未知错误")}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {paperBotDetail && (paperBotDetail as Record<string, unknown>)?.last_error && (
                    <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                      <p className="text-red-400 text-xs">
                        <span className="font-semibold">错误:</span> {String((paperBotDetail as Record<string, unknown>)?.last_error)}
                      </p>
                    </div>
                  )}

                  {/* Config Preview */}
                  {(paperBotDetail as Record<string, unknown>)?.config && (
                    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50">
                      <p className="text-slate-400 text-xs mb-2">配置预览</p>
                      <pre className="text-slate-300 text-[10px] font-mono overflow-x-auto max-h-40">
                        {JSON.stringify((paperBotDetail as Record<string, unknown>)?.config, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" /> 加载中...
                </div>
              )}
            </CardContent>
          </Card>

          {/* 模拟订单卡片 */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 text-base flex items-center gap-2">
                <ShoppingCart className="w-4 h-4 text-orange-400" />
                Paper Bot 模拟订单（只读）
              </CardTitle>
            </CardHeader>
            <CardContent>
              {paperBotOrders?.data?.filter_note && (
                <div className="mb-3 p-2 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                  <p className="text-amber-400 text-[10px]">{paperBotOrders.data.filter_note}</p>
                </div>
              )}
              {!paperBotOrders?.data?.orders || paperBotOrders.data.orders.length === 0 ? (
                <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center">
                  <ShoppingCart className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                  <p className="text-slate-400 text-sm">
                    {paperBotOrders?.data?.filter_note
                      ? paperBotOrders.data.filter_note
                      : "当前 Paper Bot 尚未被 Hummingbot 远端确认运行，因此暂无模拟订单。"}
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto max-h-60">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-slate-700">
                        <th className="text-left py-1 px-2 text-slate-400">交易对</th>
                        <th className="text-left py-1 px-2 text-slate-400">方向</th>
                        <th className="text-left py-1 px-2 text-slate-400">类型</th>
                        <th className="text-right py-1 px-2 text-slate-400">价格</th>
                        <th className="text-right py-1 px-2 text-slate-400">数量</th>
                        <th className="text-left py-1 px-2 text-slate-400">状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paperBotOrders.data.orders.slice(0, 10).map((order, idx) => (
                        <tr key={idx} className="border-b border-slate-800">
                          <td className="py-1 px-2 text-slate-300">{String(order.symbol || order.trading_pair || "-")}</td>
                          <td className={`py-1 px-2 ${order.side === "BUY" ? "text-green-400" : "text-red-400"}`}>
                            {String(order.side || "-")}
                          </td>
                          <td className="py-1 px-2 text-slate-300">{String(order.order_type || order.type || "-")}</td>
                          <td className="py-1 px-2 text-right text-slate-300">{order.price ? String(order.price) : "-"}</td>
                          <td className="py-1 px-2 text-right text-slate-300">{String(order.amount || order.quantity || "-")}</td>
                          <td className="py-1 px-2">
                            <Badge variant="outline" className="text-[10px] bg-slate-700/50 text-slate-300 border-slate-600/50">
                              {String(order.status || "-")}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 模拟持仓卡片 */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 text-base flex items-center gap-2">
                <Wallet className="w-4 h-4 text-emerald-400" />
                Paper Bot 模拟持仓（只读）
              </CardTitle>
            </CardHeader>
            <CardContent>
              {paperBotPositions?.data?.filter_note && (
                <div className="mb-3 p-2 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                  <p className="text-amber-400 text-[10px]">{paperBotPositions.data.filter_note}</p>
                </div>
              )}
              {!paperBotPositions?.data?.positions || paperBotPositions.data.positions.length === 0 ? (
                <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 text-center">
                  <Wallet className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                  <p className="text-slate-400 text-sm">
                    {paperBotPositions?.data?.filter_note
                      ? paperBotPositions.data.filter_note
                      : "当前 Paper Bot 尚未被 Hummingbot 远端确认运行，因此暂无模拟持仓。"}
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto max-h-60">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-slate-700">
                        <th className="text-left py-1 px-2 text-slate-400">交易对</th>
                        <th className="text-left py-1 px-2 text-slate-400">方向</th>
                        <th className="text-right py-1 px-2 text-slate-400">数量</th>
                        <th className="text-right py-1 px-2 text-slate-400">开仓价</th>
                        <th className="text-right py-1 px-2 text-slate-400">浮动盈亏</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paperBotPositions.data.positions.slice(0, 10).map((pos, idx) => {
                        const pnl = pos.unrealized_pnl || pos.unrealizedPnl || pos.pnl;
                        const isProfit = typeof pnl === "number" && pnl >= 0;
                        return (
                          <tr key={idx} className="border-b border-slate-800">
                            <td className="py-1 px-2 text-slate-300">{String(pos.symbol || pos.trading_pair || "-")}</td>
                            <td className={`py-1 px-2 ${pos.side === "LONG" || pos.side === "BUY" ? "text-green-400" : "text-red-400"}`}>
                              {String(pos.side || "-")}
                            </td>
                            <td className="py-1 px-2 text-right text-slate-300">{String(pos.amount || pos.quantity || "-")}</td>
                            <td className="py-1 px-2 text-right text-slate-300">{pos.entry_price ? String(pos.entry_price) : "-"}</td>
                            <td className={`py-1 px-2 text-right ${isProfit ? "text-green-400" : "text-red-400"}`}>
                              {pnl !== undefined ? String(pnl) : "-"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 日志卡片 */}
          <Card className="bg-gradient-to-br from-slate-900 to-slate-800/50 border-slate-700/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100 text-base flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-purple-400" />
                Paper Bot 日志（只读）
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!paperBotLogs?.data?.logs_available ? (
                <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
                    <p className="text-slate-400 text-xs">
                      {paperBotLogs?.data?.message || "当前 Hummingbot API 版本暂未提供 Paper Bot 日志接口，请通过 docker compose logs 查看。"}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="p-4 bg-slate-950 rounded-lg border border-slate-800 max-h-60 overflow-y-auto">
                  <pre className="text-slate-300 text-[10px] font-mono whitespace-pre-wrap">
                    {paperBotLogs.data.lines?.slice(0, 50).join("\n") || "暂无日志数据"}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ── 辅助函数 ────────────────────────────────────────────────────────────────

function formatRuntime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}
