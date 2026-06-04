"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("QuantAgent page error:", error);
  }, [error]);

  return (
    <main className="min-h-screen bg-[#071019] px-4 py-10 text-slate-100">
      <section className="mx-auto max-w-3xl rounded-3xl border border-amber-400/25 bg-amber-500/10 p-6 shadow-2xl">
        <p className="text-sm font-semibold text-amber-100">页面状态异常</p>
        <h1 className="mt-3 text-2xl font-semibold text-white">当前页面加载时出现了临时异常</h1>
        <p className="mt-3 text-sm leading-7 text-slate-300">
          这通常是开发服务热更新、接口短暂超时或页面状态未初始化导致的。系统没有执行真实交易，
          可以先重新加载；如果继续出现，我们再根据控制台日志定位具体组件。
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={reset}
            className="rounded-xl border border-cyan-400/25 bg-cyan-500/15 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:bg-cyan-500/25"
          >
            重新加载当前页面
          </button>
          <Link
            href="/"
            className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-100 transition hover:bg-white/10"
          >
            回到演示首页
          </Link>
        </div>
        {error.digest && (
          <p className="mt-4 font-mono text-xs text-slate-500">error digest: {error.digest}</p>
        )}
      </section>
    </main>
  );
}
