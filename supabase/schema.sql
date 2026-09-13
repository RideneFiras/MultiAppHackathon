-- Loomhaus hackathon: Supabase schema
-- 1) RAG knowledge base (pgvector) used by the answer_from_kb subagent
-- 2) Dashboard echo tables (Path B) mirrored from n8n after every real Sheets/Notion write
-- Safe to re-run.

create extension if not exists vector with schema extensions;

-- ---------- RAG ----------
create table if not exists public.documents (
  id bigserial primary key,
  content text,
  metadata jsonb,
  embedding extensions.vector(1536)   -- OpenAI text-embedding-3-small
);

create or replace function public.match_documents (
  query_embedding extensions.vector(1536),
  match_count int default null,
  filter jsonb default '{}'
) returns table (id bigint, content text, metadata jsonb, similarity float)
language plpgsql
set search_path = public, extensions
as $$
#variable_conflict use_column
begin
  return query
  select id, content, metadata, 1 - (documents.embedding <=> query_embedding) as similarity
  from documents
  where metadata @> filter
  order by documents.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- ---------- Dashboard echo (Path B) ----------
-- live_state mirrors the Google Sheet rows for the dashboard's team view (stock, pending, coarse status).
-- The customer-facing agent never receives these numbers; only the dashboard shows them.
create table if not exists public.live_state (
  product_id   text primary key,
  product_name text not null,
  status       text not null check (status in ('Available','Limited','Pending team review')),
  last_event   text,
  updated_at   timestamptz not null default now()
);
alter table public.live_state add column if not exists stock int;
alter table public.live_state add column if not exists pending int;
alter table public.live_state add column if not exists sheet_row int;

