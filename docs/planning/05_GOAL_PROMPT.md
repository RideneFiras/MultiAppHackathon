# The build plan — this is what Claude Code moves into automatically once
`00_START_HERE.md`'s verification pass is green. Firas does not need to
paste this in separately; it's here as the definition of done and as a
fallback if a session ever needs re-anchoring (e.g. a fresh Claude Code
session that's lost prior context can be pointed straight at this file).

---

You have full context in this folder: `01_CONTEXT.md` (who Firas is, the
hackathon, judging criteria, the scenario), `02_TECHNICAL_SPEC.md`
(architecture, integrations, guardrails, the Path A/Path B sync design),
`03_DASHBOARD_SPEC.md` (the judge-facing frontend), and `04_DEMO_SCRIPT.md`
(what the final demo needs to show).

**Goal:** build the complete system described in these files, end to end,
with full autonomy. Don't stop to ask questions unless you hit something
genuinely unresolvable alone (a real credential only Firas can provide, an
ambiguity that materially changes the architecture). Otherwise make the
reasonable call, note it, and keep going.

**Build order I'd suggest (adjust if you see a better path):**
1. n8n: build the three subagent sub-workflows first (`check_inventory`,
   `answer_from_kb`, `capture_order`), test each in isolation via n8n's
   manual execution before wiring the orchestrator.
2. n8n: build the main orchestrator AI Agent node, wire the three
   subagents as tools, add the structured output parser and the
   pre-filter injection-defense step.
3. Supabase: set up the pgvector table + ingest the store
   policy/product knowledge base for RAG. Set up the `live_state` sync
   table for the dashboard.
4. Wire the Notion → Sheets backward sync (fulfillment flow).
5. Build the Next.js dashboard per `03_DASHBOARD_SPEC.md`, deploy to
   Vercel.
6. Run the reliability tests listed at the end of `02_TECHNICAL_SPEC.md`
   yourself: the adversarial prompt set, the race-condition simulation,
   the fulfillment sync check, and one failure-path test. Use the
   Playwright MCP to actually navigate to the real Google Sheet and real
   Notion database during these tests and visually confirm the correct
   rows/cells changed — don't rely on API responses alone for Path A,
   since that's the part that has to be real, not just the dashboard
   echo. Record actual results, not assumed ones.
7. Iterate on anything that fails a test until it passes. Re-run the full
   test set after any fix that touches shared logic.
8. ONLY once steps 1-7 are solid and stable with real time to spare,
   evaluate the optional fourth integration (Slack notification —
   described in `02_TECHNICAL_SPEC.md`). If there's genuinely slack in
   the schedule, add it. If not, skip it — three real, tested
   integrations beats four with a rushed one, and the brief only asks
   for "at least three."
9. Write the README. Make explicit which apps are the real automation
   (Notion + Google Sheets, synced directly by n8n) versus the dashboard
   echo (Supabase Realtime, built solely because judges can't log into
   the other two) — this distinction should be a named section, not
   buried, since it's the core of the reliability story. Include what was
   built, how reliability was tested with actual results, a link to the
   demo video placeholder, and setup/run instructions.
10. Tell me clearly when it's ready for me to record the demo per
    `04_DEMO_SCRIPT.md`, including: the deployed URL, the exact product/
    quantity to use for the race-condition demo, and confirmation that
    the real Google Sheet and real Notion database are reset to a clean
    starting state.

**Constraints to respect throughout:**
- No tool anywhere in the system should be able to grant a discount,
  change a price, or reveal exact stock/pending numbers. If you find
  yourself tempted to add one "just to make a test pass," stop — that's
  a sign the test or the design needs rethinking, not the guardrail.
- The availability/race-condition logic must be deterministic (n8n
  IF/Switch logic), not left to LLM judgment call.
- Keep the frontend thin — no business logic in Next.js, only rendering
  and the Supabase Realtime subscription.
- Test as you go. Don't build the whole thing and test once at the end.

Work through this now. Give me a status update once the setup
verification from `00_START_HERE.md` items are all green, and again once
each numbered build step above is complete.
