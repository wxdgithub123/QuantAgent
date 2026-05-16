"use client";

import { useEffect, useRef, useCallback, useState } from "react";

// ─── Shared message payload types ───────────────────────────────────────────

export type BotLocalStatus = "pending" | "running" | "stopping" | "stopped";
export type BotRemoteStatus = "pending" | "running" | "deployed" | "not_detected" | "stopped";
export type OrderSide = "BUY" | "SELL";
export type PositionSide = "LONG" | "SHORT";
export type ErrorLevel = "error" | "warning" | "info";

export interface BotStatusUpdate {
  paper_bot_id: string;
  local_status: BotLocalStatus;
  remote_status: BotRemoteStatus;
  runtime_seconds?: number;
  event?: string;
  message?: string;
  error_message?: string;
}

export interface OrderUpdate {
  order_id: string;
  symbol: string;
  side: OrderSide;
  status: string;
  price: number;
  quantity: number;
  filled: number;
}

export interface PositionUpdate {
  symbol: string;
  side: PositionSide;
  quantity: number;
  avg_price: number;
  unrealized_pnl: number;
}

export interface PortfolioUpdate {
  source: "hummingbot" | "local";
  paper_bot_id: string;
  total_equity: number;
  cash_balance: number;
  position_value: number;
  pnl: number;
  pnl_pct: number;
}

export interface HeartbeatMessage {
  type: "heartbeat";
  timestamp: string;
}

// ─── WebSocket message union ────────────────────────────────────────────────

export type WebSocketMessage =
  | { type: "bot_status_update"; data: BotStatusUpdate }
  | { type: "orders_update"; data: OrderUpdate[] }
  | { type: "positions_update"; data: PositionUpdate[] }
  | { type: "portfolio_update"; data: PortfolioUpdate }
  | HeartbeatMessage;

// ─── Hook options ───────────────────────────────────────────────────────────

interface UsePaperBotWebSocketOptions {
  paperBotId?: string;
  onStatusUpdate?: (status: BotStatusUpdate) => void;
  onOrdersUpdate?: (orders: OrderUpdate[]) => void;
  onPositionsUpdate?: (positions: PositionUpdate[]) => void;
  onPortfolioUpdate?: (portfolio: PortfolioUpdate) => void;
  reconnectInterval?: number;
  enabled?: boolean;
}

export function usePaperBotWebSocket({
  paperBotId,
  onStatusUpdate,
  onOrdersUpdate,
  onPositionsUpdate,
  onPortfolioUpdate,
  reconnectInterval = 3000,
  enabled = true,
}: UsePaperBotWebSocketOptions = {}) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const [isConnected, setIsConnected] = useState(false);
  const [lastHeartbeat, setLastHeartbeat] = useState<Date | null>(null);

  const connect = useCallback(() => {
    if (!enabled) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${
      window.location.host
    }/ws/paper-bots${paperBotId ? `/${paperBotId}` : ""}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        clearTimeout(reconnectTimerRef.current);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          switch (message.type) {
            case "bot_status_update":
              onStatusUpdate?.(message.data);
              break;
            case "orders_update":
              onOrdersUpdate?.(message.data);
              break;
            case "positions_update":
              onPositionsUpdate?.(message.data);
              break;
            case "portfolio_update":
              onPortfolioUpdate?.(message.data);
              break;
            case "heartbeat":
              setLastHeartbeat(new Date());
              break;
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onerror = () => {
        setIsConnected(false);
      };

      ws.onclose = () => {
        setIsConnected(false);
        // Auto reconnect
        reconnectTimerRef.current = setTimeout(connect, reconnectInterval);
      };
    } catch {
      reconnectTimerRef.current = setTimeout(connect, reconnectInterval);
    }
  }, [paperBotId, onStatusUpdate, onOrdersUpdate, onPositionsUpdate, onPortfolioUpdate, reconnectInterval, enabled]);

  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimerRef.current);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const send = useCallback((message: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      disconnect();
      return;
    }
    connect();
    return () => disconnect();
  }, [connect, disconnect, enabled]);

  return {
    isConnected,
    lastHeartbeat,
    send,
    disconnect,
    reconnect: connect,
  };
}
