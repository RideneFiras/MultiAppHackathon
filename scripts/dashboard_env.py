"""Generate dashboard/.env.local from the root .env and (with --vercel) push the same vars to the Vercel project.

Browser-safe: NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY.
Server-only (route handlers): N8N_CHAT_WEBHOOK_URL, N8N_CHAT_TOKEN, N8N_ADMIN_WEBHOOK_URL, N8N_ADMIN_TOKEN, DEMO_RESET_KEY.
The Supabase service_role key is never included.
"""
import secrets
import subprocess
import sys

from lh import ROOT, env, set_env

if not env("DEMO_RESET_KEY"):
    set_env("DEMO_RESET_KEY", "loomhaus-" + secrets.token_hex(3))

base = env("N8N_BASE_URL").rstrip("/")
VALUES = {
    "NEXT_PUBLIC_SUPABASE_URL": env("supabase_url"),
    "NEXT_PUBLIC_SUPABASE_ANON_KEY": env("supabase_anon"),
    "N8N_CHAT_WEBHOOK_URL": base + "/webhook/loomhaus-chat",
    "N8N_CHAT_TOKEN": env("LH_CHAT_TOKEN"),
    "N8N_ADMIN_WEBHOOK_URL": base + "/webhook/loomhaus-admin",
    "N8N_ADMIN_TOKEN": env("LH_ADMIN_TOKEN"),
    "DEMO_RESET_KEY": env("DEMO_RESET_KEY"),
}
(ROOT / "dashboard" / ".env.local").write_text("".join(f"{k}={v}\n" for k, v in VALUES.items()), encoding="utf-8")
print("wrote dashboard/.env.local")

if "--vercel" in sys.argv:
    cwd = ROOT / "dashboard"
    for k, v in VALUES.items():
        for target in ("production",):
            subprocess.run(["vercel", "env", "rm", k, target, "--yes"], cwd=cwd, capture_output=True, shell=True)
            r = subprocess.run(["vercel", "env", "add", k, target], cwd=cwd, input=v, text=True, capture_output=True,
                               shell=True)
            print(k, target, "ok" if r.returncode == 0 else f"FAILED: {r.stderr.strip()[-200:]}")
