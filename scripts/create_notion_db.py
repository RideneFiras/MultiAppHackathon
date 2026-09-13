"""Create the 'Loomhaus Orders' Notion database under the shared 'Loomhaus Store' page.

Usage: python scripts/create_notion_db.py
Reads NOTION_TOKEN from the project .env and writes NOTION_ORDERS_DB_ID back to it.
"""
import sys

from lh import env, notion, save_result, set_env

PARENT_PAGE = "3daebf8c-efff-80e7-82c5-f52b23ff3c4b"
PRODUCTS = ["Harbor Blue Hoodie", "Everyday White Tee", "Selvedge Denim Jacket",
            "Merino Rib Beanie", "Heavy Canvas Tote", "Trail Crew Socks (3-Pack)"]


def main():
    if env("NOTION_ORDERS_DB_ID") and "--force" not in sys.argv:
        sys.exit(f"NOTION_ORDERS_DB_ID already set: {env('NOTION_ORDERS_DB_ID')} (use --force to recreate)")
    props = {
        "Order": {"title": {}},
        "Customer Name": {"rich_text": {}},
        "Contact": {"rich_text": {}},
        "Product": {"select": {"options": [{"name": p} for p in PRODUCTS]}},
        "Quantity": {"number": {"format": "number"}},
        "Status": {"select": {"options": [{"name": "Pending", "color": "yellow"},
                                          {"name": "Fulfilled", "color": "green"},
                                          {"name": "Follow-up", "color": "orange"},
                                          {"name": "Sync Error", "color": "red"}]}},
        "Reserved": {"checkbox": {}},
        "Inventory Synced": {"checkbox": {}},
        "Notes": {"rich_text": {}},
        "Session": {"rich_text": {}},
        "Created": {"created_time": {}},
    }
    st, db = notion("POST", "/databases", {
        "parent": {"type": "page_id", "page_id": PARENT_PAGE},
        "title": [{"type": "text", "text": {"content": "Loomhaus Orders"}}],
        "properties": props,
    })
    if st != 200:
        sys.exit(f"Notion API error {st}: {db}")
    set_env("NOTION_ORDERS_DB_ID", db["id"])
    st, back = notion("GET", f"/databases/{db['id']}")
    save_result("00_notion_db_readback.json", {"status": st, "id": back.get("id"), "url": back.get("url"),
                                               "properties": sorted(back.get("properties", {}).keys())})
    print("created database:", db["id"], db.get("url"))


if __name__ == "__main__":
    main()
