-- =====================================================================
--  EXPORT THE ANSWERS FROM SUPABASE, ready for r/analyze_responses.R
--
--  Do NOT use the Table Editor's "Export -> CSV" button on the responses
--  table. That dumps the raw table, where every answer is still buried in
--  a JSON blob:
--      id, pair_id, respondent, answers, created_at, meta, ip
--  r/analyze_responses.R expects one column per question, and a field_id:
--      field_id, province, year, respondent, created_at, ip, q_field, q_when, meta_*
--  Feeding it the raw dump kills it at line 22 with
--      "Error in tapply(...): arguments must have same length"
--  because d$field_id is NULL.
--
--  This query produces exactly the columns export_responses.py produces, so
--  the R script runs on it unchanged.
--
--  HOW TO USE
--    1. Supabase dashboard -> SQL Editor -> New query
--    2. Paste this whole file, Run
--    3. "Download CSV" on the results
--    4. Save it next to the project as responses_export.csv
--    5. Rscript r/analyze_responses.R
-- =====================================================================

select
  r.pair_id                            as field_id,
  p.province,
  p.year,
  r.respondent,
  r.created_at,
  r.ip,
  -- one column per question. Add a line here if you add a question to config.js.
  r.answers ->> 'q_field'              as q_field,
  r.answers ->> 'q_when'               as q_when,
  -- device / context, flattened the same way export_responses.py flattens it
  r.meta ->> 'timezone'                as meta_timezone,
  r.meta ->> 'tz_offset_min'           as meta_tz_offset_min,
  r.meta ->> 'client_time'             as meta_client_time,
  r.meta ->> 'platform'                as meta_platform,
  r.meta ->> 'language'                as meta_language,
  r.meta ->> 'screen'                  as meta_screen,
  r.meta ->> 'user_agent'              as meta_user_agent
from public.responses r
left join public.pairs p on p.pair_id = r.pair_id
order by r.created_at;
