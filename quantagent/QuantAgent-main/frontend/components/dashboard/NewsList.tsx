"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { Newspaper, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";

interface NewsArticle {
  title: string;
  source: string;
  url: string;
  date: string;
  summary?: string;
  symbol?: string;
  sentiment?: "positive" | "negative" | "neutral";
}

interface NewsListProps {
  symbol: string;
}

const SENTIMENT_CONFIG = {
  positive: { label: "正面", className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
  negative: { label: "负面", className: "bg-red-500/10 text-red-400 border-red-500/20" },
  neutral: { label: "中性", className: "bg-muted text-muted-foreground border-border" },
};

// Simple heuristic sentiment detection
function guessSentiment(title: string): "positive" | "negative" | "neutral" {
  const lower = title.toLowerCase();
  const positive = ["surge", "rally", "bull", "gain", "rise", "high", "green", "record", "breakout", "boost", "upgrade"];
  const negative = ["crash", "drop", "bear", "fall", "low", "red", "loss", "decline", "liquidat", "ban", "downgrade", "risk", "warning"];
  if (positive.some((w) => lower.includes(w))) return "positive";
  if (negative.some((w) => lower.includes(w))) return "negative";
  return "neutral";
}

export function NewsList({ symbol }: NewsListProps) {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const baseSymbol = symbol.replace("USDT", "");
        const response = await fetch(`/api/v1/market/news?symbol=${baseSymbol}&limit=10`);
        const data = await response.json();
        if (cancelled) return;
        const raw = data.articles || [];
        setArticles(raw.map((a: NewsArticle) => ({
          ...a,
          sentiment: a.sentiment || guessSentiment(a.title),
        })));
      } catch {
        if (!cancelled) setArticles([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [symbol]);

  return (
    <Card className="border-border bg-card h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-foreground flex items-center gap-2">
          <Newspaper className="w-4 h-4 text-purple-400" />
          新闻
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="space-y-1.5">
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-2 w-1/2" />
              </div>
            ))}
          </div>
        ) : articles.length === 0 ? (
          <div className="py-8 text-center">
            <Newspaper className="w-8 h-8 mx-auto mb-2 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">暂无相关新闻</p>
            <p className="text-[10px] text-muted-foreground/60 mt-1">新闻数据需要 L1 管线拉取</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[460px] overflow-y-auto">
            {articles.map((a, idx) => {
              const isExpanded = expandedIdx === idx;
              const sentiment = SENTIMENT_CONFIG[a.sentiment || "neutral"];

              return (
                <div
                  key={idx}
                  className="rounded-lg border border-border/50 bg-secondary/20 p-2.5 hover:border-border transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div
                      className="flex-1 min-w-0 cursor-pointer"
                      onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                    >
                      <p className="text-xs leading-5 text-foreground/90 line-clamp-2">{a.title}</p>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className="text-[10px] text-muted-foreground">{a.source}</span>
                        <span className="text-[10px] text-muted-foreground/60">
                          {a.date ? new Date(a.date).toLocaleDateString("zh-CN") : ""}
                        </span>
                        <Badge className={cn("text-[9px] px-1 py-0", sentiment.className)}>
                          {sentiment.label}
                        </Badge>
                      </div>
                      {isExpanded && a.summary && (
                        <p className="mt-2 text-[11px] text-muted-foreground leading-5">{a.summary}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {a.url && (
                        <a
                          href={a.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-muted-foreground hover:text-foreground transition-colors"
                        >
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                      <button
                        onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                        className="text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
