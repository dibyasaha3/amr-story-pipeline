-- Run this against the AACT database (not your local SQLite file).
-- In pgAdmin: select the AACT server/database, open the Query Tool, paste
-- this in, and run it to see what it returns before using it from Python.
--
-- What it does: pulls interventional drug/biological trials whose condition
-- mentions resistance, plus each trial's lead sponsor name (so you can
-- later match it against known startups/companies in your entities table).
--
-- This is a STARTING FILTER, not a final one — AACT has no "is this AMR"
-- flag, so keyword matching on condition names is the best available proxy.
--
-- Uses ILIKE (case-insensitive) throughout, because AACT's enum casing
-- has changed over time (e.g. 'Interventional' vs 'INTERVENTIONAL') and an
-- exact-match filter on the wrong case silently returns zero rows.
--
-- Uses DISTINCT ON (s.nct_id) to collapse to one row per trial: a trial
-- can have several matching conditions or interventions, which would
-- otherwise duplicate the row in the result (harmless to your database
-- since nct_id is UNIQUE there, but wasteful and confusing to read).

WITH matched AS (
    SELECT DISTINCT ON (s.nct_id)
        s.nct_id,
        s.brief_title,
        s.phase,
        s.overall_status,
        s.study_type,
        s.start_date,
        s.completion_date,
        s.enrollment,
        sp.name AS sponsor_name
    FROM ctgov.studies s
    JOIN ctgov.conditions c
        ON c.nct_id = s.nct_id
    JOIN ctgov.interventions i
        ON i.nct_id = s.nct_id
    LEFT JOIN ctgov.sponsors sp
        ON sp.nct_id = s.nct_id
       AND sp.lead_or_collaborator ILIKE 'lead'
    WHERE s.study_type ILIKE 'interventional'
      AND i.intervention_type ILIKE ANY (ARRAY['drug', 'biological'])
      AND (
            c.downcase_name LIKE '%resistant%'
         OR c.downcase_name LIKE '%resistance%'
         OR c.downcase_name LIKE '%multidrug%'
         OR c.downcase_name LIKE '%mdr%'
         OR c.downcase_name LIKE '%carbapenem%'
         OR c.downcase_name LIKE '%mrsa%'
         OR c.downcase_name LIKE '%extensively drug%'
      )
    ORDER BY s.nct_id, s.start_date DESC
)
SELECT * FROM matched
ORDER BY start_date DESC;
