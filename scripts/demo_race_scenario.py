"""Stage a real race-condition example in the live system for the demo video, and DON'T reset afterwards.

Customer A (Alex Kim)   orders the last 2 Harbor Blue Hoodies     -> Notion Pending, Sheet pending 0 -> 2
Customer B (Jordan Lee) asks for 1 hoodie                         -> not confirmed, Notion Follow-up, Sheet unchanged
Customer C              asks for 10 Selvedge Denim Jackets (6)    -> not confirmed, nothing written

Prints the n8n execution links to open in the video (execution log), plus the state read back from the APIs.
"""
import json
import time
import uuid
from datetime import datetime, timezone

from lh import ROOT, chat, env, n8n, notion, save_result, sheet_rows, supa

WF = json.loads((ROOT / "n8n" / "workflow_ids.json").read_text())["loomhaus"]
BASE = env("N8N_BASE_URL").rstrip("/")
started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
conversation = []


def say(session, who, message):
    st, body, secs = chat(message, session)
    body = body or {}
    conversation.append({"customer": who, "session": session, "message": message, "seconds": secs,
                         "reply": body.get("reply_text"), "trace": body.get("path")})
    print(f"[{who}] {message}\n    trace: {body.get('path')}\n    reply: {body.get('reply_text')}\n")


A, B, C = (f"demo-{n}-{uuid.uuid4().hex[:4]}" for n in ("alex", "jordan", "sam"))
say(A, "Customer A", "Hi! Is the Harbor Blue Hoodie available? I'd like 2.")
say(A, "Customer A", "Great, I'll take both. I'm Alex Kim, alex.kim@example.com")
say(B, "Customer B", "Hi, do you have the Harbor Blue Hoodie? I'd like 1.")
say(B, "Customer B", "Sure, please have the team contact me. I'm Jordan Lee, jordan.lee@example.com")
say(C, "Customer C", "Can I get 10 Selvedge Denim Jackets?")
time.sleep(4)

# ---- state read back through the APIs
rows = {r["product_name"]: r for r in sheet_rows()}
_, q = notion("POST", f"/databases/{env('NOTION_ORDERS_DB_ID')}/query", {"page_size": 20})
orders = []
for pg in q.get("results", []):
    p = pg["properties"]
    txt = lambda k: "".join(t["plain_text"] for t in (p[k].get("rich_text") or p[k].get("title") or []))  # noqa: E731
    orders.append({"order": txt("Order"), "customer": txt("Customer Name"), "product": (p["Product"]["select"] or {}).get("name"),
                   "qty": p["Quantity"]["number"], "status": (p["Status"]["select"] or {}).get("name"),
                   "reserved": p["Reserved"]["checkbox"]})

# ---- n8n executions created by these messages (skip the 30 s schedule runs)
LABELS = [
    ("Chat webhook", "chat message"),
    ("[inventory] Status: available", "check_inventory -> available"),
    ("[inventory] Status: not confirmed", "check_inventory -> NOT confirmed (IF node false branch)"),
    ("[order] Result: captured", "capture_order -> Pending + reserved"),
    ("[order] Result: follow-up", "capture_order -> Follow-up, nothing reserved"),
]
_, listing = n8n("GET", f"/executions?workflowId={WF}&limit=100")
executions = []
for e in sorted((x for x in listing.get("data", []) if x.get("startedAt", "") >= started), key=lambda x: int(x["id"])):
    _, d = n8n("GET", f"/executions/{e['id']}?includeData=true")
    run = (((d or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    if "[sync] Every 30 seconds" in run:
        continue
    what = [label for node, label in LABELS if node in run]
    detail = None
    try:
        if "Chat webhook" in run:
            detail = run["Chat webhook"][0]["data"]["main"][0][0]["json"]["body"]["message"]
        elif "When called as subagent tool" in run:
            j = run["When called as subagent tool"][0]["data"]["main"][0][0]["json"]
            detail = {k: v for k, v in j.items() if k in ("tool", "product", "quantity", "customer_name")}
    except (KeyError, IndexError, TypeError):
        pass
    executions.append({"id": e["id"], "what": what, "input": detail, "url": f"{BASE}/workflow/{WF}/executions/{e['id']}"})

print("Sheet:", {k: (v["stock"], v["pending"]) for k, v in rows.items() if k in ("Harbor Blue Hoodie", "Selvedge Denim Jacket", "Merino Rib Beanie")})
print("Notion:", orders)
print("\nExecutions:")
for x in executions:
    print(f"  {x['id']}: {', '.join(x['what'])} | {x['input']}\n     {x['url']}")

save_result("09_demo_race_scenario.json", {
    "conversation": conversation,
    "sheet": {k: {"stock": v["stock"], "pending": v["pending"]} for k, v in rows.items()},
    "notion_orders": orders,
    "dashboard_orders": supa("GET", "/order_feed?select=order_ref,customer_display,product_name,quantity,status")[1],
    "n8n_executions": executions,
})
