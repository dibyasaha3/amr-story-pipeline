-- ============================================================
-- Upgrade v3: global sources + decision table
-- ============================================================
-- Run ONCE against your existing amr_pipeline.db:
--   1. Make a backup copy of amr_pipeline.db first (copy-paste the file).
--   2. DB Browser > "Execute SQL" tab > paste this whole file > Run (play button).
--   3. Click "Write Changes".
--
-- It does not delete or change any existing rows. It only ADDS columns,
-- tables and a view. Running it a second time will stop with
-- "duplicate column name": that is harmless and means it already ran.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ---------- 1. Trials: make room for non-ClinicalTrials.gov registries ----------
-- Every existing row came from AACT, so they default to 'ClinicalTrials.gov'.
ALTER TABLE trials ADD COLUMN registry        TEXT DEFAULT 'ClinicalTrials.gov'; -- e.g. 'ChiCTR', 'CTRI', 'jRCT'
ALTER TABLE trials ADD COLUMN registry_id     TEXT;  -- the ID in that registry, e.g. ChiCTR2400081234 (equals nct_id for AACT rows)
ALTER TABLE trials ADD COLUMN title           TEXT;
ALTER TABLE trials ADD COLUMN condition_text  TEXT;
ALTER TABLE trials ADD COLUMN intervention_text TEXT;
ALTER TABLE trials ADD COLUMN countries       TEXT;  -- as given by the registry, e.g. 'China;Thailand'
ALTER TABLE trials ADD COLUMN region          TEXT;  -- coarse label used for filtering, e.g. 'China', 'South Asia'
ALTER TABLE trials ADD COLUMN registered_date TEXT;
ALTER TABLE trials ADD COLUMN secondary_ids   TEXT;  -- other IDs for the same trial (how duplicates are caught)
ALTER TABLE trials ADD COLUMN source_url      TEXT;

UPDATE trials
SET registry_id = nct_id,
    source_url  = 'https://clinicaltrials.gov/study/' || nct_id
WHERE registry_id IS NULL AND nct_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_trials_registry_id ON trials(registry_id);

-- AACT titles were only ever saved inside the 'new_trial' event text.
-- Copy them into the new title column so the board shows a readable name.
UPDATE trials
SET title = (
    SELECT substr(e.description, 23)
    FROM events e
    WHERE e.trial_id = trials.trial_id
      AND e.event_type = 'new_trial'
      AND e.description LIKE 'New trial registered: %'
    ORDER BY e.event_id LIMIT 1)
WHERE title IS NULL;

-- ...and keep doing that for future ingest.py runs.
CREATE TRIGGER IF NOT EXISTS trg_events_fill_trial_title
AFTER INSERT ON events
WHEN NEW.event_type = 'new_trial' AND NEW.description LIKE 'New trial registered: %'
BEGIN
    UPDATE trials SET title = substr(NEW.description, 23)
    WHERE trial_id = NEW.trial_id AND title IS NULL;
END;

-- Keeps ingest.py (AACT) working unchanged: any new AACT row gets its
-- registry_id and link filled in automatically.
CREATE TRIGGER IF NOT EXISTS trg_trials_fill_registry_id
AFTER INSERT ON trials
WHEN NEW.registry_id IS NULL AND NEW.nct_id IS NOT NULL
BEGIN
    UPDATE trials
    SET registry_id = NEW.nct_id,
        source_url  = 'https://clinicaltrials.gov/study/' || NEW.nct_id
    WHERE trial_id = NEW.trial_id;
END;

-- ---------- 2. Entities: record region and where you found them ----------
ALTER TABLE entities ADD COLUMN region         TEXT;  -- e.g. 'China', 'South Asia', 'Europe'
ALTER TABLE entities ADD COLUMN discovered_via TEXT;  -- e.g. 'CARB-X', 'WHO preclinical 2025', 'C-CAMP', 'China pipeline review 2024'

