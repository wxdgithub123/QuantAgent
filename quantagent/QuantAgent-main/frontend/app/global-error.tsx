"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("QuantAgent global error:", error);
  }, [error]);

  return (
    <html lang="zh-CN" className="dark">
      <body className="bg-[#071019] text-slate-100">
        <main className="flex min-h-screen items-center justify-center px-4 py-10">
          <section className="max-w-3xl rounded-3xl border border-amber-400/25 bg-amber-500/10 p-6 shadow-2xl">
            <p className="text-sm font-semibold text-amber-100">系统页面异常</p>
            <h1 className="mt-3 text-2xl font-semibold text-white">
              页面加载时出现临时异常
            </h1>
            <p className="mt-3 text-sm leading-7 text-slate-300">
              这里替代 Next.js 默认的英文 Application error。请先重新加载页面；如果仍然出现，
              我们可以继续根据控制台日志定位具体组件。当前系统不会因此产生真实订单。
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={reset}
                className="rounded-xl border border-cyan-400/25 bg-cyan-500/15 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:bg-cyan-500/25"
              >
                重新加载
              </button>
              <button
                type="button"
                onClick={() => {
                  window.location.href = "/";
                }}
                className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-100 transition hover:bg-white/10"
              >
                回到演示首页
              </button>
            </div>
            {error.digest && (
              <p className="mt-4 font-mono text-xs text-slate-500">error digest: {error.digest}</p>
            )}
          </section>
        </main>
      </body>
    </html>
  );
}
