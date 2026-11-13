-- ============================================================
-- Upgrade v4: add 'irrelevant' as a decision value
-- ============================================================
-- Run ONCE against your existing amr_pipeline.db:
--   1. Make a backup copy of amr_pipeline.db first (copy-paste the file).
--   2. DB Browser > "Execute SQL" tab > paste this whole file > Run (play button).
--   3. Click "Write Changes".
--
-- Why a migration is needed at all: SQLite cannot alter a CHECK constraint
-- in place, so this rebuilds story_candidates with the wider constraint,
-- copies every existing row across unchanged, then drops the old table
-- and renames the new one into its place. No data is lost; the
-- scoring_board view keeps working afterward since it refers to the table
-- by name, not by its internal identity.
--
-- 'irrelevant' is distinct from 'dropped': use 'dropped' for a candidate
-- you scored and decided not to pursue; use 'irrelevant' for a false
-- positive that never deserved scoring in the first place (e.g. a keyword
-- match that turned out not to be an AMR trial at all).
-- ============================================================

PRAGMA foreign_keys = OFF;

-- Must drop the view BEFORE dropping story_candidates below: SQLite
-- refuses to drop a table that a view still refers to.
DROP VIEW IF EXISTS scoring_board;

CREATE TABLE story_candidates_new (
    candidate_id          INTEGER PRIMARY KEY,
    story_phase           TEXT NOT NULL
                          CHECK (story_phase IN ('preclinical startup', 'clinical trial', 'academic finding')),
    decision              TEXT NOT NULL DEFAULT 'to review'
                          CHECK (decision IN ('to review', 'shortlist', 'writing', 'published', 'dropped', 'irrelevant')),
    working_title         TEXT,
    region                TEXT,
    country               TEXT,
    found_via             TEXT,
    source_url            TEXT,

    entity_id             INTEGER REFERENCES entities(entity_id),
    asset_id              INTEGER REFERENCES assets(asset_id),
    trial_id              INTEGER UNIQUE REFERENCES trials(trial_id),
    publication_id        INTEGER UNIQUE REFERENCES publications(publication_id),

    tier1_mechanism       INTEGER CHECK (tier1_mechanism      IN (0, 1, 2)),
    tier1_pathogen        INTEGER CHECK (tier1_pathogen       IN (0, 2)),
    tier1_overlap         INTEGER CHECK (tier1_overlap        IN (0, 1, 2)),
    tier2_status_change   INTEGER CHECK (tier2_status_change  IN (0, 1, 2)),
    tier2_first_in_class  INTEGER CHECK (tier2_first_in_class IN (0, 1, 2)),
    tier2_sponsor_stage   INTEGER CHECK (tier2_sponsor_stage  IN (0, 1, 2)),
    tier3_open_question   INTEGER CHECK (tier3_open_question  IN (0, 1, 2)),
    tier3_comparability   INTEGER CHECK (tier3_comparability  IN (0, 2)),

    underreported_region  INTEGER NOT NULL DEFAULT 0 CHECK (underreported_region IN (0, 1)),

    notes                 TEXT,
    added_at              TEXT DEFAULT (datetime('now'))
);

INSERT INTO story_candidates_new SELECT * FROM story_candidates;

DROP TABLE story_candidates;
ALTER TABLE story_candidates_new RENAME TO story_candidates;

CREATE INDEX IF NOT EXISTS idx_candidates_phase ON story_candidates(story_phase, decision);

PRAGMA foreign_keys = ON;

-- Recreate the view so it is bound fresh to the rebuilt table, and push
-- 'irrelevant' rows to the bottom of the ranking alongside 'dropped'.
CREATE VIEW scoring_board AS
SELECT
    candidate_id,
    story_phase,
    decision,
    working_title,
    region,
    underreported_region,
    COALESCE(tier1_mechanism, 0) + COALESCE(tier1_pathogen, 0) + COALESCE(tier1_overlap, 0)
  + COALESCE(tier2_status_change, 0) + COALESCE(tier2_first_in_class, 0) + COALESCE(tier2_sponsor_stage, 0)
  + COALESCE(tier3_open_question, 0) + COALESCE(tier3_comparability, 0)            AS total_score,
    (tier1_mechanism IS NOT NULL) + (tier1_pathogen IS NOT NULL) + (tier1_overlap IS NOT NULL)
  + (tier2_status_change IS NOT NULL) + (tier2_first_in_class IS NOT NULL) + (tier2_sponsor_stage IS NOT NULL)
  + (tier3_open_question IS NOT NULL) + (tier3_comparability IS NOT NULL)          AS criteria_scored,
    found_via,
    source_url,
    notes
FROM story_candidates
ORDER BY
    story_phase,
    CASE decision WHEN 'writing' THEN 0 WHEN 'shortlist' THEN 1 WHEN 'to review' THEN 2
                  WHEN 'published' THEN 3 WHEN 'dropped' THEN 4 ELSE 5 END,
    total_score DESC;
