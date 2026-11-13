-- Run this in DB Browser's "Execute SQL" tab against amr_pipeline.db,
-- AFTER you have run migrate_v2.sql, re-run ingest.py to backfill
-- sponsor_name, and run seed_entities.sql.
--
-- What it does: for every trial sponsor name in your database, shows
-- whether it loosely matches one of your curated CARB-X entities. This is
-- a REVIEW list, not an automatic link -- company names in AACT rarely
-- match CARB-X's naming exactly (legal entity names, subsidiaries, typos),
-- so check each match by eye before trusting it.

SELECT
    t.trial_id,
    t.nct_id,
    t.sponsor_name,
    e.entity_id AS possible_entity_id,
    e.name AS possible_entity_match
FROM trials t
LEFT JOIN entities e
    ON t.sponsor_name LIKE '%' || e.name || '%'
    OR e.name LIKE '%' || t.sponsor_name || '%'
WHERE t.sponsor_name IS NOT NULL
ORDER BY possible_entity_match IS NULL, t.sponsor_name;

-- Rows with a non-null possible_entity_match are candidates to link.
-- To link a confirmed match, find the trial_id and entity_id from the
-- result above, then (one asset per distinct drug/vaccine candidate --
-- several trials can share one asset):
--
--   INSERT INTO assets (entity_id, name, modality, mechanism_of_action, target_pathogen)
--   VALUES (<entity_id>, '<asset name, e.g. the drug/vaccine candidate name>',
--           '<small molecule | vaccine | biologic | phage | antibody | other>',
--           '<what you know about mechanism>', '<target pathogen>');
--
--   UPDATE trials SET asset_id = (SELECT last_insert_rowid()) WHERE trial_id = <trial_id>;
--
-- Do this trial by trial as you confirm each match -- it's deliberately
-- manual, since this is the step where your judgment about what counts
-- as a genuine match belongs, not an automated guess.
