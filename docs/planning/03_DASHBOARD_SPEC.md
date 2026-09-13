# Dashboard / Frontend Spec

## Purpose

Judges cannot log into Google Sheets, Notion, or Supabase — they only get
a public URL. This page exists SOLELY to make that real backend activity
visible to someone who can't otherwise see it. It is a window, not the
system itself. The real integration is n8n writing directly to Notion and
Google Sheets (see `02_TECHNICAL_SPEC.md`, Path A) — the dashboard just
mirrors that via a Supabase echo (Path B) so judges aren't asked to trust
it on faith. Keep this framing explicit in the README and in the demo: the
dashboard is a convenience for judges, not where the actual work happens.

## Layout (single page, deployed on Vercel via Next.js)

**Left panel — the chat widget**
- A simple, clean chat UI simulating the storefront's customer support
  chat. This is what the judge actually interacts with.
- Sends messages to the n8n webhook, streams/displays the response.
- Include 2-3 suggested prompt chips (e.g. "Do you have the blue hoodie
  in stock?", "What's your return policy?") so judges who don't know what
  to type can get started immediately.

**Top-right panel — live inventory view**
- A read-only table mirroring the Google Sheet: product name, and a
  simple status indicator (Available / Limited / Pending team review) —
  NOT the raw stock/pending numbers, consistent with the agent's own
  information boundary. Showing raw numbers here while the agent refuses
  to say them out loud would undercut the guardrail story.
- Updates via the Supabase Realtime subscription (see
  `02_TECHNICAL_SPEC.md`) — should visibly change within a second or two
  of an action happening in chat.

**Bottom-right panel — live order feed**
- A read-only list of recent order records mirrored from Notion (customer
  name, product, qty, status badge: Pending/Fulfilled).
- Also updates via the same Supabase Realtime subscription.
- This is what makes the "someone marks it Fulfilled in Notion → this
  page updates automatically" moment visible without judges ever opening
  Notion.

**Small "system trace" strip (optional, high value if time allows)**
- A thin collapsible panel showing which subagent/tool fired for the last
  message (e.g. `check_inventory → not available → capture_order`). This
  directly demonstrates the orchestrator/subagent architecture to judges
  who won't read your n8n canvas.

## Technical notes

- Keep the frontend thin: it should not contain business logic. All
  decisions happen in n8n. The frontend only renders chat + subscribes to
  Supabase Realtime + displays state.
- Use Supabase's JS client directly in the Next.js app for the Realtime
  subscription — no need to proxy it through n8n.
- Make sure the chat widget clearly shows loading/typing state while
  waiting on the n8n webhook response, since a few seconds of latency is
  expected (RAG + tool calls take real time) and an unstyled blank wait
  reads as broken.
- Mobile responsiveness is not a priority — judges will view this on
  desktop during the judging window.
