# Project Context

## Who's building this

Firas Ridene — AI engineer, Tunis. Currently freelancing as lead engineer on
a B2B AI sales outreach SaaS (Python/FastAPI/Next.js/TypeScript/Postgres/
Claude/Stripe stack). Background includes CrewAI multi-agent systems,
n8n automation pipelines, voice agents (VocaFlow), and MLOps work. Works
fast, prioritizes shipping working systems over polish, is comfortable
directing an AI coding agent autonomously and reviewing/correcting rather
than writing every line by hand. Portfolio: firasridene.tech.

Working style for this project: Firas wants you (Claude Code) to run with
**full autonomy** after the initial setup-verification pass — he will give
you a single `/goal` prompt (see `05_GOAL_PROMPT.md`) and expects you to
build, test yourself, and iterate until the thing works, checking in only
when you hit something you genuinely can't resolve alone.

## The hackathon

**Multi-App AI Agent Hackathon** — one-day virtual event, Sept 13 2026,
9AM-5PM Pacific. Hosted by Lemma and Comma Capital, judged by founders of
Arga Labs and Userlens. $15,000 total prizes ($10k/$4k/$1k). Top 3 teams
get guaranteed interviews with Arga Labs or Lemma AI.

**The brief:** Build one useful, multi-step AI agent. Connect it to at
least three external apps. Show how you know it works. Submission = working
project/repo, a 2-minute demo, a short system/reliability brief, README.

**Preferences stated by organizers (not hard requirements, but scored):**
- Real economic work — genuinely useful / time-saving, not necessarily
  "financial" in subject matter
- External integrations that preferably work together
- Deployed and testable by judges directly (they will NOT have accounts
  on any of the backend apps — they can only interact with a public URL)
- README must state: what was built, which external apps were used, and
  how reliability was tested
- 2-minute demo linked from the README
- Preferably a main orchestrator agent with subagents underneath it

**Judging weights:**
- Technical execution — 30%
- Reliability & evaluation — 25%
- Usefulness — 20%
- Originality — 15%
- Demo clarity — 10%

Firas is solo (team of one).

## The scenario

**AI customer service agent for an e-commerce store**, with real inventory
consequences, not just a FAQ bot.

A visitor chats with the store's support agent on a demo storefront page.
The agent can:

1. **Answer store/product/policy questions** via RAG over a small knowledge
   base (shipping policy, return policy, product descriptions, etc).
2. **Check product availability.** Availability is backed by a real
   "inventory" spreadsheet (Google Sheets) that has both a `stock` count
   and a `pending` count per product. The agent will confirm availability
   in general terms but will **never reveal exact stock numbers** — this
   is a deliberate information-boundary rule, not just a style choice.
3. **Handle the race condition on purchase intent.** If a customer wants
   to buy, say, 2 units of a product that has exactly 2 in stock and 0
   pending, the agent collects their info and marks 2 as `pending`. If a
   SECOND customer then asks for the same product, the agent does NOT
   say "sold out" bluntly and does NOT confirm availability — it takes
   their information and tells them the team will follow up. This must
   be handled deterministically in the workflow, not left to LLM judgment
   about what "pending" means.
4. **Log order intent to Notion** with all customer-provided details
   (name, contact, product, quantity, timestamp).
5. **Sync back when fulfilled.** When someone on the "team" marks an order
   Fulfilled in Notion, the pending count in the Sheet automatically drops
   and the item becomes available again for the next customer — this
   should happen automatically, not require the agent to be asked.
6. **Resist prompt injection**, specifically attempts to get the agent to
   grant a discount, reveal internal data (exact stock numbers, other
   customers' info), or override its own policies. This is a live,
   demoable part of the demo, not just a written claim.

This design is deliberately chosen because it produces a genuine,
testable reliability story (concurrent-order handling, injection
resistance) rather than a generic "chatbot that answers questions."
