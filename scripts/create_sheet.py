"""Create the 'Loomhaus Inventory' Google Sheet through the n8n admin proxy, seed it, save GOOGLE_SHEET_ID."""
import csv
import sys

from lh import ROOT, admin, env, save_result, set_env, sheet_values

if env("GOOGLE_SHEET_ID") and "--force" not in sys.argv:
    sid = env("GOOGLE_SHEET_ID")
else:
    st, b = admin({"method": "POST", "url": "https://sheets.googleapis.com/v4/spreadsheets",
                   "body": {"properties": {"title": "Loomhaus Inventory"},
                            "sheets": [{"properties": {"title": "Inventory", "gridProperties": {"frozenRowCount": 1}}}]}})
    if st != 200 or "spreadsheetId" not in (b or {}):
        sys.exit(f"create failed {st}: {b}")
    sid = b["spreadsheetId"]
    set_env("GOOGLE_SHEET_ID", sid)

rows = list(csv.reader((ROOT / "supabase" / "inventory_seed.csv").open(encoding="utf-8")))
seed = [rows[0]] + [[r[0], r[1], int(r[2]), int(r[3])] for r in rows[1:]]
st, b = admin({"method": "PUT",
               "url": f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/Inventory!A1:D{len(seed)}?valueInputOption=RAW",
               "body": {"values": seed}})
if st != 200:
    sys.exit(f"seed failed {st}: {b}")
back = sheet_values()
save_result("00_sheet_seed_readback.json", {"spreadsheet_id": sid,
                                            "url": f"https://docs.google.com/spreadsheets/d/{sid}", "values": back})
print(sid, back)
