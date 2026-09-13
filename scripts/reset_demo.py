"""Reset the demo through the n8n workflow, then read every system back and save the evidence.

  python scripts/reset_demo.py          same as the dashboard button: archive the Notion orders, release the units
                                        they reserved in the Sheet (stock untouched), clear the dashboard feed
  python scripts/reset_demo.py --seed   admin only: first restore the Sheet to supabase/inventory_seed.csv
"""
import sys
import time

from lh import admin, env, notion, save_result, sheet_values, supa

action = "reset_seed" if "--seed" in sys.argv else "reset"
st, resp = admin({"action": action})
time.sleep(3)
_, q = notion("POST", f"/databases/{env('NOTION_ORDERS_DB_ID')}/query", {"page_size": 100})
out = {
    "action": action,
    "reset_http": st,
    "reset_response": resp,
    "sheet_values": sheet_values(),
    "notion_active_orders": len(q.get("results", [])),
    "order_feed_rows": len(supa("GET", "/order_feed?select=notion_page_id")[1]),
    "agent_trace_rows": len(supa("GET", "/agent_trace?select=id")[1]),
    "live_state": supa("GET", "/live_state?select=sheet_row,product_name,stock,pending,status&order=sheet_row")[1],
}
print(out)
save_result("05_demo_reset_readback.json", out)
