"""Shared helpers for Loomhaus scripts: .env loading + thin stdlib API clients.

Secrets are read from the project-root .env (keys are mixed case -> matched case-insensitively).
"""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
RESULTS = ROOT / "tests" / "results"


def _load_env():
    out = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


ENV = _load_env()


def env(key, default=None):
    return ENV.get(key.lower(), default)


def set_env(key, value):
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if "=" in line and line.split("=", 1)[0].strip().lower() == key.lower():
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ENV[key.lower()] = value


def http(method, url, body=None, headers=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "User-Agent": "loomhaus-scripts/1.0", **(headers or {})}
    req = urllib.request.Request(url, method=method, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def notion(method, path, body=None):
    return http(method, f"https://api.notion.com/v1{path}", body,
                {"Authorization": f"Bearer {env('NOTION_TOKEN')}", "Notion-Version": "2022-06-28"})


def n8n(method, path, body=None):
    return http(method, f"{env('N8N_BASE_URL').rstrip('/')}/api/v1{path}", body,
                {"X-N8N-API-KEY": env("n8n_api")})


def supa(method, path, body=None, prefer=None):
    key = env("service_role_supa")
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    if prefer:
        h["Prefer"] = prefer
    return http(method, f"{env('supabase_url')}/rest/v1{path}", body, h)


def admin(payload):
    """Call the n8n 'LH admin' webhook (Google Sheets proxy; the Google credential lives only in n8n)."""
    return http("POST", f"{env('N8N_BASE_URL').rstrip('/')}/webhook/loomhaus-admin", payload,
                {"X-Admin-Token": env("LH_ADMIN_TOKEN")})


def sheet_values(rng="Inventory!A1:D20"):
    sid = env("GOOGLE_SHEET_ID")
    st, body = admin({"method": "GET", "url": f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/{rng}"})
    if st != 200:
        raise RuntimeError(f"sheet read failed {st}: {body}")
    return body.get("values", [])


def sheet_rows():
    vals = sheet_values()
    head = vals[0]
    return [dict(zip(head, r)) for r in vals[1:]]


def chat(message, session_id, timeout=120):
    t0 = time.time()
    st, body = http("POST", f"{env('N8N_BASE_URL').rstrip('/')}/webhook/loomhaus-chat",
                    {"session_id": session_id, "message": message},
                    {"X-Chat-Token": env("LH_CHAT_TOKEN")}, timeout=timeout)
    return st, body, round(time.time() - t0, 2)


def save_result(name, data):
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = RESULTS / name
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return p
