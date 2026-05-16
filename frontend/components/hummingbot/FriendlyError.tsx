"use client";

import { AlertTriangle, FileText, Lightbulb, ChevronDown, ChevronUp, Copy, CheckCircle, Info } from "lucide-react";
import { useState } from "react";

type ErrorLevel = "error" | "warning" | "info";

interface FriendlyErrorProps {
  error: {
    code?: string;
    short?: string;
    detail?: string;
    action?: string;
    doc_url?: string;
    context?: Record<string, unknown>;
    raw_message?: string;
    quality_warnings?: string[];
    level?: ErrorLevel;
  };
  showRaw?: boolean;
}

const LEVEL_STYLES: Record<ErrorLevel, { bg: string; border: string; icon: typeof AlertTriangle; iconColor: string; textColor: string }> = {
  error: {
    bg: "bg-red-500/10",
    border: "border-red-500/20",
    icon: AlertTriangle,
    iconColor: "text-red-400",
    textColor: "text-red-300",
  },
  warning: {
    bg: "bg-amber-500/10",
    border: "border-amber-500/20",
    icon: AlertTriangle,
    iconColor: "text-amber-400",
    textColor: "text-amber-300",
  },
  info: {
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
    icon: Info,
    iconColor: "text-blue-400",
    textColor: "text-blue-300",
  },
};

export function FriendlyError({ error, showRaw = false }: FriendlyErrorProps) {
  const [expanded, setExpanded] = useState(false);
  const [showRawMessage, setShowRawMessage] = useState(showRaw);
  const [copied, setCopied] = useState(false);

  if (!error || !error.short) return null;

  const level: ErrorLevel = error.level ?? "error";
  const style = LEVEL_STYLES[level];
  const Icon = style.icon;

  const rawToCopy = error.raw_message ?? JSON.stringify(error, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(rawToCopy).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="space-y-2">
      {/* Main error alert */}
      <div className={`p-4 ${style.bg} border ${style.border} rounded-lg`}>
        <div className="flex items-start gap-3">
          <Icon className={`w-5 h-5 ${style.iconColor} mt-0.5 shrink-0`} />
          <div className="flex-1 min-w-0">
            <p className={`${style.textColor} font-semibold text-sm`}>{error.short}</p>
            {error.detail && (
              <p className="text-slate-400 text-xs mt-1">{error.detail}</p>
            )}
          </div>
        </div>
      </div>

      {/* Suggested action */}
      {error.action && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
          <div className="flex items-start gap-2">
            <Lightbulb className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
            <div>
              <p className="text-amber-300 text-xs font-semibold mb-1">建议操作</p>
              <pre className="text-amber-200/80 text-xs whitespace-pre-wrap font-sans">
                {error.action}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Documentation & copy action row */}
      <div className="flex items-center gap-3 flex-wrap">
        {error.doc_url && (
          <a
            href={error.doc_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 text-xs underline"
          >
            <FileText className="w-3.5 h-3.5" />
            查看文档
          </a>
        )}
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-slate-400 hover:text-slate-300 text-xs transition-colors"
        >
          {copied ? (
            <>
              <CheckCircle className="w-3.5 h-3.5 text-green-400" />
              <span className="text-green-400">已复制</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              复制错误信息
            </>
          )}
        </button>
      </div>

      {/* Quality warnings */}
      {error.quality_warnings && error.quality_warnings.length > 0 && (
        <div className="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
          <p className="text-yellow-300 text-xs font-semibold mb-1">回测质量警告</p>
          <ul className="space-y-1">
            {error.quality_warnings.map((warning, i) => (
              <li key={i} className="text-yellow-200/80 text-xs flex items-start gap-1">
                <span className="text-yellow-400 mt-0.5">•</span>
                {warning}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Expandable raw message */}
      {error.raw_message && (
        <div className="border border-slate-700/50 rounded-lg overflow-hidden">
          <button
            onClick={() => setShowRawMessage(!showRawMessage)}
            className="w-full flex items-center justify-between px-3 py-2 bg-slate-800/50 hover:bg-slate-800 transition-colors"
          >
            <span className="text-slate-400 text-xs">原始错误信息</span>
            {showRawMessage ? (
              <ChevronUp className="w-3.5 h-3.5 text-slate-500" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
            )}
          </button>
          {showRawMessage && (
            <pre className="px-3 py-2 text-slate-300 text-xs font-mono max-h-48 overflow-auto whitespace-pre-wrap">
              {error.raw_message}
            </pre>
          )}
        </div>
      )}

      {/* Error code */}
      {error.code && error.code !== "unknown" && (
        <p className="text-slate-600 text-[10px] font-mono">
          错误代码: {error.code}
        </p>
      )}
    </div>
  );
}
