"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  RefreshCw, Wifi, WifiOff, Bot, AlertTriangle, CheckCircle,
  XCircle, ArrowLeft, AlertCircle, ShieldCheck, Play, Copy, Check,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────────

interface TestnetPreviewResponse {
  valid: boolean;
  source: string;
  mode: string;
  market_type: string;
  live_trading: boolean;
  testnet: boolean;
  requires_api_key: boolean;
  uses_real_exchange_account: boolean;
  data: {
    controller_config: Record<string, unknown>;
    warnings: string[];
  } | null;
  error: string | null;
  timestamp: string;
}

interface TestnetStartResponse {
  local_record_created: boolean;
  remote_started: boolean;
  remote_confirmed: boolean;
  mode: string;
  testnet: boolean;
  data: {
    testnet_bot_id: string;
    bot_name: string;
    connector: string;
    credentials_profile: string;
    controller_name: string;
    trading_pair: string;
    local_status: string;
    remote_confirmed: boolean;
    local_record_created: boolean;
    remote_started: boolean;
    hummingbot_bot_id: string | null;
    started_at: string;
  } | null;
  error: string | null;
  timestamp: string;
}

interface TestnetBot {
  testnet_bot_id: string;
  bot_name: string;
  connector: string;
  credentials_profile: string;
  controller_name: string;
  trading_pair: string;
  mode: string;
  market_type: string;
  live_trading: boolean;
  testnet: boolean;
  requires_api_key: boolean;
  local_status: string;
  remote_status: string;
  matched_by: string;
  can_fetch_runtime_data: boolean;
  hummingbot_bot_id: string | null;
  started_at: string;
  runtime_seconds: number;
  last_error: string | null;
}

interface TestnetListResponse {
  connected: boolean;
  source: string;
  mode: string;
  data: {
    bots: TestnetBot[];
    last_check_at: string;
  };
  error: string | null;
}

interface FormData {
  bot_name: string;
  connector: string;
  credentials_profile: string;
  controller_name: string;
  trading_pair: string;
  timeframe: string;
  total_amount_quote: number;
  leverage: number;
  position_mode: string;
  bb_length: number;
  bb_std: number;
  bb_long_threshold: number;
  bb_short_threshold: number;
  macd_fast: number;
  macd_slow: number;
  macd_signal: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  cooldown_minutes: number;
  time_limit_minutes: number;
  max_executors_per_side: number;
}

// ── Component ───────────────────────────────────────────────────────────────────

