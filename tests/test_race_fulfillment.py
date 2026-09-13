"""Race condition + fulfillment sync test, verified only through API read-backs
(Notion API, Google Sheets via the n8n admin proxy, Supabase REST).

reset demo -> customer A orders the last 2 Harbor Blue Hoodies -> customer B asks for 1 (must NOT be confirmed,
logged as Follow-up, pending untouched) -> A's Notion page set to Fulfilled via the Notion API -> the 30 s
sync updates the Sheet (stock 0 / pending 0) + Inventory Synced -> one more cycle to prove idempotency.
"""
import json
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lh import admin, chat, env, notion, save_result, sheet_rows, supa  # noqa: E402

DB = env("NOTION_ORDERS_DB_ID")
HOODIE = "Harbor Blue Hoodie"
NUM_LEAK = re.compile(r"\b\d+\s+(units?\s+)?(left|remaining|in stock|on hand)\b", re.I)
CONFIRMS = re.compile(r"\b(order (is|has been) (confirmed|placed)|is available|are available)\b", re.I)
checks, transcript = [], []


def check(name, ok, detail=None):
    checks.append({"check": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, "" if detail is None else json.dumps(detail, ensure_ascii=False)[:300])


def notion_orders():
    _, b = notion("POST", f"/databases/{DB}/query", {"page_size": 100})
    out = []
    for pg in b.get("results", []):
        p = pg["properties"]

        def txt(k):
            return "".join(t["plain_text"] for t in (p[k].get("rich_text") or p[k].get("title") or []))

        out.append({"page_id": pg["id"], "order_ref": txt("Order"), "customer": txt("Customer Name"),
                    "product": (p["Product"]["select"] or {}).get("name"), "quantity": p["Quantity"]["number"],
                    "status": (p["Status"]["select"] or {}).get("name"), "reserved": p["Reserved"]["checkbox"],
                    "inventory_synced": p["Inventory Synced"]["checkbox"], "session": txt("Session"),
                    "created_time": pg["created_time"]})
    return out


def hoodie_row():
    return next(r for r in sheet_rows() if r["product_name"] == HOODIE)


def say(session, msg):
    st, body, secs = chat(msg, session)
    transcript.append({"session": session, "message": msg, "http": st, "seconds": secs, "response": body})
    print(f"[{session}] {secs}s {json.dumps(body, ensure_ascii=False)[:420]}")
    return body or {}


def supa_get(path):
    return supa("GET", path)[1]


evidence = {}
st, r = admin({"action": "reset_seed"})
check("reset demo through the n8n workflow", st == 200 and (r or {}).get("ok"), r)
time.sleep(3)
row = hoodie_row()
check("clean start: Sheet hoodie stock 2 / pending 0", row["stock"] == "2" and row["pending"] == "0", row)
check("clean start: no active Notion orders", len(notion_orders()) == 0)

A, B = "race-A-" + uuid.uuid4().hex[:6], "race-B-" + uuid.uuid4().hex[:6]
a1 = say(A, "Hi! Is the Harbor Blue Hoodie available? I'd like 2.")
check("A1: availability checked by check_inventory -> available", "check_inventory(available)" in (a1.get("path") or ""), a1.get("path"))
check("A1: no stock numbers in reply", not NUM_LEAK.search(a1.get("reply_text", "")), a1.get("reply_text"))
a2 = say(A, "Great, I'll take 2. My name is Alex Kim and my email is alex.kim@example.com")
check("A2: capture_order -> order_captured", "capture_order(order_captured)" in (a2.get("path") or ""), a2.get("path"))
time.sleep(2)
oa = [o for o in notion_orders() if o["session"] == A]
check("Notion: A's order Pending, Reserved, qty 2, Harbor Blue Hoodie",
      len(oa) == 1 and oa[0]["status"] == "Pending" and oa[0]["reserved"] and oa[0]["quantity"] == 2 and oa[0]["product"] == HOODIE, oa)
row = hoodie_row()
check("Sheet: hoodie pending incremented 0 -> 2 (stock still 2)", row["pending"] == "2" and row["stock"] == "2", row)

b1 = say(B, "Do you have the Harbor Blue Hoodie? I want 1.")
check("B1: check_inventory -> not_confirmed (deterministic IF gate)", "check_inventory(not_confirmed)" in (b1.get("path") or ""), b1.get("path"))
t = b1.get("reply_text", "")
check("B1: reply neither says sold out nor confirms availability",
      "sold out" not in t.lower() and "out of stock" not in t.lower() and not CONFIRMS.search(t), t)
b2 = say(B, "OK, please have the team follow up with me. I'm Jordan Lee, phone +1 415 555 0199")
check("B2: capture_order -> follow_up_logged", "capture_order(follow_up_logged)" in (b2.get("path") or ""), b2.get("path"))
t = b2.get("reply_text", "")
check("B2: reply does not confirm the order or say sold out", "sold out" not in t.lower() and not CONFIRMS.search(t), t)
time.sleep(2)
orders = notion_orders()
ob = [o for o in orders if o["session"] == B]
check("Notion: B logged with Status Follow-up, not Reserved",
      len(ob) == 1 and ob[0]["status"] == "Follow-up" and not ob[0]["reserved"], ob)
row = hoodie_row()
check("Sheet: pending NOT incremented for B (still 2)", row["pending"] == "2" and row["stock"] == "2", row)
feed = supa_get("/order_feed?select=order_ref,customer_display,product_name,quantity,status&order=created_at.asc")
live = supa_get("/live_state?select=product_name,stock,pending,status&product_id=eq.LH-HOOD-BLU")
check("Supabase echo: order_feed = A Pending + B Follow-up with masked names",
      [f["status"] for f in feed] == ["Pending", "Follow-up"] and [f["customer_display"] for f in feed] == ["Alex K.", "Jordan L."], feed)
check("Dashboard mirror: hoodie row matches the Sheet (stock 2, pending 2, Pending team review)",
      live and live[0]["stock"] == 2 and live[0]["pending"] == 2 and live[0]["status"] == "Pending team review", live)
evidence["after_race"] = {"notion": orders, "sheet_hoodie": row, "order_feed": feed, "live_state": live}

# ---- fulfillment sync (Notion -> Sheets), nobody talks to the agent
st, _ = notion("PATCH", f"/pages/{oa[0]['page_id']}", {"properties": {"Status": {"select": {"name": "Fulfilled"}}}})
check("Notion API: A's order set to Fulfilled", st == 200)
t0, synced = time.time(), None
while time.time() - t0 < 100:
    time.sleep(5)
    row = hoodie_row()
    pa = next(o for o in notion_orders() if o["page_id"] == oa[0]["page_id"])
    if row["stock"] == "0" and row["pending"] == "0" and pa["inventory_synced"]:
        synced = round(time.time() - t0, 1)
        break
check("Fulfillment: Sheet stock 2->0, pending 2->0 and Inventory Synced=true in < 60 s",
      synced is not None and synced < 60, {"seconds": synced, "sheet_hoodie": row})
time.sleep(3)
feed = supa_get("/order_feed?select=order_ref,customer_display,status&order=created_at.asc")
live = supa_get("/live_state?select=product_name,stock,pending,status,last_event&product_id=eq.LH-HOOD-BLU")
check("Supabase echo after fulfillment: A = Fulfilled", feed and feed[0]["status"] == "Fulfilled", feed)
check("Dashboard mirror after fulfillment: hoodie stock 0 / pending 0", live and live[0]["stock"] == 0 and live[0]["pending"] == 0, live)
evidence["after_fulfillment"] = {"seconds_to_sync": synced, "sheet_hoodie": row, "order_feed": feed, "live_state": live}

time.sleep(40)  # at least one more 30 s poll
row = hoodie_row()
pa = next(o for o in notion_orders() if o["page_id"] == oa[0]["page_id"])
check("Idempotent: next sync cycle leaves stock 0 / pending 0 (no double decrement)",
      row["stock"] == "0" and row["pending"] == "0" and pa["inventory_synced"], row)
evidence["after_idempotency_wait"] = {"sheet_hoodie": row, "notion_order_a": pa}

passed = sum(c["pass"] for c in checks)
print(f"\n{passed}/{len(checks)} checks passed")
save_result("03_race_fulfillment.json", {"summary": f"{passed}/{len(checks)} checks passed", "checks": checks,
                                         "transcript": transcript, "evidence": evidence})
