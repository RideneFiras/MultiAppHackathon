"""Public reset (the dashboard's Reset button, no key) against the deployed dashboard.

Expected: Notion orders archived, the units they reserved released in the Sheet, stock never overwritten
(a manual stock edit survives the reset), dashboard feed cleared, inventory mirror matches the Sheet.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lh import admin, env, http, notion, save_result, sheet_rows, supa  # noqa: E402

URL = os.environ.get("DASHBOARD_URL", "https://loomhaus-agent.vercel.app")
SHEET_URL = f"https://sheets.googleapis.com/v4/spreadsheets/{env('GOOGLE_SHEET_ID')}/values"
checks = []


def check(name, ok, detail=None):
    checks.append({"check": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, "" if detail is None else json.dumps(detail, ensure_ascii=False)[:300])


def rows_by_id():
    return {r["product_id"]: r for r in sheet_rows()}


st, r = admin({"action": "reset_seed"})
check("start from the seed state (admin reset)", st == 200 and (r or {}).get("ok"), r)
time.sleep(2)

st, r = admin({"action": "tool", "tool": "capture_order", "customer_name": "Reset Tester",
               "contact": "reset.tester@example.com", "product": "Merino Rib Beanie", "quantity": 2, "notes": "",
               "session_id": "public-reset-test"})
check("capture_order reserves 2 Merino Rib Beanies", (r or {}).get("result") == "order_captured", r)
rows = rows_by_id()
check("Sheet: beanie stock 3 / pending 2 before the reset", rows["LH-BEAN-GRY"]["stock"] == "3" and rows["LH-BEAN-GRY"]["pending"] == "2", rows["LH-BEAN-GRY"])

tote_row = list(rows).index("LH-TOTE-NAT") + 2
st, _ = admin({"method": "PUT", "url": f"{SHEET_URL}/Inventory!C{tote_row}?valueInputOption=RAW", "body": {"values": [[24]]}})
check("simulate a manual stock correction in the Sheet (tote 25 -> 24)", st == 200)

t0 = time.time()
st, r = http("POST", URL + "/api/reset", {})
check("POST /api/reset on the public dashboard works without a key", st == 200 and (r or {}).get("ok"),
      {"http": st, "response": r, "seconds": round(time.time() - t0, 1)})
time.sleep(3)

rows = rows_by_id()
_, q = notion("POST", f"/databases/{env('NOTION_ORDERS_DB_ID')}/query", {"page_size": 100})
check("Notion: no active orders left", len(q.get("results", [])) == 0, len(q.get("results", [])))
check("Sheet: beanie reservation released (pending 2 -> 0, stock still 3)",
      rows["LH-BEAN-GRY"]["pending"] == "0" and rows["LH-BEAN-GRY"]["stock"] == "3", rows["LH-BEAN-GRY"])
check("Sheet: stock not overwritten (tote keeps the manual value 24)", rows["LH-TOTE-NAT"]["stock"] == "24", rows["LH-TOTE-NAT"])
feed = supa("GET", "/order_feed?select=notion_page_id")[1]
traces = supa("GET", "/agent_trace?select=id")[1]
check("dashboard feed and trace cleared", len(feed) == 0 and len(traces) == 0, {"order_feed": len(feed), "agent_trace": len(traces)})
live = {x["product_id"]: x for x in supa("GET", "/live_state?select=product_id,stock,pending,status")[1]}
check("dashboard inventory mirror matches the Sheet after the reset",
      live["LH-BEAN-GRY"]["pending"] == 0 and live["LH-BEAN-GRY"]["stock"] == 3 and live["LH-TOTE-NAT"]["stock"] == 24,
      {"LH-BEAN-GRY": live["LH-BEAN-GRY"], "LH-TOTE-NAT": live["LH-TOTE-NAT"]})

st, _ = admin({"method": "PUT", "url": f"{SHEET_URL}/Inventory!C{tote_row}?valueInputOption=RAW", "body": {"values": [[25]]}})
check("restore tote stock to 25", st == 200)

passed = sum(c["pass"] for c in checks)
print(f"\n{passed}/{len(checks)} checks passed")
save_result("08_public_reset.json", {"summary": f"{passed}/{len(checks)} checks passed", "checks": checks})
