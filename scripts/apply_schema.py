"""Apply supabase/schema.sql to the app's public schema (never touches schema n8n) and print a read-back."""
import psycopg

from lh import ROOT, env, save_result

sql = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
with psycopg.connect(env("supabase_db_url"), autocommit=True) as conn:
    conn.execute(sql)  # no params -> simple protocol, multiple statements allowed
    out = {
        "tables": [r[0] for r in conn.execute(
            "select table_name from information_schema.tables where table_schema='public' order by 1").fetchall()],
        "vector_ext": conn.execute("select extversion from pg_extension where extname='vector'").fetchone(),
        "realtime": [r[0] for r in conn.execute(
            "select tablename from pg_publication_tables where pubname='supabase_realtime' and schemaname='public'").fetchall()],
        "live_state": [list(r) for r in conn.execute("select product_id, status from public.live_state order by 1").fetchall()],
    }
print(out)
save_result("00_supabase_schema_readback.json", out)
