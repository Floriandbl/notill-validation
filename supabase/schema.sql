-- =====================================================================
--  Supabase / Postgres schema for the tillage image-pair study.
--  Run this once in the Supabase SQL editor (Dashboard -> SQL -> New query).
--  Safe to re-run: tables use IF NOT EXISTS and functions use CREATE OR REPLACE.
--
--  Design notes
--  - NO per-pair labeler cap right now (each pair can be seen by any number of
--    people). One answer per person per pair is still enforced by the
--    unique(pair_id, respondent) constraint. To re-enable a cap, add a count
--    check back into submit_response() (see git history) and a `< N` filter in
--    claim_batch().
--  - claim_batch() hands out the least-labeled pairs first (spreads coverage)
--    and uses FOR UPDATE SKIP LOCKED so simultaneous requests don't collide.
--  - The browser uses only the public anon/publishable key and can ONLY call
--    the two functions below (RLS is on, no anon table policies), so respondent
--    names are never readable from the client. You (the researcher) read
--    responses with the service_role key from R.
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
  -- No per-pair labeler cap right now: only exclude pairs this person already
  -- answered, and hand out the least-labeled pairs first to spread coverage.
  select coalesce(jsonb_agg(t), '[]'::jsonb) into v_pairs
  from (
    select p.pair_id, p.province, p.year, p.image_a, p.image_b
    from public.pairs p
    where not exists (
        select 1 from public.responses r
        where r.pair_id = p.pair_id and r.respondent = p_name)
    order by (select count(*) from public.responses r where r.pair_id = p.pair_id) asc,
             p.pair_id
    limit greatest(1, least(p_size, 500))
    for update of p skip locked
  ) t;

  select count(*) into v_remaining
  from public.pairs p
  where not exists (
      select 1 from public.responses r
      where r.pair_id = p.pair_id and r.respondent = p_name);

  return jsonb_build_object('pairs', v_pairs, 'remaining', v_remaining);
end;
$$;

-- ---------- submit one answer (one per person; no per-pair cap right now) ----
-- Returns: { "ok": true }
--        | { "ok": true, "updated": true }      (re-answer by same person)
--        | { "ok": false, "reason": "unknown_pair" }
create or replace function public.submit_response(p_pair_id text, p_name text, p_answers jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
begin
  -- pair must exist; lock its row to serialise concurrent submits by the same person
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

  -- no per-pair labeler cap right now; one answer per person is still enforced
  -- by the unique(pair_id, respondent) constraint
  insert into public.responses(pair_id, respondent, answers)
  values (p_pair_id, p_name, p_answers);
  return jsonb_build_object('ok', true);

exception when unique_violation then
  -- same person raced two submits for this pair -> treat as a successful answer
  return jsonb_build_object('ok', true, 'updated', true);
end;
$$;

-- ---------- public progress (aggregate counts only; no names) -------
-- Returns headline study progress for the landing page. Exposes only counts,
-- never respondent names, so it is safe to call with the public anon key.
create or replace function public.study_progress()
returns jsonb
language sql
security definer
set search_path = public
stable
as $$
  with pd as (
    select p.province, p.year, p.pair_id, count(r.id) as lc
    from public.pairs p
    left join public.responses r on r.pair_id = p.pair_id
    group by p.province, p.year, p.pair_id
  ),
  cells as (
    select province, year, count(*) as total, count(*) filter (where lc > 0) as done
    from pd group by province, year
  )
  select jsonb_build_object(
    'contributors',  (select count(distinct respondent) from public.responses),
    'responses',     (select count(*) from public.responses),
    'pairs_total',   (select count(*) from pd),
    'pairs_done',    (select count(*) from pd where lc > 0),
    'cells_total',   (select count(*) from cells),
    'cells_started', (select count(*) from cells where done > 0),
    'cells_done',    (select count(*) from cells where total > 0 and done = total),
    'by_year', (
      select coalesce(jsonb_agg(jsonb_build_object('year', year, 'pairs', t, 'done', d)
                                order by year), '[]'::jsonb)
      from (select year, sum(total) as t, sum(done) as d from cells group by year) z)
  );
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
grant execute on function public.study_progress()                   to anon, authenticated;

-- =====================================================================
--  Loading the pairs:
--  Run r/build_pairs.R to produce either
--    - pairs_for_supabase.csv  (import via Table editor -> pairs -> Insert -> Import CSV)
--    - pairs_seed.sql          (paste & run here in the SQL editor)
-- =====================================================================
