-- ============================================================
-- Database health check
-- ============================================================
-- Lists every column that ingest.py, ingest_ictrp.py, refresh_board.sql,
-- match_sponsors.sql or seed_entities.sql needs but your database is missing.
--
-- How to use (DB Browser):
--   1. Execute SQL tab > open this file > press play.
--   2. EMPTY result  = your database is complete. Nothing to do.
--      ROWS returned = copy every line of the "fix" column into a new
--      Execute SQL tab, press play, then click "Write Changes".
--   3. Run this file again; it should now return nothing.
--
-- Read-only: this file changes nothing by itself.
-- ============================================================

WITH expected(table_name, column_name, column_type, added_by) AS (VALUES
    -- trials: original schema
    ('trials', 'trial_id',          'INTEGER', 'schema.sql'),
    ('trials', 'asset_id',          'INTEGER', 'schema.sql'),
    ('trials', 'nct_id',            'TEXT',    'schema.sql'),
    ('trials', 'phase',             'TEXT',    'schema.sql'),
    ('trials', 'status',            'TEXT',    'schema.sql'),
    ('trials', 'start_date',        'TEXT',    'schema.sql'),
    ('trials', 'completion_date',   'TEXT',    'schema.sql'),
    ('trials', 'enrollment',        'INTEGER', 'schema.sql'),
    ('trials', 'comparator',        'TEXT',    'schema.sql'),
    ('trials', 'primary_endpoint',  'TEXT',    'schema.sql'),
    ('trials', 'last_checked',      'TEXT',    'schema.sql'),
    ('trials', 'created_at',        'TEXT',    'schema.sql'),
    ('trials', 'updated_at',        'TEXT',    'schema.sql'),
    -- trials: upgrade v2
    ('trials', 'sponsor_name',      'TEXT',    'migrate_v2.sql'),
    -- trials: upgrade v3
    ('trials', 'registry',          'TEXT DEFAULT ''ClinicalTrials.gov''', 'migrate_v3.sql'),
    ('trials', 'registry_id',       'TEXT',    'migrate_v3.sql'),
    ('trials', 'title',             'TEXT',    'migrate_v3.sql'),
    ('trials', 'condition_text',    'TEXT',    'migrate_v3.sql'),
    ('trials', 'intervention_text', 'TEXT',    'migrate_v3.sql'),
    ('trials', 'countries',         'TEXT',    'migrate_v3.sql'),
    ('trials', 'region',            'TEXT',    'migrate_v3.sql'),
    ('trials', 'registered_date',   'TEXT',    'migrate_v3.sql'),
    ('trials', 'secondary_ids',     'TEXT',    'migrate_v3.sql'),
    ('trials', 'source_url',        'TEXT',    'migrate_v3.sql'),
    -- events
    ('events', 'trial_id',          'INTEGER', 'schema.sql'),
    ('events', 'event_type',        'TEXT',    'schema.sql'),
    ('events', 'event_date',        'TEXT',    'schema.sql'),
    ('events', 'description',       'TEXT',    'schema.sql'),
    ('events', 'source_url',        'TEXT',    'schema.sql'),
    -- entities
    ('entities', 'name',            'TEXT',    'schema.sql'),
    ('entities', 'entity_type',     'TEXT',    'schema.sql'),
    ('entities', 'country',         'TEXT',    'schema.sql'),
    ('entities', 'carb_x_funded',   'INTEGER DEFAULT 0', 'schema.sql'),
    ('entities', 'gardp_funded',    'INTEGER DEFAULT 0', 'schema.sql'),
    ('entities', 'website',         'TEXT',    'schema.sql'),
    ('entities', 'notes',           'TEXT',    'schema.sql'),
    ('entities', 'region',          'TEXT',    'migrate_v3.sql'),
    ('entities', 'discovered_via',  'TEXT',    'migrate_v3.sql'),
    -- assets (used by match_sponsors.sql)
    ('assets', 'entity_id',         'INTEGER', 'schema.sql'),
    ('assets', 'name',              'TEXT',    'schema.sql'),
    ('assets', 'modality',          'TEXT',    'schema.sql'),
    ('assets', 'mechanism_of_action', 'TEXT',  'schema.sql'),
    ('assets', 'target_pathogen',   'TEXT',    'schema.sql'),
    -- tables created whole by migrate_v3.sql (spot-check one column each)
    ('publications',     'publication_id',     'INTEGER', 'migrate_v3.sql'),
    ('story_candidates', 'candidate_id',       'INTEGER', 'migrate_v3.sql'),
    ('story_candidates', 'underreported_region', 'INTEGER', 'migrate_v3.sql')
)
SELECT
    e.table_name,
    e.column_name,
    e.added_by,
    CASE
        WHEN NOT EXISTS (SELECT 1 FROM sqlite_master m WHERE m.type = 'table' AND m.name = e.table_name)
            THEN '-- whole table missing: run ' || e.added_by
        ELSE 'ALTER TABLE ' || e.table_name || ' ADD COLUMN ' || e.column_name || ' ' || e.column_type || ';'
    END AS fix
FROM expected e
WHERE e.column_name NOT IN (SELECT p.name FROM pragma_table_info(e.table_name) p)
ORDER BY e.added_by, e.table_name, e.column_name;