create table if not exists public.order_feed (
  notion_page_id   text primary key,
  order_ref        text,
  customer_display text,          -- masked in n8n, e.g. "Firas R." (no contact details ever)
  product_name     text,
  quantity         int,
  status           text,          -- Pending / Fulfilled / Follow-up / Sync Error
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create table if not exists public.agent_trace (
  id         bigserial primary key,
  session_id text,
  intent     text,
  path       text,                -- e.g. "prefilter → refuse" or "check_inventory → capture_order"
  created_at timestamptz not null default now()
);

-- Failure log for the reliability story (written best-effort by n8n error branches)
create table if not exists public.sync_log (
  id         bigserial primary key,
  workflow   text,
  step       text,
  level      text,
  detail     jsonb,
  created_at timestamptz not null default now()
);

-- ---------- RLS: public read-only for the three dashboard tables; everything else service-role only ----------
alter table public.documents   enable row level security;
alter table public.live_state  enable row level security;
alter table public.order_feed  enable row level security;
alter table public.agent_trace enable row level security;
alter table public.sync_log    enable row level security;

drop policy if exists "public read live_state"  on public.live_state;
drop policy if exists "public read order_feed"  on public.order_feed;
drop policy if exists "public read agent_trace" on public.agent_trace;
create policy "public read live_state"  on public.live_state  for select to anon, authenticated using (true);
create policy "public read order_feed"  on public.order_feed  for select to anon, authenticated using (true);
create policy "public read agent_trace" on public.agent_trace for select to anon, authenticated using (true);

-- ---------- Realtime ----------
do $$
declare t text;
begin
  foreach t in array array['live_state','order_feed','agent_trace'] loop
    if not exists (select 1 from pg_publication_tables
                   where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;

-- ---------- Seed (matches the clean demo starting state of the Google Sheet) ----------
insert into public.live_state (product_id, product_name, stock, pending, sheet_row, status, last_event) values
  ('LH-HOOD-BLU', 'Harbor Blue Hoodie',         2, 0, 2, 'Limited',   'seed'),
  ('LH-TEE-WHT',  'Everyday White Tee',        40, 0, 3, 'Available', 'seed'),
  ('LH-JKT-DNM',  'Selvedge Denim Jacket',      6, 0, 4, 'Available', 'seed'),
  ('LH-BEAN-GRY', 'Merino Rib Beanie',          3, 0, 5, 'Limited',   'seed'),
  ('LH-TOTE-NAT', 'Heavy Canvas Tote',         25, 0, 6, 'Available', 'seed'),
  ('LH-SOCK-3PK', 'Trail Crew Socks (3-Pack)', 12, 0, 7, 'Available', 'seed')
on conflict (product_id) do update
  set product_name = excluded.product_name, stock = excluded.stock, pending = excluded.pending,
      sheet_row = excluded.sheet_row, status = excluded.status,
      last_event = excluded.last_event, updated_at = now();

-- ---------- Echo RPC (Path B) ----------
-- One call per n8n event: upserts order_feed / live_state, appends agent_trace / sync_log.
-- service_role only; n8n calls it best-effort AFTER the real Notion/Sheets writes (continue-on-fail).
create or replace function public.echo_event(p jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  insert into public.order_feed (notion_page_id, order_ref, customer_display, product_name, quantity, status, updated_at)
  select e->>'notion_page_id', e->>'order_ref', e->>'customer_display', e->>'product_name',
         nullif(e->>'quantity','')::int, e->>'status', now()
  from jsonb_array_elements(coalesce(p->'orders', '[]'::jsonb)) e
  where coalesce(e->>'notion_page_id','') <> ''
  on conflict (notion_page_id) do update
    set order_ref = coalesce(excluded.order_ref, order_feed.order_ref),
        customer_display = coalesce(excluded.customer_display, order_feed.customer_display),
        product_name = coalesce(excluded.product_name, order_feed.product_name),
        quantity = coalesce(excluded.quantity, order_feed.quantity),
        status = excluded.status, updated_at = now();

  -- only rows whose values changed are written, so the 30 s Sheet mirror doesn't spam Realtime
  insert into public.live_state (product_id, product_name, stock, pending, sheet_row, status, last_event, updated_at)
  select e->>'product_id', e->>'product_name', nullif(e->>'stock','')::int, nullif(e->>'pending','')::int,
         nullif(e->>'sheet_row','')::int, e->>'status', e->>'last_event', now()
  from jsonb_array_elements(coalesce(p->'lives', '[]'::jsonb)) e
  where coalesce(e->>'product_id','') <> ''
  on conflict (product_id) do update
    set product_name = excluded.product_name,
        stock = coalesce(excluded.stock, live_state.stock),
        pending = coalesce(excluded.pending, live_state.pending),
        sheet_row = coalesce(excluded.sheet_row, live_state.sheet_row),
        status = excluded.status, last_event = excluded.last_event, updated_at = now()
    where live_state.product_name is distinct from excluded.product_name
       or live_state.status is distinct from excluded.status
       or live_state.stock is distinct from coalesce(excluded.stock, live_state.stock)
       or live_state.pending is distinct from coalesce(excluded.pending, live_state.pending)
       or live_state.sheet_row is distinct from coalesce(excluded.sheet_row, live_state.sheet_row);

  insert into public.agent_trace (session_id, intent, path)
  select e->>'session_id', e->>'intent', e->>'path'
  from jsonb_array_elements(coalesce(p->'traces', '[]'::jsonb)) e;

  insert into public.sync_log (workflow, step, level, detail)
  select e->>'workflow', e->>'step', coalesce(e->>'level','error'), e->'detail'
  from jsonb_array_elements(coalesce(p->'logs', '[]'::jsonb)) e;

  return jsonb_build_object('ok', true);
end $$;

-- Demo reset: clears the dashboard feed. live_state is re-synced from the Sheet by n8n right after,
-- and sync_log is kept (it's the failure history, not demo data).
create or replace function public.reset_dashboard() returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  delete from public.order_feed where true;
  delete from public.agent_trace where true;
  return jsonb_build_object('ok', true);
end $$;

revoke all on function public.echo_event(jsonb) from public, anon, authenticated;
revoke all on function public.reset_dashboard() from public, anon, authenticated;
grant execute on function public.echo_event(jsonb) to service_role;
grant execute on function public.reset_dashboard() to service_role;
revoke all on function public.match_documents(extensions.vector, int, jsonb) from public, anon, authenticated;
grant execute on function public.match_documents(extensions.vector, int, jsonb) to service_role;

notify pgrst, 'reload schema';