-- ---------- 3. Publications: academic findings (new) ----------
-- Note: the existing `articles` table is for YOUR published scicomm pieces.
CREATE TABLE IF NOT EXISTS publications (
    publication_id   INTEGER PRIMARY KEY,
    pmid             TEXT UNIQUE,
    doi              TEXT,
    title            TEXT NOT NULL,
    journal          TEXT,
    pub_date         TEXT,
    first_author     TEXT,
    lead_country     TEXT,   -- country of the corresponding or last author's institution
    region           TEXT,
    pub_type         TEXT,   -- 'peer-reviewed' or 'preprint'
    finding_summary  TEXT,   -- one or two lines in plain language
    source_url       TEXT,
    found_via        TEXT,   -- e.g. 'PubMed search 2026-11-05, China affiliation'
    added_at         TEXT DEFAULT (datetime('now'))
);

-- ---------- 4. The decision table ----------
-- One row per possible story. You fill the score columns by typing into
-- the cells in DB Browser's "Browse Data" tab. The allowed values are
-- enforced: a typo like 3 in a 0-2 column is refused.
CREATE TABLE IF NOT EXISTS story_candidates (
    candidate_id          INTEGER PRIMARY KEY,
    story_phase           TEXT NOT NULL
                          CHECK (story_phase IN ('preclinical startup', 'clinical trial', 'academic finding')),
    decision              TEXT NOT NULL DEFAULT 'to review'
                          CHECK (decision IN ('to review', 'shortlist', 'writing', 'published', 'dropped')),
    working_title         TEXT,
    region                TEXT,
    country               TEXT,
    found_via             TEXT,
    source_url            TEXT,

    -- links back to the underlying record (only one is normally filled)
    entity_id             INTEGER REFERENCES entities(entity_id),
    asset_id              INTEGER REFERENCES assets(asset_id),
    trial_id              INTEGER UNIQUE REFERENCES trials(trial_id),
    publication_id        INTEGER UNIQUE REFERENCES publications(publication_id),

    -- your 16-point rubric (same criteria and scales as the scores table)
    tier1_mechanism       INTEGER CHECK (tier1_mechanism      IN (0, 1, 2)),
    tier1_pathogen        INTEGER CHECK (tier1_pathogen       IN (0, 2)),
    tier1_overlap         INTEGER CHECK (tier1_overlap        IN (0, 1, 2)),
    tier2_status_change   INTEGER CHECK (tier2_status_change  IN (0, 1, 2)),
    tier2_first_in_class  INTEGER CHECK (tier2_first_in_class IN (0, 1, 2)),
    tier2_sponsor_stage   INTEGER CHECK (tier2_sponsor_stage  IN (0, 1, 2)),
    tier3_open_question   INTEGER CHECK (tier3_open_question  IN (0, 1, 2)),
    tier3_comparability   INTEGER CHECK (tier3_comparability  IN (0, 2)),

    -- kept OUT of the total on purpose: a filter, not a merit score
    underreported_region  INTEGER NOT NULL DEFAULT 0 CHECK (underreported_region IN (0, 1)),

    notes                 TEXT,
    added_at              TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_candidates_phase ON story_candidates(story_phase, decision);

-- ---------- 5. The view you actually look at ----------
-- Read-only: scores are typed into story_candidates, and this view
-- adds them up and sorts them. Open it under Browse Data > Table: scoring_board.
DROP VIEW IF EXISTS scoring_board;
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
  + (tier3_open_question IS NOT NULL) + (tier3_comparability IS NOT NULL)          AS criteria_scored,  -- out of 8
    found_via,
    source_url,
    notes
FROM story_candidates
ORDER BY
    story_phase,
    CASE decision WHEN 'writing' THEN 0 WHEN 'shortlist' THEN 1 WHEN 'to review' THEN 2
                  WHEN 'published' THEN 3 ELSE 4 END,
    total_score DESC;
