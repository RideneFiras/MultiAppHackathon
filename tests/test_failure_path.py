"""Failure-path test: break capture_order's Notion access for real (invalid database id), place an order through
the live chat, and verify the system fails loudly instead of half-writing:
  - agent trace shows capture_order(error) and the customer is told nothing was recorded
  - Google Sheet pending is NOT incremented
  - no Notion page was created for the session
  - a sync_log error row was written
Then redeploy the normal workflow and confirm a subagent is healthy again.
"""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lh import admin, chat, env, notion, save_result, sheet_rows, supa  # noqa: E402

JACKET = "Selvedge Denim Jacket"
checks, evidence = [], {}


def check(name, ok, detail=None):
    checks.append({"check": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, "" if detail is None else json.dumps(detail, ensure_ascii=False)[:300])


def deploy(broken):
    e = dict(os.environ, LH_BREAK_NOTION="1" if broken else "0")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_n8n.py")], env=e, capture_output=True, text=True,
                       cwd=ROOT / "scripts")
    print(r.stdout.strip()[-200:], r.stderr.strip()[-300:])
    return r.returncode == 0


jacket_before = next(r for r in sheet_rows() if r["product_name"] == JACKET)
logs = supa("GET", "/sync_log?select=id&order=id.desc&limit=1")[1]
last_log_id = logs[0]["id"] if logs else 0
evidence["sheet_before"] = jacket_before

check("deploy workflow with an invalid Notion database id (simulated outage)", deploy(True))
try:
    time.sleep(3)
    S = "fail-" + uuid.uuid4().hex[:8]
    st, body, secs = chat("I'd like to order 1 Selvedge Denim Jacket please. I'm Sam Rivera, sam.rivera@example.com", S)
    body = body or {}
    evidence["chat"] = {"http": st, "seconds": secs, "response": body}
    print(json.dumps(body, ensure_ascii=False)[:500])
    check("trace shows capture_order(error)", "capture_order(error)" in (body.get("path") or ""), body.get("path"))
    reply = (body.get("reply_text") or "").lower()
    check("customer told the request could not be recorded (no false confirmation)",
          any(w in reply for w in ("could not", "couldn't", "unable", "not able", "try again")), body.get("reply_text"))
    time.sleep(2)
    jacket_after = next(r for r in sheet_rows() if r["product_name"] == JACKET)
    evidence["sheet_after"] = jacket_after
    check("Google Sheet pending NOT incremented", jacket_after["pending"] == jacket_before["pending"],
          {"before": jacket_before, "after": jacket_after})
    _, q = notion("POST", f"/databases/{env('NOTION_ORDERS_DB_ID')}/query",
                  {"filter": {"property": "Session", "rich_text": {"equals": S}}})
    check("no Notion page created for the failed order", len(q.get("results", [])) == 0, len(q.get("results", [])))
    new_logs = supa("GET", f"/sync_log?select=*&id=gt.{last_log_id}&order=id.asc")[1]
    evidence["sync_log"] = new_logs
    check("sync_log has an error row for capture_order",
          any(l["workflow"] == "capture_order" and l["level"] == "error" for l in new_logs), new_logs)
finally:
    check("redeploy the normal workflow", deploy(False))
    time.sleep(3)
    st, r = admin({"action": "tool", "tool": "check_inventory", "product": "denim jacket", "quantity": 1})
    check("after restore, subagent healthy (check_inventory -> available)", st == 200 and (r or {}).get("status") == "available", r)

passed = sum(c["pass"] for c in checks)
print(f"\n{passed}/{len(checks)} checks passed")
save_result("04_failure_path.json", {"summary": f"{passed}/{len(checks)} checks passed", "checks": checks, "evidence": evidence})
