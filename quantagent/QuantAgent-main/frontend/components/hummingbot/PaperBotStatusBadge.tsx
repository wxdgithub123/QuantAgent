"use client";

import { Badge } from "@/components/ui/badge";
import { PaperBot } from "./PaperBotList";

interface PaperBotStatusBadgeProps {
  localStatus: string;
  remoteStatus: string;
  size?: "sm" | "md";
}

const STATUS_CONFIG: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline"; className: string }> = {
  running: {
    label: "运行中",
    variant: "default",
    className: "bg-green-500/15 text-green-400 border-green-500/30",
  },
  submitted: {
    label: "已提交",
    variant: "secondary",
    className: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  },
  start_failed: {
    label: "启动失败",
    variant: "destructive",
    className: "bg-red-500/15 text-red-400 border-red-500/30",
  },
  stopped: {
    label: "已停止",
    variant: "secondary",
    className: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  },
  unknown: {
    label: "未知",
    variant: "outline",
    className: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  },
  not_detected: {
    label: "未检测到",
    variant: "outline",
    className: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  },
};

const REMOTE_STATUS_CONFIG: Record<string, { label: string; dotColor: string }> = {
  running: { label: "远端运行", dotColor: "bg-green-400" },
  stopped: { label: "远端停止", dotColor: "bg-slate-400" },
  not_detected: { label: "未检测", dotColor: "bg-amber-400" },
  unknown: { label: "未知", dotColor: "bg-slate-500" },
};

export function PaperBotStatusBadge({ localStatus, remoteStatus, size = "md" }: PaperBotStatusBadgeProps) {
  const config = STATUS_CONFIG[localStatus] || STATUS_CONFIG.unknown;
  const remoteConfig = REMOTE_STATUS_CONFIG[remoteStatus] || REMOTE_STATUS_CONFIG.unknown;
  const textSize = size === "sm" ? "text-[10px]" : "text-xs";
  const padding = size === "sm" ? "px-1.5 py-0" : "px-2 py-0.5";

  return (
    <div className="flex items-center gap-2">
      <Badge
        variant={config.variant}
        className={`${padding} ${textSize} border ${config.className}`}
      >
        {config.label}
      </Badge>
      <div className="flex items-center gap-1">
        <div className={`w-1.5 h-1.5 rounded-full ${remoteConfig.dotColor}`} />
        <span className={`text-slate-500 ${textSize}`}>{remoteConfig.label}</span>
      </div>
    </div>
  );
}
