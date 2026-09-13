// Demo reset (key-protected): asks the n8n workflow to restore the Sheet seed, archive Notion orders
// and clear the dashboard echo tables. The admin token never reaches the browser.
export const maxDuration = 60;

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const expected = process.env.DEMO_RESET_KEY;
  if (!expected || body?.key !== expected) {
    return Response.json({ ok: false, error: "Invalid reset key" }, { status: 401 });
  }
  try {
    const res = await fetch(process.env.N8N_ADMIN_WEBHOOK_URL as string, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": process.env.N8N_ADMIN_TOKEN as string },
      body: JSON.stringify({ action: "reset" }),
      signal: AbortSignal.timeout(55000),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data?.ok) throw new Error(`n8n responded ${res.status}`);
    return Response.json({ ok: true, archived_orders: data.archived_orders ?? 0 });
  } catch (err) {
    return Response.json({ ok: false, error: err instanceof Error ? err.message : "reset failed" }, { status: 502 });
  }
}
