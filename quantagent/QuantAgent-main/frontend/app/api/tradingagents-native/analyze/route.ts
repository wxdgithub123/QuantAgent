export const dynamic = "force-dynamic";
export const maxDuration = 600;

function serviceUrlCandidates() {
  const configured = process.env.TRADINGAGENTS_SERVICE_URL || "http://tradingagents-service:8010";
  return Array.from(
    new Set([
      configured.replace(/\/$/, ""),
      "http://tradingagents-service:8010",
      "http://localhost:8010",
      "http://127.0.0.1:8010",
    ])
  );
}

async function postNativeAnalyze(serviceUrl: string, bodyText: string) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 540_000);
  try {
    return await fetch(`${serviceUrl}/native/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: bodyText,
      cache: "no-store",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

export async function POST(request: Request) {
  const body = await request.json();
  const bodyText = JSON.stringify(body);
  const failures: string[] = [];

  for (const serviceUrl of serviceUrlCandidates()) {
    try {
      const upstream = await postNativeAnalyze(serviceUrl, bodyText);
      const text = await upstream.text();
      return new Response(text, {
        status: upstream.status,
        headers: {
          "Content-Type": upstream.headers.get("Content-Type") || "application/json",
        },
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      failures.push(`${serviceUrl}: ${message}`);
    }
  }

  return Response.json(
    {
      status: "error",
      error: `原版 TradingAgentsGraph 服务暂时无法连接。已尝试：${failures.join("；")}`,
    },
    { status: 502 }
  );
}
