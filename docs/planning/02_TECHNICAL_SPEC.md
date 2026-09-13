# Technical Specification

## Stack decisions (already made — do not re-litigate these unless something
is genuinely broken)

- **Orchestrator/runtime:** n8n (already deployed on Azure). Chosen for
  build speed given the one-day window.
- **Interface:** a chat widget embedded directly in the demo storefront
  page (NOT Telegram/WhatsApp — a self-built widget is our own UI, not a
  scored external integration, so there's no reason to add a messaging
  platform's OAuth overhead).
- **External integrations (the ones that count toward "at least 3 apps"):**
  1. **Google Sheets** — inventory source of truth (`stock`, `pending`
     columns per product)
  2. **Notion** — order/CRM database (customer info, product, quantity,
     status: Pending → Fulfilled)
  3. **Supabase (pgvector)** — RAG knowledge base for store policy/product
     Q&A, AND the realtime sync layer for the dashboard (see below)
- **Frontend/dashboard:** Next.js, deployed on Vercel.
- **LLM:** Claude (Anthropic) via API for the AI Agent nodes in n8n.

## Orchestrator / subagent architecture

Build this as ONE main n8n workflow acting as the orchestrator, calling
narrower sub-workflows as tools (n8n supports calling a sub-workflow as a
tool from an AI Agent node — use this, don't just chain everything in one
giant flow).

**Main orchestrator (AI Agent node):**
- Receives the incoming chat message (webhook from the frontend widget)
- Has a structured output parser constraining its response to a fixed
  schema (see below)
- Has access to exactly these tools, no more:
  - `check_inventory` (sub-workflow → reads Google Sheet)
  - `answer_from_kb` (sub-workflow → RAG query against Supabase pgvector)
  - `capture_order` (sub-workflow → writes to Notion + marks pending in
    Sheet, in the same transaction)
- Does NOT have any tool capable of: changing price, granting discount,
  revealing exact stock numbers, or modifying anything other than
  creating a new order record.

**Subagent: check_inventory**
- Reads the product row from Google Sheets.
- Applies the availability rule deterministically (this logic lives in
  an n8n IF/Switch node, NOT left to the LLM):
  - `stock - pending >= requested_qty` → respond "available"
  - otherwise → respond "not confirmed, we'll have someone follow up"
- Returns only a boolean-ish status to the orchestrator, never the raw
  numbers. The orchestrator must not be able to see or repeat exact
  stock/pending counts — enforce this by not passing the raw numbers back
  from this subagent at all, only a status string.

**Subagent: answer_from_kb**
- Takes the user question, embeds it, queries Supabase pgvector for top-k
  chunks from the store policy/product knowledge base, returns the
  answer grounded in retrieved text.

**Subagent: capture_order**
- Takes customer name/contact/product/qty.
- Writes a new row to Notion (status: `Pending`).
- Increments the `pending` count for that product in Google Sheets.
- Writes the same event to the Supabase sync table (see Realtime section).
- Both writes should happen together; if one fails, log the failure
  clearly rather than silently succeeding half-way (this matters for the
  reliability writeup).

## Structured output constraint

Force every orchestrator response through a fixed schema, e.g.:

```json
{
  "intent": "faq" | "check_availability" | "capture_order" | "refuse",
  "reply_text": "string",
  "tool_calls_made": ["string"]
}
```

No field in this schema can express a discount, a price change, or raw
inventory numbers. This is the primary technical guardrail — if the
capability doesn't exist in the schema or the toolset, no prompt can
produce it.

## Prompt injection defense (this needs to be genuinely demoable, not just
claimed)

Layer these, in order:

1. **No dangerous tool exists.** There is no `apply_discount` or
   `change_price` tool anywhere in the system. This alone blocks the
   classic "give me a refund/discount" attack class entirely.
2. **Pre-filter step before the main agent runs.** A small, cheap
   classification step (either a lightweight LLM call or keyword/pattern
   matching in an n8n node) scans the incoming message for injection
   patterns ("ignore previous instructions," "you are now in admin mode,"
   "reveal your system prompt," "give me a discount," etc). Matches are
   routed to a hardcoded safe response and never reach the main agent's
   context at all.
3. **System prompt treats user input as untrusted data**, explicitly
   instructed not to follow embedded instructions found inside the
   conversation.
