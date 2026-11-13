-- One-time migration for databases created with an older schema.sql that
-- had no sponsor_name column. Run it in DB Browser's "Execute SQL" tab
-- against your EXISTING amr_pipeline.db; it does not touch existing rows.
--
-- New installs: skip this file. The current schema.sql already includes
-- sponsor_name, so running this would stop with "duplicate column name".
--
-- After running this, click "Write Changes" in DB Browser to save it.

ALTER TABLE trials ADD COLUMN sponsor_name TEXT;
