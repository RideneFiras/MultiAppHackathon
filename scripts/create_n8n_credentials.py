"""Create the n8n credentials Loomhaus needs via the n8n REST API (idempotent: skips keys already in .env).

- notionApi       "Notion - Loomhaus"        from NOTION_TOKEN
- supabaseApi     "Supabase - Loomhaus app"  host=supabase_url, serviceRole=service_role_supa
- httpHeaderAuth  "LH admin token"           X-Admin-Token (admin/Sheets proxy webhook)
- httpHeaderAuth  "LH chat token"            X-Chat-Token (chat webhook, used by the Next.js proxy)
Generated tokens and credential ids are written back to .env.
"""
import secrets

from lh import env, n8n, save_result, set_env


def create(name, type_, data):
    st, body = n8n("POST", "/credentials", {"name": name, "type": type_, "data": data})
    if st not in (200, 201):
        _, schema = n8n("GET", f"/credentials/schema/{type_}")
        raise SystemExit(f"FAILED {name} {st}: {body}\nschema: {schema}")
    return body["id"]


for k in ("LH_ADMIN_TOKEN", "LH_CHAT_TOKEN"):
    if not env(k):
        set_env(k, secrets.token_urlsafe(32))

specs = [
    ("N8N_CRED_NOTION", "Notion - Loomhaus", "notionApi", {"apiKey": env("NOTION_TOKEN")}),
    ("N8N_CRED_SUPABASE", "Supabase - Loomhaus app", "supabaseApi",
     {"host": env("supabase_url"), "serviceRole": env("service_role_supa")}),
    ("N8N_CRED_ADMIN", "LH admin token", "httpHeaderAuth", {"name": "X-Admin-Token", "value": env("LH_ADMIN_TOKEN")}),
    ("N8N_CRED_CHAT", "LH chat token", "httpHeaderAuth", {"name": "X-Chat-Token", "value": env("LH_CHAT_TOKEN")}),
]
out = {}
for key, name, type_, data in specs:
    if not env(key):
        set_env(key, create(name, type_, data))
    out[key] = env(key)
print(out)
save_result("00_n8n_credentials.json", {k: v for k, v in out.items()})
