"""
Phase 2 ingestion script.

What it does:
  1. Connects to the live AACT database and runs aact_query.sql.
  2. Compares each returned trial against your local amr_pipeline.db.
  3. Inserts new trials, and logs an event any time a trial you already
     have changes phase or status.
  4. Prints a summary so you can see what's new since last run.

Setup (one-time):
  pip install psycopg2-binary

Credentials:
  This script reads your AACT username/password from environment
  variables, never hardcoded in the file:

    export AACT_USER="your_aact_username"
    export AACT_PASSWORD="your_aact_password"

  (On Windows PowerShell: $env:AACT_USER="..." etc.)

Run it:
  python ingest.py

Re-run it weekly. It only inserts/logs what's new or changed — running it
twice in a row with no new data on AACT's side is a safe no-op.
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "amr_pipeline.db"
SQL_PATH = Path(__file__).parent / "aact_query.sql"


def get_aact_rows():
    """Connect to AACT and run the query. Returns a list of dict rows."""
    import psycopg2
    import psycopg2.extras

    user = os.environ.get("AACT_USER")
    password = os.environ.get("AACT_PASSWORD")
    if not user or not password:
        sys.exit(
            "Missing credentials. Set AACT_USER and AACT_PASSWORD as "
            "environment variables before running this script."
        )

    query = SQL_PATH.read_text()

    conn = psycopg2.connect(
        host="aact-db.ctti-clinicaltrials.org",
        port=5432,
        dbname="aact",
        user=user,
        password=password,
    )
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _to_str(value):
    """
    AACT returns start_date/completion_date as Python date objects (via
    psycopg2), not strings. Older Python versions silently auto-convert
    these for sqlite3, but that auto-conversion is deprecated and will be
    removed in a future Python release — so convert explicitly here rather
    than relying on it.
    """
    if value is None:
        return None
    return str(value)


def sync_rows(local_conn, rows):
    """
    Compare AACT rows against the local trials table and write
    inserts/updates + events. Returns a summary dict.
    Pure function of (local_conn, rows) so it can be tested with
    fake rows, without touching AACT.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    summary = {"new_trials": 0, "status_changes": 0, "phase_changes": 0, "unchanged": 0}

    cur = local_conn.cursor()

    for row in rows:
        nct_id = row["nct_id"]
        cur.execute(
            "SELECT trial_id, phase, status FROM trials WHERE nct_id = ?",
            (nct_id,),
        )
        existing = cur.fetchone()

        if existing is None:
            # New trial: insert it. We don't yet know its asset/entity —
            # that linkage happens when you manually curate against
            # CARB-X/WHO in Phase 2's second step. For now it sits
            # unlinked (asset_id NULL) and visible in your shortlist query.
            cur.execute(
                """
                INSERT INTO trials
                    (asset_id, nct_id, phase, status, start_date,
                     completion_date, enrollment, sponsor_name, primary_endpoint, last_checked)
                VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    nct_id,
                    row.get("phase"),
                    row.get("overall_status"),
                    _to_str(row.get("start_date")),
                    _to_str(row.get("completion_date")),
                    row.get("enrollment"),
                    row.get("sponsor_name"),
                    today,
                ),
            )
            trial_id = cur.lastrowid
            cur.execute(
                """
                INSERT INTO events (trial_id, event_type, event_date, description, source_url)
                VALUES (?, 'new_trial', ?, ?, ?)
                """,
                (
                    trial_id,
                    today,
                    f"New trial registered: {row.get('brief_title', '')}",
                    f"https://clinicaltrials.gov/study/{nct_id}",
                ),
            )
            summary["new_trials"] += 1
            continue

        trial_id, old_phase, old_status = existing
        changed = False

        if row.get("overall_status") and row.get("overall_status") != old_status:
            cur.execute(
                """
                INSERT INTO events (trial_id, event_type, event_date, description, source_url)
                VALUES (?, 'status_change', ?, ?, ?)
                """,
                (
                    trial_id,
                    today,
                    f"Status changed: {old_status} -> {row['overall_status']}",
                    f"https://clinicaltrials.gov/study/{nct_id}",
                ),
            )
            summary["status_changes"] += 1
            changed = True

        if row.get("phase") and row.get("phase") != old_phase:
            cur.execute(
                """
                INSERT INTO events (trial_id, event_type, event_date, description, source_url)
                VALUES (?, 'phase_change', ?, ?, ?)
                """,
                (
                    trial_id,
                    today,
                    f"Phase changed: {old_phase} -> {row['phase']}",
                    f"https://clinicaltrials.gov/study/{nct_id}",
                ),
            )
            summary["phase_changes"] += 1
            changed = True

        if changed:
            cur.execute(
                """
                UPDATE trials
                SET phase = ?, status = ?, enrollment = ?, sponsor_name = ?, last_checked = ?, updated_at = datetime('now')
                WHERE trial_id = ?
                """,
                (row.get("phase"), row.get("overall_status"), row.get("enrollment"), row.get("sponsor_name"), today, trial_id),
            )
        else:
            # Still backfill sponsor_name here: trials inserted before this
            # column existed have it as NULL, and a re-run is how they get
            # filled in, even when phase/status didn't change.
            cur.execute(
                "UPDATE trials SET sponsor_name = ?, last_checked = ? WHERE trial_id = ?",
                (row.get("sponsor_name"), today, trial_id),
            )
            summary["unchanged"] += 1

    local_conn.commit()
    return summary


def main():
    rows = get_aact_rows()
    print(f"AACT returned {len(rows)} candidate trials.")

    conn = sqlite3.connect(DB_PATH)
    summary = sync_rows(conn, rows)
    conn.close()

    print("Sync complete:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(
        "\nNext: open amr_pipeline.db in DB Browser and check the events "
        "table for this run's rows (event_date = today) before moving to "
        "Phase 3 scoring."
    )


if __name__ == "__main__":
    main()
