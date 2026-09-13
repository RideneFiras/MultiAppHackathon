"""One-off infra script from the setup session: move n8n's own database from Neon to Supabase (schema n8n)
and repoint the Azure Container App that runs n8n. Not needed to run Loomhaus.

  python scripts/infra/run_migration.py            -> preflight only, changes nothing
  python scripts/infra/run_migration.py --execute  -> stop n8n, copy DB inside an Azure container, verify counts,
                                                      repoint n8n at Supabase, start, verify. Rolls back on failure.
Neon is never modified, so it stays a working fallback. Needs AZURE_SUBSCRIPTION_ID in the environment.
"""
import argparse, base64, copy, json, os, re, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path
from urllib.parse import urlparse, unquote

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
SUB = os.environ.get("AZURE_SUBSCRIPTION_ID", "<azure-subscription-id>")
RG = "rg-n8n"
APP = f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.App/containerApps/n8n"
ACI = f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.ContainerInstance/containerGroups/n8n-db-migrate"
APP_API, ACI_API = "2024-03-01", "2023-05-01"
N8N = "https://n8n.calmplant-7938ba96.switzerlandnorth.azurecontainerapps.io"
IMAGE = "public.ecr.aws/docker/library/postgres:18"
HERE = Path(__file__).parent


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def read_env():
    vals = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*[=:]\s*(.*)$", line)
        if m:
            vals[m.group(1).lower()] = m.group(2).strip().strip("'\"")
    return vals


_token = None


