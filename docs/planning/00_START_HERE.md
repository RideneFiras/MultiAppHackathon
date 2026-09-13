# START HERE — Read this file first, in this folder, before anything else

You are helping Firas build a hackathon project in ONE DAY (the hackathon is
happening today, Sept 13, 2026, 9AM-5PM Pacific).

**Read ALL of these fully, in order, before doing anything else:**

1. `00_START_HERE.md` (this file)
2. `01_CONTEXT.md` — who Firas is, the hackathon, judging criteria, the scenario
3. `02_TECHNICAL_SPEC.md` — architecture, integrations, guardrails, sync design
4. `03_DASHBOARD_SPEC.md` — the judge-facing frontend
5. `04_DEMO_SCRIPT.md` — what the 2-minute demo video needs to show
6. `05_GOAL_PROMPT.md` — the full build plan and definition of done

Once you've read all six, you have everything you need to work
autonomously. Do NOT wait for Firas to paste `05_GOAL_PROMPT.md` to you
separately — after you finish the verification pass below, if everything
required is in place, proceed directly into the build plan in
`05_GOAL_PROMPT.md` yourself, in the same session, without stopping. Only
stop and wait if a manual blocker (a credential, an account, a decision
only Firas can make) is genuinely in your way — and when Firas clears it,
continue straight into `05_GOAL_PROMPT.md` yourself rather than waiting
to be told to.

## Step 1 right now: VERIFY, DON'T BUILD YET

Before touching `05_GOAL_PROMPT.md`, check the environment and report back
to Firas exactly what he needs to set up manually. Do this by actually
running commands, not by asking him first — only ask about things you
genuinely cannot check or do yourself.

### Checks to run

**1. Azure CLI + n8n server**
- Check `az --version` and `az account show` to confirm Azure CLI is
  installed and logged into the right subscription.
- Find the App Service (or VM/container) running n8n. Check its current
  state and idle/sleep configuration (e.g. `az webapp show`, or check the
  plan tier — Free/Shared tiers idle after inactivity; Basic and above
  support "Always On").
- If it's on a tier that supports "Always On," enable it
  (`az webapp config set --always-on true ...`) so it doesn't go idle
  during the hackathon window.
- If it's on a tier that does NOT support Always On, tell Firas — he'll
  need to either upgrade the plan for the day or use an external uptime
  pinger (cron-job.org / UptimeRobot) hitting a health-check endpoint
  every 5 minutes. Set this up if you can do it via CLI/API; otherwise
  tell Firas to set the pinger up manually with the exact URL to ping.
- Confirm you can reach the n8n instance's URL/API from here (health
  check endpoint, or `/rest/login` etc.) and report status.

**2. n8n internal setup**
- Confirm n8n is reachable and check what credentials/nodes are already
  configured (Google Sheets, Notion, Supabase, HTTP nodes for the AI
  model).
- List what's MISSING that Firas needs to provide:
  - Google Sheets API access (service account JSON or OAuth) for a sheet
    Firas needs to create (inventory + pending count columns)
  - Notion integration token + a Notion database shared with that
    integration (orders/CRM database)
  - Supabase project URL + service key, and confirm the `pgvector`
    extension needs enabling (you can do this yourself if given DB
    access via the Supabase MCP — see below)
  - An LLM API key for the AI Agent nodes (Anthropic/OpenAI — ask which
    Firas wants to use)

**3. MCP access**
- Firas will provide MCP connections for Supabase and Notion. Once
  available, use them to:
  - Confirm the Supabase project is reachable, enable `pgvector` if not
    already on, and check/create the tables you'll need (see
    `02_TECHNICAL_SPEC.md` for schema).
  - Confirm the Notion integration can see the workspace, and check
    whether the orders database already exists or needs creating.
- If either MCP isn't connected yet, say so explicitly and tell Firas
  what needs connecting.

**4. Deployment target**
- Confirm you can deploy to Vercel (check for a Vercel CLI/token, or ask
  Firas to run `vercel login` if needed).
- Confirm n8n itself is reachable publicly (it already is, on Azure) so
  webhooks from the deployed frontend can hit it.

**5. Playwright MCP for visual verification**
- Firas has a Playwright MCP available. Confirm it's connected. You'll
  use this throughout the build (not just now) to actually open Chrome
  and look at the real Google Sheet and real Notion database yourself —
  useful both for initial setup (confirming the sheet/database structure
  matches what `02_TECHNICAL_SPEC.md` expects) and later for reliability
  testing (visually confirming state changed in the real apps, not just
  trusting an API response). See the "Visual verification via Playwright
  MCP" section in `02_TECHNICAL_SPEC.md`.
- Firas may need to have these accounts already logged into the Chrome
  profile Playwright will drive — ask him to confirm this if the
  Sheet/Notion pages aren't reachable when you try.

### Output of this step

Give Firas a short, direct list:
- ✅ What's already working
- ⚠️ What YOU fixed yourself (e.g. "enabled Always On")
- 🔲 What FIRAS needs to do manually before you can proceed (be specific:
  exact accounts, exact tokens, exact steps)

**Then:** if the list is all ✅/⚠️ with no 🔲 items, don't wait — proceed
straight into `05_GOAL_PROMPT.md` yourself. If there are 🔲 items, wait
for Firas to confirm they're done, then proceed straight into
`05_GOAL_PROMPT.md` yourself in that same reply — don't make him paste it
in as a separate message.
