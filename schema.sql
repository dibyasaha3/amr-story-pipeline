-- AMR Startup Pipeline: starter schema
-- Run once to create your personal database. Re-running this file is safe
-- (IF NOT EXISTS guards against accidentally wiping existing data).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS entities (
    entity_id       INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    entity_type     TEXT,              -- 'startup', 'academic spinout', 'mid-size biotech', 'large pharma'
    country         TEXT,
    founded_year    INTEGER,
    carb_x_funded   INTEGER DEFAULT 0, -- 0/1 boolean
    gardp_funded    INTEGER DEFAULT 0, -- 0/1 boolean
    website         TEXT,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assets (
    asset_id             INTEGER PRIMARY KEY,
    entity_id            INTEGER REFERENCES entities(entity_id),
    name                 TEXT NOT NULL,
    modality             TEXT,  -- 'small molecule', 'vaccine', 'biologic', 'phage', 'antibody', 'other'
    mechanism_of_action  TEXT,
    target_pathogen      TEXT,
    who_priority_pathogen INTEGER DEFAULT 0,
    notes                TEXT,
    created_at           TEXT DEFAULT (datetime('now')),
    updated_at           TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trials (
    trial_id          INTEGER PRIMARY KEY,
    asset_id          INTEGER REFERENCES assets(asset_id),
    nct_id            TEXT UNIQUE,     -- the AACT/ClinicalTrials.gov identifier, e.g. NCT01234567
    phase             TEXT,
    status            TEXT,
    start_date        TEXT,
    completion_date   TEXT,
    enrollment        INTEGER,
    sponsor_name      TEXT,            -- lead sponsor name as given by AACT, unmatched to an entity until curated
    comparator        TEXT,
    primary_endpoint  TEXT,
    last_checked      TEXT,            -- date you last verified this row against AACT
    created_at        TEXT DEFAULT (datetime('now')),
    updated_at        TEXT DEFAULT (datetime('now'))
);

-- The audit trail: every ingestion run logs what changed here.
-- This is what lets you ask "what's new since last week" and what
-- the verification pass checks against.
CREATE TABLE IF NOT EXISTS events (
    event_id      INTEGER PRIMARY KEY,
    entity_id     INTEGER REFERENCES entities(entity_id),
    asset_id      INTEGER REFERENCES assets(asset_id),
    trial_id      INTEGER REFERENCES trials(trial_id),
    event_type    TEXT,   -- 'new_trial', 'phase_change', 'status_change', 'funding', 'termination', 'other'
    event_date    TEXT,
    description   TEXT,
    source_url    TEXT,
    logged_at     TEXT DEFAULT (datetime('now'))
);

-- One row per time you score a candidate against the rubric.
-- Keeping history (rather than overwriting) lets you see if a
-- candidate's score changed as new events came in.
CREATE TABLE IF NOT EXISTS scores (
    score_id              INTEGER PRIMARY KEY,
    asset_id              INTEGER REFERENCES assets(asset_id),
    tier1_mechanism       INTEGER,  -- 0, 1, or 2
    tier1_pathogen        INTEGER,  -- 0 or 2
    tier1_overlap         INTEGER,  -- 0, 1, or 2
    tier2_status_change   INTEGER,  -- 0, 1, or 2
    tier2_first_in_class  INTEGER,  -- 0, 1, or 2
    tier2_sponsor_stage   INTEGER,  -- 0, 1, or 2
    tier3_open_question   INTEGER,  -- 0, 1, or 2
    tier3_comparability   INTEGER,  -- 0 or 2
    total_score           INTEGER,  -- sum of the above, out of 16
    scored_at             TEXT DEFAULT (datetime('now')),
    notes                 TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    article_id      INTEGER PRIMARY KEY,
    asset_id        INTEGER REFERENCES assets(asset_id),
    title           TEXT,
    published_date  TEXT,
    url             TEXT,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_assets_entity ON assets(entity_id);
CREATE INDEX IF NOT EXISTS idx_trials_asset ON trials(asset_id);
CREATE INDEX IF NOT EXISTS idx_events_asset ON events(asset_id);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_scores_asset ON scores(asset_id);