def arm(method, path, api, body=None, ok=(200, 201, 202, 204)):
    global _token
    if _token is None:
        _token = subprocess.run("az account get-access-token --query accessToken -o tsv", shell=True,
                                capture_output=True, text=True, check=True).stdout.strip()
    url = f"https://management.azure.com{path}?api-version={api}"
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {_token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        if e.code in ok:
            return e.code, {}
        raise RuntimeError(f"{method} {path.split('/providers/')[-1]} -> HTTP {e.code}: {raw[:600]}")


def http_code(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def pg_parts(url):
    u = urlparse(url)
    return dict(host=u.hostname, port=u.port or 5432, dbname=(u.path or "/postgres").lstrip("/") or "postgres",
                user=unquote(u.username or ""), password=unquote(u.password or ""))


def preflight(src, dst):
    import psycopg
    d = pg_parts(dst)
    problems = []
    if not d["password"] or d["password"] in ("[YOUR-PASSWORD]", "YOUR_DB_PASSWORD"):
        problems.append("supabase_db_url has no real password in it")
    if not (d["host"] or "").endswith("pooler.supabase.com"):
        problems.append(f"host {d['host']} is not the Session pooler (*.pooler.supabase.com); db.* hosts are IPv6-only and unreachable from Azure")
    if d["port"] != 5432:
        problems.append(f"port {d['port']} is the Transaction pooler; n8n needs the Session pooler on port 5432")
    if problems:
        for p in problems:
            log("PREFLIGHT FAIL:", p)
        return False
    for name, url in (("neon", src), ("supabase", dst)):
        with psycopg.connect(url, connect_timeout=20) as c:
            ver = c.execute("show server_version").fetchone()[0]
            if name == "neon":
                n = c.execute("select count(*) from information_schema.tables where table_schema='public'").fetchone()[0]
                log(f"preflight neon ok: postgres {ver}, {n} n8n tables")
            else:
                n8n_tables = c.execute("select count(*) from information_schema.tables where table_schema='n8n'").fetchone()[0]
                pub = c.execute("select count(*) from information_schema.tables where table_schema='public'").fetchone()[0]
                log(f"preflight supabase ok: postgres {ver}, schema n8n has {n8n_tables} tables (must be 0), public has {pub}")
                if n8n_tables:
                    log("PREFLIGHT FAIL: schema n8n on Supabase is not empty")
                    return False
    return True


def wait_app_state(want, timeout=240):
    end = time.time() + timeout
    while time.time() < end:
        _, a = arm("GET", APP, APP_API)
        if a["properties"].get("runningStatus") == want:
            return True
        time.sleep(10)
    return False


def run_container(src, dst):
    script = (HERE / "migrate_n8n_db.sh").read_bytes().replace(b"\r\n", b"\n")
    body = {"location": "switzerlandnorth", "properties": {"osType": "Linux", "restartPolicy": "Never", "containers": [{
        "name": "migrate", "properties": {
            "image": IMAGE,
            "command": ["/bin/bash", "-c", 'echo "$SCRIPT_B64" | base64 -d > /tmp/m.sh && exec bash /tmp/m.sh'],
            "environmentVariables": [{"name": "SRC_URL", "secureValue": src}, {"name": "DST_URL", "secureValue": dst},
                                     {"name": "SCRIPT_B64", "secureValue": base64.b64encode(script).decode()}],
            "resources": {"requests": {"cpu": 1, "memoryInGB": 1.5}}}}]}}
    arm("DELETE", ACI, ACI_API, ok=(200, 202, 204, 404))
    time.sleep(5)
    arm("PUT", ACI, ACI_API, body)
    log("migration container created; waiting for it to finish")
    cs, end = {}, time.time() + 900
    while time.time() < end:
        _, g = arm("GET", ACI, ACI_API)
        p = g.get("properties", {})
        cs = (((p.get("containers") or [{}])[0].get("properties") or {}).get("instanceView") or {}).get("currentState") or {}
        log("  container:", p.get("provisioningState"), cs.get("state"), cs.get("detailStatus", ""))
        if cs.get("state") == "Terminated" or p.get("provisioningState") == "Failed":
            break
        time.sleep(10)
    try:
        _, lg = arm("GET", ACI + "/containers/migrate/logs", ACI_API)
        logs = lg.get("content", "")
    except RuntimeError as e:
        logs = f"(could not fetch logs: {e})"
    print("----- container logs -----\n" + logs + "\n--------------------------", flush=True)
    arm("DELETE", ACI, ACI_API, ok=(200, 202, 204, 404))
    return cs.get("exitCode"), logs


def cutover(orig, dst):
    d = pg_parts(dst)
    t = copy.deepcopy(orig["properties"]["template"])
    c = t["containers"][0]
    c["env"] = [e for e in c["env"] if not e["name"].startswith("DB_POSTGRESDB_")] + [
        {"name": "DB_POSTGRESDB_HOST", "value": d["host"]},
        {"name": "DB_POSTGRESDB_PORT", "value": str(d["port"])},
        {"name": "DB_POSTGRESDB_DATABASE", "value": d["dbname"]},
        {"name": "DB_POSTGRESDB_USER", "value": d["user"]},
        {"name": "DB_POSTGRESDB_PASSWORD", "secretRef": "supabase-db-password"},
        {"name": "DB_POSTGRESDB_SCHEMA", "value": "n8n"},
        {"name": "DB_POSTGRESDB_SSL_ENABLED", "value": "true"},
        {"name": "DB_POSTGRESDB_SSL_REJECT_UNAUTHORIZED", "value": "false"},
    ]
    cfg = copy.deepcopy(orig["properties"]["configuration"])
    cfg["secrets"] = [{"name": "supabase-db-password", "value": d["password"]}]
    arm("PATCH", APP, APP_API, {"properties": {"configuration": cfg, "template": t}})


def wait_healthy(old_rev, timeout=600):
    end = time.time() + timeout
    while time.time() < end:
        _, revs = arm("GET", APP + "/revisions", APP_API)
        act = [(r["name"], r["properties"].get("runningState")) for r in revs.get("value", []) if r["properties"].get("active")]
        code = http_code(N8N + "/healthz/readiness")
        log("  active:", act, "readiness:", code)
        if code == 200 and any(n != old_rev and s in ("Running", "RunningAtMaxScale") for n, s in act):
            return True
        time.sleep(15)
    return False


def owner_exists():
    for _ in range(3):
        try:
            with urllib.request.urlopen(N8N + "/rest/settings", timeout=20) as r:
                return not json.loads(r.read())["data"]["userManagement"]["showSetupOnFirstLoad"]
        except Exception as e:
            log("  settings check retry:", e)
            time.sleep(10)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    env = read_env()
    src, dst = env.get("neon"), env.get("supabase_db_url")
    if not src or not dst:
        sys.exit("need both `neon` and `supabase_db_url` in .env")
    if not preflight(src, dst):
        sys.exit(1)
    if not args.execute:
        log("preflight passed; run again with --execute to migrate")
        return
    _, orig = arm("GET", APP, APP_API)
    old_rev = orig["properties"]["latestRevisionName"]
    log("stopping n8n (no writes during the copy)")
    try:
        arm("POST", APP + "/stop", APP_API)
        log("  stopped" if wait_app_state("Stopped") else "  WARNING: stop not confirmed, continuing (pg_dump is a consistent snapshot)")
    except RuntimeError as e:
        log("  WARNING: stop call failed, continuing on a live snapshot:", e)
    try:
        code, logs = run_container(src, dst)
        if code != 0 or "MIGRATION_OK" not in logs:
            raise RuntimeError(f"migration container exit={code}")
    except Exception as e:
        log("MIGRATION FAILED:", e, "-> restarting n8n on Neon, nothing changed")
        arm("POST", APP + "/start", APP_API, ok=(200, 202, 204, 409))
        sys.exit(2)
    log("data copied and verified; repointing n8n at Supabase")
    try:
        cutover(orig, dst)
    except Exception as e:
        log("CUTOVER PATCH FAILED:", e, "-> starting n8n on Neon (config unchanged)")
        arm("POST", APP + "/start", APP_API, ok=(200, 202, 204, 409))
        sys.exit(2)
    arm("POST", APP + "/start", APP_API, ok=(200, 202, 204, 409))
    if wait_healthy(old_rev) and owner_exists():
        log("SUCCESS: n8n is running on Supabase (schema n8n); owner account and data present")
        return
    log("CUTOVER FAILED -> rolling back to Neon")
    arm("PATCH", APP, APP_API, {"properties": {"template": orig["properties"]["template"]}})
    arm("POST", APP + "/start", APP_API, ok=(200, 202, 204, 409))
    log("rolled back; healthy on Neon" if wait_healthy(None) else "ROLLBACK NOT CONFIRMED - check the app")
    sys.exit(3)


if __name__ == "__main__":
    main()
