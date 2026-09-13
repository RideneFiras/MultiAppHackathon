"""Embed kb/*.md (one chunk per '##' section) with OpenAI text-embedding-3-small into public.documents.

Idempotent: replaces all rows. Read-back: runs match_documents for a probe question and saves the evidence.
"""
import json
import re

import psycopg

from lh import ROOT, env, http, save_result

OPENAI = {"Authorization": f"Bearer {env('openai')}"}


def chunks():
    for f in sorted((ROOT / "kb").glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = re.match(r"#\s+(.+)", text)
        title = m.group(1).strip() if m else f.stem
        parts = re.split(r"\n(?=## )", text)
        if len(parts) == 1:
            yield f.name, title, text.strip()
            continue
        if len(parts[0].strip().splitlines()) > 1:
            yield f.name, title, parts[0].strip()
        for p in parts[1:]:
            yield f.name, title, f"# {title}\n{p.strip()}"


def embed(texts):
    st, body = http("POST", "https://api.openai.com/v1/embeddings",
                    {"model": "text-embedding-3-small", "input": texts}, OPENAI)
    assert st == 200, body
    return [d["embedding"] for d in body["data"]]


def vec(e):
    return "[" + ",".join(f"{x:.7f}" for x in e) + "]"


items = list(chunks())
embs = embed([c[2] for c in items])
with psycopg.connect(env("supabase_db_url"), autocommit=True) as conn:
    conn.execute("delete from public.documents")
    for (fname, title, content), e in zip(items, embs):
        conn.execute("insert into public.documents (content, metadata, embedding) values (%s, %s, %s::extensions.vector)",
                     (content, json.dumps({"source": fname, "title": title}), vec(e)))
    count = conn.execute("select count(*) from public.documents").fetchone()[0]
    probe = "What is your return policy?"
    rows = conn.execute("select metadata->>'source', round(similarity::numeric, 3) from public.match_documents(%s::extensions.vector, 4)",
                        (vec(embed([probe])[0]),)).fetchall()
out = {"chunks": count, "probe": probe, "top4": [list(map(str, r)) for r in rows]}
print(out)
save_result("00_kb_ingest_readback.json", out)