export default function HummingbotTestnetPage() {
  const [status, setStatus] = useState<"loading" | "online" | "offline">("loading");
  const [statusMsg, setStatusMsg] = useState("");

  const [formData, setFormData] = useState<FormData>({
    bot_name: "",
    connector: "binance_perpetual_testnet",
    credentials_profile: "binance_testnet_account",
    controller_name: "bollinger_v1",
    trading_pair: "BTC-USDT",
    timeframe: "15m",
    total_amount_quote: 1000,
    leverage: 1,
    position_mode: "ONEWAY",
    bb_length: 100,
    bb_std: 2.0,
    bb_long_threshold: 0.0,
    bb_short_threshold: 1.0,
    macd_fast: 12,
    macd_slow: 26,
    macd_signal: 9,
    stop_loss_pct: 3.0,
    take_profit_pct: 5.0,
    cooldown_minutes: 5,
    time_limit_minutes: 45,
    max_executors_per_side: 1,
  });

  const [preview, setPreview] = useState<TestnetPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [startResult, setStartResult] = useState<TestnetStartResponse | null>(null);
  const [startLoading, setStartLoading] = useState(false);
  const [botList, setBotList] = useState<TestnetListResponse | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"create" | "list">("create");

  const updateField = useCallback((field: keyof FormData, value: unknown) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  }, []);

  // ── API Calls ──────────────────────────────────────────────────────────────

  const checkStatus = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/hummingbot/status`);
      if (resp.ok) {
        const data = await resp.json();
        setStatus(data.connected ? "online" : "offline");
        setStatusMsg(data.message || "");
      } else {
        setStatus("offline");
      }
    } catch {
      setStatus("offline");
    }
  }, []);

  const fetchPreview = useCallback(async () => {
    setPreviewLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/hummingbot/testnet-bots/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      const data = await resp.json();
      setPreview(data);
    } catch (err) {
      setPreview({
        valid: false, source: "quantagent", mode: "testnet",
        market_type: "perpetual", live_trading: false, testnet: true,
        requires_api_key: true, uses_real_exchange_account: false,
        data: null,
        error: `预览请求失败: ${String(err)}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setPreviewLoading(false);
    }
  }, [formData]);

  const startBot = useCallback(async () => {
    setStartLoading(true);
    setStartResult(null);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/hummingbot/testnet-bots/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      const data = await resp.json();
      setStartResult(data);
      if (data.local_record_created) {
        fetchBotList();
      }
    } catch (err) {
      setStartResult({
        local_record_created: false,
        remote_started: false,
        remote_confirmed: false,
        mode: "testnet",
        testnet: true,
        data: null,
        error: `启动请求失败: ${String(err)}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setStartLoading(false);
    }
  }, [formData]);

  const fetchBotList = useCallback(async () => {
    setListLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/hummingbot/testnet-bots`);
      if (resp.ok) {
        const data = await resp.json();
        setBotList(data);
      }
    } catch { /* ignore */ }
    finally { setListLoading(false); }
  }, []);

  const stopBot = useCallback(async (botId: string) => {
    try {
      await fetch(`${API_BASE}/api/v1/hummingbot/testnet-bots/${botId}/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      fetchBotList();
    } catch { /* ignore */ }
  }, []);

  const copyToClipboard = useCallback((text: string, id: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }, []);

  // ── Effects ───────────────────────────────────────────────────────────────

  useEffect(() => { checkStatus(); }, [checkStatus]);
  useEffect(() => {
    if (activeTab === "list") fetchBotList();
  }, [activeTab, fetchBotList]);

  const statusColor = status === "online" ? "text-green-400" : status === "offline" ? "text-red-400" : "text-yellow-400";
  const StatusIcon = status === "online" ? Wifi : status === "offline" ? WifiOff : RefreshCw;

  const runtimeStr = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  };

  const controllerLabel: Record<string, string> = {
    bollinger_v1: "Bollinger Bands",
    supertrend_v1: "SuperTrend",
    macd_bb_v1: "MACD + Bollinger",
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-6xl mx-auto space-y-6">

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/hummingbot">
              <Button variant="ghost" size="icon" className="text-slate-400 hover:text-slate-100">
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </Link>
            <div>
              <h1 className="text-2xl font-bold text-slate-100">
                Hummingbot — Testnet Perpetual Bot
              </h1>
              <p className="text-sm text-slate-400 mt-1">
                永续合约测试网 Bot · Binance Futures Testnet · 不动真钱
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 ${statusColor} text-sm`}>
              <StatusIcon className="w-4 h-4" />
              <span>
                {status === "loading" ? "检测中..." :
                  status === "online" ? `Hummingbot ${statusMsg}` : "离线"}
              </span>
            </div>
            <Button variant="outline" size="sm" onClick={checkStatus}>
              <RefreshCw className="w-3 h-3 mr-1" /> 刷新
            </Button>
          </div>
        </div>

        {/* ── 风险提示 Banner ───────────────────────────────────────────── */}
        <Card className="border-orange-600 bg-orange-950/40">
          <CardContent className="p-4">
            <div className="flex gap-3">
              <AlertTriangle className="w-5 h-5 text-orange-400 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="text-orange-300 text-sm font-semibold">测试网风险提示</p>
                <div className="text-orange-200/70 text-xs space-y-0.5">
                  <p>• 当前为测试网永续合约 Bot，走 Binance Futures Testnet，不动真钱</p>
                  <p>• <strong>必须填写 Binance Futures Testnet API Key</strong>，禁止填写主网 API Key</p>
                  <p>• API Key 格式示例：<code className="bg-orange-950/60 px-1 rounded">testnet_binance_api_key_here</code></p>
                  <p>• 请在 Hummingbot 中导入 Testnet API Key，凭证名称需匹配表单中的 credentials_profile</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ── Tab 切换 ───────────────────────────────────────────────────── */}
        <div className="flex gap-1 border-b border-slate-800">
          <button
            onClick={() => setActiveTab("create")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "create"
                ? "border-cyan-500 text-cyan-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            创建 Bot
          </button>
          <button
            onClick={() => setActiveTab("list")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "list"
                ? "border-cyan-500 text-cyan-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            Bot 列表
          </button>
        </div>

        {/* ── 创建表单 ───────────────────────────────────────────────────── */}
        {activeTab === "create" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* 左：表单 */}
            <Card className="bg-slate-900/80 border-slate-800">
              <CardHeader className="pb-4">
                <CardTitle className="text-slate-100 text-base flex items-center gap-2">
                  <Bot className="w-4 h-4 text-cyan-400" />
                  Testnet Bot 配置
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">

                {/* Bot 名称 */}
                <div className="space-y-1">
                  <Label htmlFor="bot_name" className="text-slate-300 text-xs">
                    Bot 名称 <span className="text-red-400">*</span>
                  </Label>
                  <Input
                    id="bot_name"
                    value={formData.bot_name}
                    onChange={e => updateField("bot_name", e.target.value)}
                    placeholder="testnet_boll_001"
                    className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
                  />
                </div>

                {/* Connector */}
                <div className="space-y-1">
                  <Label htmlFor="connector" className="text-slate-300 text-xs">
                    Connector <span className="text-red-400">*</span>
                  </Label>
                  <select
                    id="connector"
                    value={formData.connector}
                    onChange={e => updateField("connector", e.target.value)}
                    className="w-full h-9 px-3 bg-slate-800 border border-slate-700 rounded-md text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  >
                    <option value="binance_perpetual_testnet">binance_perpetual_testnet</option>
                    <option value="bybit_perpetual_testnet">bybit_perpetual_testnet</option>
                    <option value="okx_perpetual_testnet">okx_perpetual_testnet</option>
                  </select>
                </div>

                {/* Credentials Profile */}
                <div className="space-y-1">
                  <Label htmlFor="credentials_profile" className="text-slate-300 text-xs">
                    Credentials Profile <span className="text-red-400">*</span>
                  </Label>
                  <select
                    id="credentials_profile"
                    value={formData.credentials_profile}
                    onChange={e => updateField("credentials_profile", e.target.value)}
                    className="w-full h-9 px-3 bg-slate-800 border border-slate-700 rounded-md text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  >
                    <option value="binance_testnet_account">binance_testnet_account</option>
                    <option value="bybit_testnet_account">bybit_testnet_account</option>
                    <option value="okx_testnet_account">okx_testnet_account</option>
                  </select>
                </div>

                {/* Controller */}
                <div className="space-y-1">
                  <Label htmlFor="controller_name" className="text-slate-300 text-xs">
                    Controller <span className="text-red-400">*</span>
                  </Label>
                  <select
                    id="controller_name"
                    value={formData.controller_name}
                    onChange={e => updateField("controller_name", e.target.value)}
                    className="w-full h-9 px-3 bg-slate-800 border border-slate-700 rounded-md text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  >
                    <option value="bollinger_v1">bollinger_v1 (Bollinger Bands)</option>
                    <option value="supertrend_v1">supertrend_v1 (SuperTrend)</option>
                    <option value="macd_bb_v1">macd_bb_v1 (MACD + Bollinger)</option>
                  </select>
                </div>

                {/* Trading Pair + Timeframe */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="trading_pair" className="text-slate-300 text-xs">交易对</Label>
                    <select
                      id="trading_pair"
                      value={formData.trading_pair}
                      onChange={e => updateField("trading_pair", e.target.value)}
                      className="w-full h-9 px-3 bg-slate-800 border border-slate-700 rounded-md text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    >
                      <option value="BTC-USDT">BTC-USDT</option>
                      <option value="ETH-USDT">ETH-USDT</option>
                      <option value="SOL-USDT">SOL-USDT</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="timeframe" className="text-slate-300 text-xs">周期</Label>
                    <select
                      id="timeframe"
                      value={formData.timeframe}
                      onChange={e => updateField("timeframe", e.target.value)}
                      className="w-full h-9 px-3 bg-slate-800 border border-slate-700 rounded-md text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    >
                      <option value="3m">3 分钟</option>
                      <option value="5m">5 分钟</option>
                      <option value="15m">15 分钟</option>
                      <option value="1h">1 小时</option>
                    </select>
                  </div>
                </div>

                {/* 账户参数 */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="total_amount_quote" className="text-slate-300 text-xs">
                      测试网资金 (USDT)
                    </Label>
                    <Input
                      id="total_amount_quote"
                      type="number"
                      min={1}
                      value={formData.total_amount_quote}
                      onChange={e => updateField("total_amount_quote", Number(e.target.value))}
                      className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="leverage" className="text-slate-300 text-xs">杠杆倍数</Label>
                    <select
                      id="leverage"
                      value={formData.leverage}
                      onChange={e => updateField("leverage", Number(e.target.value))}
                      className="w-full h-9 px-3 bg-slate-800 border border-slate-700 rounded-md text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    >
                      {[1,2,3,5,10,20,50,100].map(v => (
                        <option key={v} value={v}>{v}x</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* 风控参数 */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="stop_loss_pct" className="text-slate-300 text-xs">止损 (%)</Label>
                    <Input
                      id="stop_loss_pct"
                      type="number"
                      min={0}
                      max={50}
                      step={0.5}
                      value={formData.stop_loss_pct}
                      onChange={e => updateField("stop_loss_pct", Number(e.target.value))}
                      className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="take_profit_pct" className="text-slate-300 text-xs">止盈 (%)</Label>
                    <Input
                      id="take_profit_pct"
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={formData.take_profit_pct}
                      onChange={e => updateField("take_profit_pct", Number(e.target.value))}
                      className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
                    />
                  </div>
                </div>

                {/* 布林带参数 */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="bb_length" className="text-slate-300 text-xs">BB 周期</Label>
                    <Input
                      id="bb_length"
                      type="number"
                      min={1}
                      value={formData.bb_length}
                      onChange={e => updateField("bb_length", Number(e.target.value))}
                      className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="bb_std" className="text-slate-300 text-xs">BB 标准差</Label>
                    <Input
                      id="bb_std"
                      type="number"
                      min={0.1}
                      max={5}
                      step={0.1}
                      value={formData.bb_std}
                      onChange={e => updateField("bb_std", Number(e.target.value))}
                      className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
                    />
                  </div>
                </div>

                {/* Position Mode + Max Executors */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="position_mode" className="text-slate-300 text-xs">持仓模式</Label>
                    <select
                      id="position_mode"
                      value={formData.position_mode}
                      onChange={e => updateField("position_mode", e.target.value)}
                      className="w-full h-9 px-3 bg-slate-800 border border-slate-700 rounded-md text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    >
                      <option value="ONEWAY">单向（ONEWAY）</option>
                      <option value="HEDGE">双向（HEDGE）</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="max_executors_per_side" className="text-slate-300 text-xs">每侧最大挂单数</Label>
                    <Input
                      id="max_executors_per_side"
                      type="number"
                      min={1}
                      max={10}
                      value={formData.max_executors_per_side}
                      onChange={e => updateField("max_executors_per_side", Number(e.target.value))}
                      className="bg-slate-800 border-slate-700 text-slate-100 text-sm"
                    />
                  </div>
                </div>

                {/* 执行按钮 */}
                <div className="flex gap-3 pt-2">
                  <Button
                    variant="outline"
                    className="flex-1 border-cyan-600 text-cyan-400 hover:bg-cyan-950"
                    onClick={fetchPreview}
                    disabled={previewLoading || !formData.bot_name}
                  >
                    {previewLoading ? (
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <ShieldCheck className="w-4 h-4 mr-2" />
                    )}
                    预览配置
                  </Button>
                  <Button
                    variant="default"
                    className="flex-1 bg-cyan-600 hover:bg-cyan-700 text-white"
                    onClick={startBot}
                    disabled={startLoading || !formData.bot_name || status === "offline"}
                  >
                    {startLoading ? (
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <Play className="w-4 h-4 mr-2" />
                    )}
                    启动 Bot
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* 右：预览 + 启动结果 */}
            <div className="space-y-4">

              {/* 预览结果 */}
              {preview && (
                <Card className={`bg-slate-900/80 border ${
                  preview.valid ? "border-cyan-600" : "border-red-600"
                }`}>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base text-slate-100 flex items-center gap-2">
                      {preview.valid ? (
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      ) : (
                        <XCircle className="w-4 h-4 text-red-400" />
                      )}
                      配置预览
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {preview.valid && preview.data ? (
                      <>
                        <div className="space-y-1">
                          <p className="text-xs text-slate-400">将发送给 Hummingbot 的 Controller Config：</p>
                          <div className="bg-slate-950 rounded-md p-3 text-xs font-mono text-slate-300 max-h-64 overflow-y-auto">
                            <pre className="whitespace-pre-wrap break-all">
                              {JSON.stringify(preview.data.controller_config, null, 2)}
                            </pre>
                          </div>
                          {preview.data.warnings.length > 0 && (
                            <div className="space-y-1">
                              {preview.data.warnings.map((w, i) => (
                                <div key={i} className="flex items-start gap-2 text-xs text-yellow-400">
                                  <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                                  <span>{w}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </>
                    ) : (
                      <div className="text-sm text-red-400 flex items-start gap-2">
                        <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
                        <span>{preview.error || "预览失败"}</span>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* 启动结果 */}
              {startResult && (
                <Card className={`bg-slate-900/80 border ${
                  startResult.remote_confirmed ? "border-green-600" :
                  startResult.remote_started ? "border-yellow-600" : "border-red-600"
                }`}>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base text-slate-100 flex items-center gap-2">
                      {startResult.remote_confirmed ? (
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      ) : (
                        <AlertCircle className="w-4 h-4 text-red-400" />
                      )}
                      启动结果
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {startResult.data && (
                      <>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                          <span className="text-slate-400">Bot 名称：</span>
                          <span className="text-slate-100 font-mono">{startResult.data.bot_name}</span>
                          <span className="text-slate-400">Bot ID：</span>
                          <span className="text-slate-100 font-mono flex items-center gap-1">
                            <span className="truncate max-w-[120px]">{startResult.data.testnet_bot_id}</span>
                            <button
                              onClick={() => copyToClipboard(startResult.data!.testnet_bot_id, startResult.data!.testnet_bot_id)}
                              className="shrink-0 text-slate-500 hover:text-slate-300"
                            >
                              {copiedId === startResult.data!.testnet_bot_id
                                ? <Check className="w-3 h-3 text-green-400" />
                                : <Copy className="w-3 h-3" />}
                            </button>
                          </span>
                          <span className="text-slate-400">Controller：</span>
                          <span className="text-slate-100">
                            {controllerLabel[startResult.data.controller_name] || startResult.data.controller_name}
                          </span>
                          <span className="text-slate-400">Connector：</span>
                          <span className="text-slate-100 font-mono">{startResult.data.connector}</span>
                          <span className="text-slate-400">本地状态：</span>
                          <Badge variant={startResult.data.local_status === "submitted" ? "default" : "destructive"}>
                            {startResult.data.local_status}
                          </Badge>
                          <span className="text-slate-400">远端确认：</span>
                          <Badge variant={startResult.data.remote_confirmed ? "default" : "outline"}>
                            {startResult.data.remote_confirmed ? "running" : "not confirmed"}
                          </Badge>
                          {startResult.data.hummingbot_bot_id && (
                            <>
                              <span className="text-slate-400">Hummingbot ID：</span>
                              <span className="text-slate-100 font-mono">{startResult.data.hummingbot_bot_id}</span>
                            </>
                          )}
                        </div>
                      </>
                    )}
                    {startResult.error && (
                      <div className="text-red-400 text-xs flex items-start gap-2 mt-2">
                        <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
                        <span>{startResult.error}</span>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* 验收说明 */}
              {!startResult && !preview && (
                <Card className="bg-slate-900/80 border-slate-800">
                  <CardContent className="p-4">
                    <div className="text-sm text-slate-400 space-y-2">
                      <p className="text-slate-300 font-medium">验收标准</p>
                      <div className="space-y-1 text-xs">
                        <div className="flex items-start gap-2">
                          <div className="w-4 h-4 rounded border border-slate-600 shrink-0 mt-0.5" />
                          <span>Hummingbot 账户中有对应 testnet credentials profile</span>
                        </div>
                        <div className="flex items-start gap-2">
                          <div className="w-4 h-4 rounded border border-slate-600 shrink-0 mt-0.5" />
                          <span>preview 生成的 payload 无 extra fields 错误</span>
                        </div>
                        <div className="flex items-start gap-2">
                          <div className="w-4 h-4 rounded border border-slate-600 shrink-0 mt-0.5" />
                          <span>active_bots 出现新 Bot</span>
                        </div>
                        <div className="flex items-start gap-2">
                          <div className="w-4 h-4 rounded border border-slate-600 shrink-0 mt-0.5" />
                          <span>QuantAgent remote_status=running</span>
                        </div>
                        <div className="flex items-start gap-2">
                          <div className="w-4 h-4 rounded border border-slate-600 shrink-0 mt-0.5" />
                          <span>can_fetch_runtime_data=true</span>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}

        {/* ── Bot 列表 ───────────────────────────────────────────────────── */}
        {activeTab === "list" && (
          <Card className="bg-slate-900/80 border-slate-800">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-slate-100 text-base">Testnet Bot 列表</CardTitle>
                <Button variant="outline" size="sm" onClick={fetchBotList} disabled={listLoading}>
                  <RefreshCw className={`w-3 h-3 mr-1 ${listLoading ? "animate-spin" : ""}`} />
                  刷新
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {!botList || botList.data.bots.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-sm">
                  <Bot className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  暂无 Testnet Bot，点击「创建 Bot」启动第一个
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="text-left py-2 pr-3 font-medium">名称</th>
                        <th className="text-left py-2 pr-3 font-medium">Controller</th>
                        <th className="text-left py-2 pr-3 font-medium">交易对</th>
                        <th className="text-left py-2 pr-3 font-medium">本地状态</th>
                        <th className="text-left py-2 pr-3 font-medium">远端状态</th>
                        <th className="text-left py-2 pr-3 font-medium">来源</th>
                        <th className="text-left py-2 pr-3 font-medium">运行时长</th>
                        <th className="text-left py-2 font-medium">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {botList.data.bots.map(bot => (
                        <tr key={bot.testnet_bot_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                          <td className="py-2 pr-3">
                            <div className="font-mono text-slate-100">{bot.bot_name}</div>
                          </td>
                          <td className="py-2 pr-3 text-slate-300">
                            {controllerLabel[bot.controller_name] || bot.controller_name}
                          </td>
                          <td className="py-2 pr-3 text-slate-300">{bot.trading_pair}</td>
                          <td className="py-2 pr-3">
                            <Badge
                              variant={bot.local_status === "submitted" ? "default" : "destructive"}
                              className="text-[10px]"
                            >
                              {bot.local_status}
                            </Badge>
                          </td>
                          <td className="py-2 pr-3">
                            <Badge
                              variant={bot.remote_status === "running" ? "default" : "outline"}
                              className={`text-[10px] ${
                                bot.remote_status === "running" ? "bg-green-900 text-green-300 border-green-700" : ""
                              }`}
                            >
                              {bot.remote_status}
                            </Badge>
                          </td>
                          <td className="py-2 pr-3 text-slate-400">{bot.matched_by}</td>
                          <td className="py-2 pr-3 text-slate-400">{runtimeStr(bot.runtime_seconds)}</td>
                          <td className="py-2">
                            {bot.remote_status === "running" || bot.local_status === "submitted" ? (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-6 text-[10px] border-red-700 text-red-400 hover:bg-red-950"
                                onClick={() => stopBot(bot.testnet_bot_id)}
                              >
                                停止
                              </Button>
                            ) : (
                              <span className="text-slate-600 text-[10px]">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