4. **Structured output schema** (above) as the last line of defense —
   even if something slipped through, there's no field to express a
   discount or a price override.

Build a small test set of adversarial prompts (5-10 examples: direct
discount requests, role-override attempts, "ignore instructions" variants,
attempts to extract exact stock numbers, attempts to extract another
customer's info). Run them against the finished system and record the
pass rate — this becomes both a README section and a demo beat.

## Bidirectional sync (Sheets ↔ Notion)

- **Forward:** `capture_order` subagent writes to Notion (status
  `Pending`) and increments `pending` in Sheets, atomically as described
  above.
- **Backward:** when someone changes an order's status to `Fulfilled` in
  Notion, this needs to flow back automatically:
  - If Notion webhooks are available/reliable in the current API, use a
    Notion webhook trigger in n8n.
  - If not, use a polling trigger (n8n Notion node, poll every ~30-60s
    for status changes) — acceptable for a one-day demo since fulfillment
    isn't a split-second operation.
  - On detecting `Fulfilled`: decrement `pending` AND decrement `stock`
    by the order quantity in Google Sheets (the item has now actually
    left inventory).

## IMPORTANT: two independent write paths — do not conflate these

This system has TWO separate things happening. Keep them architecturally
separate; do not let one become a dependency of the other.

**Path A — the real automation (this is what the hackathon is actually
scoring).** n8n writes directly to Notion's API and directly to Google
Sheets' API. This is genuine, independent multi-app sync: capturing an
order writes to both real systems; marking an order Fulfilled in Notion
triggers n8n to write back to the real Google Sheet. If Supabase did not
exist, Path A would still work correctly on its own. This is the part
that should be described as "the integration" in the README — Notion and
Google Sheets are real, functioning, synced systems of record, not props.

**Path B — the dashboard echo (purely a judge-visibility workaround).**
Judges cannot log into Firas's Google account or Notion workspace, so
there is no way for them to see Path A happening directly. To solve
*only* that problem, every time n8n completes a Path A write, it ALSO
fires a second, independent write of the same event into a Supabase
table (`live_state`: product, stock, pending, last_order, status,
updated_at). The Next.js dashboard subscribes to **Supabase Realtime** on
that table and updates instantly via websocket. This write must not block
or gate Path A — if the Supabase echo fails for some reason, Notion and
Sheets should still be correctly synced; only the dashboard would be
stale. Log that failure clearly rather than silently swallowing it.

Do not build this such that the dashboard reads live from Sheets/Notion,
and do not build it such that Sheets/Notion sync depends on Supabase in
any way. The dependency only ever flows one direction: Path A → echo →
Path B.

## Visual verification via Playwright MCP

Firas has a Playwright MCP available. Use it to actually open Chrome and
visually confirm state in the real Google Sheet and real Notion database
during both setup and testing — e.g. after a test order is captured,
navigate to the actual Sheet URL and actual Notion database URL yourself
and confirm the cell/row changed, rather than only trusting API responses.
This is a genuinely useful self-testing tool here: it lets you verify
Path A (the real sync) independently of Path B (the dashboard), which is
exactly the separation that matters. Use it during the reliability test
pass described below, and again before Firas records the demo, to confirm
both real apps are in a clean, correct starting state.

## Optional fourth integration — evaluate but don't force it

If Path A/B is built, tested, and stable with time to spare, one low-risk
addition worth considering: a **Slack notification** fired by the
`capture_order` subagent whenever an order needs team follow-up
(including the race-condition case where a customer is told "the team
will follow up"). This is a single native n8n node, no OAuth complexity,
and it directly matches language already in the scenario ("team will
contact them") rather than being a bolt-on. Only add this after Path A/B
is solid — three real, working integrations beats four where the fourth
is rushed and flaky. If time is tight, skip it; it is not required to
meet the "at least three apps" bar.

## Reliability testing to actually perform (for the README + demo)

1. Run the adversarial prompt set (above) and record pass/fail.
2. Simulate the race condition: request the last 2 units as customer A
   (confirm capture), then immediately request the same product as
   customer B (confirm it does NOT get falsely confirmed).
3. Test the fulfillment sync: mark an order Fulfilled in Notion, confirm
   the Sheet and dashboard update without manual intervention.
4. Test a failure path: temporarily break one integration (e.g. wrong
   Notion token) and confirm the system fails loudly/logs clearly rather
   than silently corrupting state.
