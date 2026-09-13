"""Reset the demo to a clean state through the n8n workflow, then read every system back and save the evidence.

Sheet -> seed (Harbor Blue Hoodie stock 2 / pending 0 ...), Notion orders archived, dashboard tables cleared.
"""
import time

from lh import admin, env, notion, save_result, sheet_values, supa

st, resp = admin({"action": "reset"})
time.sleep(3)
_, q = notion("POST", f"/databases/{env('NOTION_ORDERS_DB_ID')}/query", {"page_size": 100})
out = {
    "reset_http": st,
    "reset_response": resp,
    "sheet_values": sheet_values(),
    "notion_active_orders": len(q.get("results", [])),
    "order_feed_rows": len(supa("GET", "/order_feed?select=notion_page_id")[1]),
    "agent_trace_rows": len(supa("GET", "/agent_trace?select=id")[1]),
    "live_state": supa("GET", "/live_state?select=product_name,status&order=product_name")[1],
}
print(out)
save_result("05_demo_reset_readback.json", out)
