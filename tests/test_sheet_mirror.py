"""Manual edit in the Google Sheet -> dashboard mirror, with no chat and no Notion involved.

Edits Heavy Canvas Tote stock directly in the Sheet (as a team member would), waits for the 30 s poll to copy it
to Supabase live_state, then restores the original value and waits for the mirror again.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lh import admin, env, save_result, sheet_rows, supa  # noqa: E402

PRODUCT = "LH-TOTE-NAT"
checks = []


def check(name, ok, detail=None):
    checks.append({"check": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, "" if detail is None else json.dumps(detail, ensure_ascii=False)[:300])


def set_stock(row_number, value):
    sid = env("GOOGLE_SHEET_ID")
    st, _ = admin({"method": "PUT", "body": {"values": [[value]]},
                   "url": f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/Inventory!C{row_number}?valueInputOption=RAW"})
    return st == 200


def wait_for_mirror(expected_stock, timeout=75):
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(5)
        live = supa("GET", f"/live_state?select=stock,pending,status,sheet_row,last_event&product_id=eq.{PRODUCT}")[1]
        if live and live[0]["stock"] == expected_stock:
            return round(time.time() - t0, 1), live[0]
    return None, None


rows = sheet_rows()
idx = next(i for i, r in enumerate(rows) if r["product_id"] == PRODUCT)
row_number, original = idx + 2, int(rows[idx]["stock"])
edited = original - 1

check(f"edit the Sheet directly: tote stock {original} -> {edited}", set_stock(row_number, edited))
secs, live = wait_for_mirror(edited)
check("dashboard mirror shows the edited value within one poll (< 45 s)", secs is not None and secs < 45,
      {"seconds": secs, "live_state": live})

check(f"restore the Sheet: tote stock {edited} -> {original}", set_stock(row_number, original))
secs2, live2 = wait_for_mirror(original)
check("dashboard mirror shows the restored value", secs2 is not None, {"seconds": secs2, "live_state": live2})

passed = sum(c["pass"] for c in checks)
print(f"\n{passed}/{len(checks)} checks passed")
save_result("07_sheet_mirror.json", {"summary": f"{passed}/{len(checks)} checks passed", "checks": checks})
