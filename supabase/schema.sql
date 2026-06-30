-- =====================================================================
--  Supabase / Postgres schema for the tillage image-pair study.
--  Run this once in the Supabase SQL editor (Dashboard -> SQL -> New query).
--
--  Design notes
--  - The "max 2 labelers per pair" rule is enforced ATOMICALLY at write
--    time inside submit_response() (row lock on the pair). This is the
--    hard guarantee; concurrent users can never push a pair to 3.
--  - claim_batch() also uses FOR UPDATE SKIP LOCKED so two people asking
--    for a batch at the same instant are unlikely to be handed the same
--    pairs in the first place.
--  - The browser uses only the public "anon" key and can ONLY call the two
--    functions below (RLS is on, and there are no anon table policies), so
--    respondent names are never readable from the client. You (the
--    researcher) read responses with the service_role key from R.
-- =====================================================================

-- ---------- tables ---------------------------------------------------
create table if not exists public.pairs (
  pair_id   text primary key,
  province  text,
  year      int,
  image_a   text not null,   -- full https URL (jsDelivr CDN)
  image_b   text not null
);

create table if not exists public.responses (
  id          bigint generated always as identity primary key,
  pair_id     text not null references public.pairs(pair_id),
  respondent  text not null,
  answers     jsonb not null,            -- {"q_a":"till","q_b":"no_till"}
  created_at  timestamptz not null default now(),
  unique (pair_id, respondent)           -- one answer per person per pair
);

create index if not exists idx_responses_pair on public.responses(pair_id);
create index if not exists idx_responses_name on public.responses(respondent);

-- ---------- claim a batch -------------------------------------------
-- Returns: { "pairs": [ {pair_id, province, year, image_a, image_b}, ... ],
--            "remaining": <int> }
create or replace function public.claim_batch(p_name text, p_size int default 50)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_pairs jsonb;
  v_remaining int;
begin
  select coalesce(jsonb_agg(t), '[]'::jsonb) into v_pairs
  from (
    select p.pair_id, p.province, p.year, p.image_a, p.image_b
    from public.pairs p
    where (select count(*) from public.responses r where r.pair_id = p.pair_id) < 2
      and not exists (
        select 1 from public.responses r
        where r.pair_id = p.pair_id and r.respondent = p_name)
    order by (select count(*) from public.responses r where r.pair_id = p.pair_id) desc,
             p.pair_id
    limit greatest(1, least(p_size, 200))
    for update of p skip locked
  ) t;

  select count(*) into v_remaining
  from public.pairs p
  where (select count(*) from public.responses r where r.pair_id = p.pair_id) < 2
    and not exists (
      select 1 from public.responses r
      where r.pair_id = p.pair_id and r.respondent = p_name);

  return jsonb_build_object('pairs', v_pairs, 'remaining', v_remaining);
end;
$$;

-- ---------- submit one answer (atomic max-2 enforcement) ------------
-- Returns: { "ok": true }
--        | { "ok": true, "updated": true }      (re-answer by same person)
--        | { "ok": false, "reason": "pair_full" | "unknown_pair" }
create or replace function public.submit_response(p_pair_id text, p_name text, p_answers jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count int;
begin
  -- pair must exist; lock its row to serialise concurrent submits
  perform 1 from public.pairs where pair_id = p_pair_id for update;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'unknown_pair');
  end if;

  if exists (select 1 from public.responses
             where pair_id = p_pair_id and respondent = p_name) then
    update public.responses
       set answers = p_answers, created_at = now()
     where pair_id = p_pair_id and respondent = p_name;
    return jsonb_build_object('ok', true, 'updated', true);
  end if;

  select count(*) into v_count from public.responses where pair_id = p_pair_id;
  if v_count >= 2 then
    return jsonb_build_object('ok', false, 'reason', 'pair_full');
  end if;

  insert into public.responses(pair_id, respondent, answers)
  values (p_pair_id, p_name, p_answers);
  return jsonb_build_object('ok', true);

exception when unique_violation then
  return jsonb_build_object('ok', false, 'reason', 'pair_full');
end;
$$;

-- ---------- lock down direct table access ---------------------------
alter table public.pairs     enable row level security;
alter table public.responses enable row level security;
-- (no policies for anon/authenticated => the browser cannot read/write
--  tables directly; it can only call the two functions below.)

revoke all on public.pairs     from anon, authenticated;
revoke all on public.responses from anon, authenticated;

grant execute on function public.claim_batch(text, int)             to anon, authenticated;
grant execute on function public.submit_response(text, text, jsonb) to anon, authenticated;

-- =====================================================================
--  Loading the pairs:
--  Run r/build_pairs.R to produce either
--    - pairs_for_supabase.csv  (import via Table editor -> pairs -> Insert -> Import CSV)
--    - pairs_seed.sql          (paste & run here in the SQL editor)
-- =====================================================================
