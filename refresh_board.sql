-- ============================================================
-- Refresh the scoring board
-- ============================================================
-- Run after each import (weekly). DB Browser > Execute SQL > paste > Run
-- > Write Changes. Safe to re-run: it only adds rows that are not on the
-- board yet, and never touches scores or decisions you already entered.
--
-- Adjust the two settings in the first block if the board gets too full.
-- ============================================================

-- Settings: how far back to look
--   trials registered (or, for AACT, started) within this many months
--   publications published within this many months
DROP TABLE IF EXISTS temp.board_settings;
CREATE TEMP TABLE board_settings AS
SELECT 36 AS trial_months,
       24 AS publication_months;

-- Regions treated as "underreported" in English-language AMR coverage.
-- Edit this list to match your own judgment.
DROP TABLE IF EXISTS temp.underreported;
CREATE TEMP TABLE underreported(region TEXT PRIMARY KEY);
INSERT INTO underreported VALUES
    ('China'), ('South Asia'), ('Japan'), ('South Korea'), ('Southeast Asia'),
    ('Middle East'), ('Africa'), ('Latin America');

-- 0. Rows already on the board whose region was unknown when they were
--    added: copy region/country from the source record now, and flag them
--    if that region is in the list above. Rows with a region are untouched.
UPDATE story_candidates
SET region = COALESCE(
        (SELECT t.region FROM trials t WHERE t.trial_id = story_candidates.trial_id),
        (SELECT e.region FROM entities e WHERE e.entity_id = story_candidates.entity_id),
        (SELECT p.region FROM publications p WHERE p.publication_id = story_candidates.publication_id)),
    country = COALESCE(country,
        (SELECT t.countries FROM trials t WHERE t.trial_id = story_candidates.trial_id),
        (SELECT e.country FROM entities e WHERE e.entity_id = story_candidates.entity_id),
        (SELECT p.lead_country FROM publications p WHERE p.publication_id = story_candidates.publication_id))
WHERE region IS NULL;

-- Flag existing rows from listed regions (only ever switches 0 -> 1).
UPDATE story_candidates
SET underreported_region = 1
WHERE underreported_region = 0
  AND region IN (SELECT region FROM underreported);

-- 1. Clinical trials (all registries)
INSERT INTO story_candidates
    (story_phase, working_title, region, country, found_via, source_url, trial_id, underreported_region)
SELECT
    'clinical trial',
    COALESCE(t.title, t.sponsor_name || ' trial ' || t.registry_id, t.registry_id),
    t.region,
    t.countries,
    COALESCE(t.registry, 'ClinicalTrials.gov'),
    t.source_url,
    t.trial_id,
    CASE WHEN t.region IN (SELECT region FROM underreported) THEN 1 ELSE 0 END
FROM trials t
WHERE t.trial_id NOT IN (SELECT trial_id FROM story_candidates WHERE trial_id IS NOT NULL)
  AND COALESCE(t.registered_date, t.start_date) >=
      date('now', '-' || (SELECT trial_months FROM board_settings) || ' months');

-- 2. Preclinical developers (entities with no row on the board yet)
--    Startups, spinouts and mid-size biotechs from every region, plus ALL
--    organisation types (academic groups, non-profits, government
--    institutes, large companies) from the underreported regions above.
INSERT INTO story_candidates
    (story_phase, working_title, region, country, found_via, source_url, entity_id, underreported_region)
SELECT
    'preclinical startup',
    e.name,
    e.region,
    e.country,
    COALESCE(e.discovered_via,
             CASE WHEN e.carb_x_funded = 1 THEN 'CARB-X'
                  WHEN e.gardp_funded = 1 THEN 'GARDP' END),
    e.website,
    e.entity_id,
    CASE WHEN e.region IN (SELECT region FROM underreported) THEN 1 ELSE 0 END
FROM entities e
WHERE NOT EXISTS (
        SELECT 1 FROM story_candidates c
        WHERE c.entity_id = e.entity_id AND c.story_phase = 'preclinical startup')
  AND (   COALESCE(e.entity_type, 'startup') IN ('startup', 'academic spinout', 'mid-size biotech')
       OR e.region IN (SELECT region FROM underreported));

-- 3. Academic findings
INSERT INTO story_candidates
    (story_phase, working_title, region, country, found_via, source_url, publication_id, underreported_region)
SELECT
    'academic finding',
    p.title,
    p.region,
    p.lead_country,
    p.found_via,
    p.source_url,
    p.publication_id,
    CASE WHEN p.region IN (SELECT region FROM underreported) THEN 1 ELSE 0 END
FROM publications p
WHERE p.publication_id NOT IN (SELECT publication_id FROM story_candidates WHERE publication_id IS NOT NULL)
  AND (p.pub_date IS NULL OR p.pub_date >=
       date('now', '-' || (SELECT publication_months FROM board_settings) || ' months'));

-- What is on the board now, per phase and decision
SELECT story_phase, decision, COUNT(*) AS candidates,
       SUM(underreported_region) AS from_underreported_regions
FROM story_candidates
GROUP BY story_phase, decision
ORDER BY story_phase, decision;
