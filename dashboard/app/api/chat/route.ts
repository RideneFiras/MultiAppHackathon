// Thin proxy to the n8n chat webhook: avoids CORS and keeps the webhook token server-side.
// No business logic here: every decision happens in n8n.
export const maxDuration = 60;

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const message = typeof body?.message === "string" ? body.message.slice(0, 2000) : "";
  const sessionId = typeof body?.session_id === "string" ? body.session_id.slice(0, 64) : "";
  if (!message.trim() || !sessionId) {
    return Response.json({ error: "session_id and message are required" }, { status: 400 });
  }

  try {
    const res = await fetch(process.env.N8N_CHAT_WEBHOOK_URL as string, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Chat-Token": process.env.N8N_CHAT_TOKEN as string },
      body: JSON.stringify({ session_id: sessionId, message }),
      signal: AbortSignal.timeout(55000),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data) throw new Error(`n8n responded ${res.status}`);
    return Response.json(data);
  } catch (err) {
    return Response.json({
      intent: "faq",
      reply_text: "Sorry, the assistant is unavailable right now. Please try again in a moment.",
      tool_calls_made: [],
      path: `proxy error: ${err instanceof Error ? err.message : "unknown"}`,
    });
  }
}
