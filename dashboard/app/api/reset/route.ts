// Public demo reset (no key, so anyone testing can start over). The n8n workflow archives the demo orders in
// Notion, releases the units they reserved in the Google Sheet (stock is never overwritten) and clears the
// dashboard feed. The admin token stays server-side and this route can only trigger that one action.
export const maxDuration = 60;

export async function POST() {
  try {
    const res = await fetch(process.env.N8N_ADMIN_WEBHOOK_URL as string, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": process.env.N8N_ADMIN_TOKEN as string },
      body: JSON.stringify({ action: "reset" }),
      signal: AbortSignal.timeout(55000),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data?.ok) throw new Error(`n8n responded ${res.status}`);
    return Response.json({ ok: true, archived_orders: data.archived_orders ?? 0, released_units: data.released_units ?? 0 });
  } catch (err) {
    return Response.json({ ok: false, error: err instanceof Error ? err.message : "reset failed" }, { status: 502 });
  }
}
