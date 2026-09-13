# Planning docs

How the project was planned and handed over during the hackathon day (September 13, 2026). They're kept as a record of how we worked; the code and the main README describe what was actually built.

| File | What it is |
|---|---|
| `00_START_HERE.md` | Instructions for the setup session: check the infrastructure before building |
| `01_CONTEXT.md` | The hackathon brief, judging criteria and the store scenario |
| `02_TECHNICAL_SPEC.md` | First architecture: orchestrator + subagents, guardrails, the two write paths |
| `03_DASHBOARD_SPEC.md` | First dashboard spec |
| `04_DEMO_SCRIPT.md` | Plan for the 2-minute demo video |
| `05_GOAL_PROMPT.md` | Build plan and definition of done |
| `HANDOFF.md` | Handover from the setup session to the build session: verified infrastructure and decisions that override the specs (OpenAI instead of Claude, API-only verification, status rules) |

Some choices changed while building: everything moved into one n8n workflow, and the dashboard now shows the Sheet's stock and pending numbers.
