"""
score.py: score story candidates one at a time, without DB Browser.

What it does:
  Shows one candidate from the scoring board at a time, with what the
  database knows about it, then asks for each of the eight rubric scores
  with the meaning of 0, 1 and 2 printed beside the question. You type a
  number and press Enter. Each candidate is saved the moment you finish
  it, so you can stop at any time.

Run it (from the folder that holds amr_pipeline.db):
  python score.py

Keys while scoring:
  0, 1, 2   the score (only allowed values are accepted)
  Enter     leave this criterion blank for now
  i         mark this candidate irrelevant and move on, without scoring it
  s         skip this candidate (nothing saved for it)
  q         quit (everything already finished stays saved)

'irrelevant' vs 'dropped':
  irrelevant  never deserved scoring (e.g. a keyword match that is not an
              AMR story at all). Saved with no scores.
  dropped     you scored it and decided not to pursue it.

Requires migrate_v4.sql to have been run once (it adds 'irrelevant' as an
allowed decision). The script checks this and tells you if it is missing.

No extra packages needed. Close DB Browser first, or at least make sure it
has no unsaved changes ("Write Changes"), otherwise the database is locked.

The rubric wording below is provisional: edit the text in RUBRIC and
PHASE_READINGS to match your confirmed definitions. Only the wording is
editable; the column names and allowed scores are fixed by the database.
"""

import sqlite3
import sys
import textwrap
from pathlib import Path

DB_PATH = Path(__file__).parent / "amr_pipeline.db"

# (column, allowed scores, question, {score: meaning})
RUBRIC = [
    ("tier1_mechanism", (0, 1, 2), "How new is the mechanism of action?",
     {0: "Known antibiotic class", 1: "Known target, new approach", 2: "New target or mechanism"}),
    ("tier1_pathogen", (0, 2), "Does it target a WHO bacterial priority pathogen (2024 list)?",
     {0: "No", 2: "Yes"}),
    ("tier1_overlap", (0, 1, 2), "Overlap with your expertise (biofilms, persistence, tolerance)?",
     {0: "None", 1: "Adjacent", 2: "Direct"}),
    ("tier2_status_change", (0, 1, 2), "Is there a recent news hook?",
     {0: "None in the past year", 1: "Within the past year", 2: "Within about 3 months"}),
    ("tier2_first_in_class", (0, 1, 2), "Novelty against existing treatments?",
     {0: "Similar to existing drugs", 1: "Clear improvement within a known class", 2: "First in class"}),
    ("tier2_sponsor_stage", (0, 1, 2), "Who is behind it?",
     {0: "Large pharma", 1: "Mid-size company", 2: "Startup or academic group"}),
    ("tier3_open_question", (0, 1, 2), "Is there an unresolved question the article can explore?",
     {0: "None", 1: "Partly", 2: "Clear and interesting"}),
    ("tier3_comparability", (0, 2), "Is there data against a benchmark, so readers can judge it?",
     {0: "No", 2: "Yes"}),
]

# Extra hint per phase for the three criteria whose reading changes by phase.
PHASE_READINGS = {
    "tier2_status_change": {
        "clinical trial": "Phase or status changed recently",
        "preclinical startup": "New funding, award or first-in-human announcement",
        "academic finding": "Published in the last 6 months",
    },
    "tier2_sponsor_stage": {
        "academic finding": "Translational stage: spinout or licence 2, efficacy in animals 1, lab dishes only 0",
    },
    "tier3_comparability": {
        "clinical trial": "Has a standard-of-care comparison arm",
        "preclinical startup": "Data against a benchmark antibiotic",
        "academic finding": "Tested in an animal model or on clinical isolates",
    },
}

DECISIONS = {"1": "shortlist", "2": "writing", "3": "dropped", "4": "irrelevant", "": "to review"}
PHASES = {"1": "preclinical startup", "2": "clinical trial", "3": "academic finding", "": None}


class Quit(Exception):
    pass


class Skip(Exception):
    pass


class Irrelevant(Exception):
    pass


def wrap(text, indent="    ", width=88):
    return textwrap.fill(str(text), width=width, initial_indent=indent, subsequent_indent=indent)


def ask(prompt, valid):
    """Ask until the answer is one of `valid` (strings). 'q' quits everywhere."""
    while True:
        answer = input(prompt).strip().lower()
        if answer == "q":
            raise Quit
        if answer in valid:
            return answer
        print("    Please type one of: " + ", ".join(v if v else "Enter" for v in valid))


def irrelevant_allowed(conn):
    """True if migrate_v4.sql has been run (the decision constraint lists 'irrelevant')."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'story_candidates'"
    ).fetchone()
    return row is not None and "'irrelevant'" in row[0]


def show_candidate(conn, c, number, total):
    print("\n" + "=" * 88)
    print(f"Candidate {number} of {total}   [{c['story_phase']}]   id {c['candidate_id']}   decision: {c['decision']}")
    print("=" * 88)
    print(wrap(c["working_title"] or "(no title)", indent="  "))
    where = ", ".join(x for x in [c["country"], c["region"]] if x)
    print(f"  Where: {where or 'unknown'}" + ("   (underreported region)" if c["underreported_region"] else ""))
    print(f"  Found via: {c['found_via'] or 'unknown'}")
    if c["source_url"]:
        print(f"  Link: {c['source_url']}")

    if c["trial_id"]:
        t = conn.execute("SELECT * FROM trials WHERE trial_id = ?", (c["trial_id"],)).fetchone()
        if t:
            print(f"  Trial: {t['registry_id']}  phase {t['phase'] or '?'}  status {t['status'] or '?'}")
            for label, key in [("Sponsor", "sponsor_name"), ("Condition", "condition_text"),
                               ("Intervention", "intervention_text"), ("Registered", "registered_date"),
                               ("Started", "start_date")]:
                if t[key]:
                    print(wrap(f"{label}: {t[key]}"[:400], indent="  "))
    if c["entity_id"]:
        e = conn.execute("SELECT * FROM entities WHERE entity_id = ?", (c["entity_id"],)).fetchone()
        if e:
            print(f"  Organisation type: {e['entity_type'] or 'unknown'}")
            if e["notes"]:
                print(wrap(f"Notes: {e['notes']}"[:400], indent="  "))
        assets = conn.execute(
            "SELECT name, modality, target_pathogen, notes FROM assets WHERE entity_id = ? ORDER BY asset_id",
            (c["entity_id"],)).fetchall()
        for a in assets[:4]:
            print(f"  Product: {a['name']}  ({a['modality'] or '?'})")
            if a["target_pathogen"]:
                print(wrap(f"Targets: {a['target_pathogen']}", indent="      "))
            if a["notes"]:
                print(wrap(a["notes"][:300] + ("..." if len(a["notes"]) > 300 else ""), indent="      "))
        if len(assets) > 4:
            print(f"  ... and {len(assets) - 4} more products")
    if c["notes"]:
        print(wrap(f"Your notes: {c['notes']}", indent="  "))
    print("\n  Type i at any score prompt to mark this candidate irrelevant without scoring it.")


def score_one(c):
    """Ask the eight criteria. Returns a dict of new values.
    Raises Skip ('s') or Irrelevant ('i') to leave early."""
    scores = {}
    for column, allowed, question, meanings in RUBRIC:
        print(f"\n  {column}: {question}")
        hint = PHASE_READINGS.get(column, {}).get(c["story_phase"])
        if hint:
            print(f"    For a {c['story_phase']}: {hint}")
        for s in allowed:
            print(f"    {s} = {meanings[s]}")
        current = c[column]
        suffix = f" [now {current}, Enter keeps it]" if current is not None else " [Enter = leave blank]"
        answer = ask(f"  Score{suffix}: ", [str(s) for s in allowed] + ["", "s", "i"])
        if answer == "s":
            raise Skip
        if answer == "i":
            raise Irrelevant
        scores[column] = int(answer) if answer else current
    return scores


def ask_note():
    note = input("  Note (optional, Enter to skip): ").strip()
    if note.lower() == "q":
        raise Quit
    return note


def save(conn, candidate_id, columns, decision, note):
    """Write the given score columns (may be empty), the decision and an appended note."""
    sets = [f"{col} = ?" for col in columns] + ["decision = ?"]
    values = list(columns.values()) + [decision]
    if note:
        sets.append("notes = CASE WHEN notes IS NULL OR notes = '' THEN ? ELSE notes || ' | ' || ? END")
        values += [note, note]
    conn.execute(f"UPDATE story_candidates SET {', '.join(sets)} WHERE candidate_id = ?",
                 values + [candidate_id])
    conn.commit()


def main():
    if not DB_PATH.exists():
        sys.exit(f"Could not find {DB_PATH.name} next to this script. Put both in the same folder.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("SELECT underreported_region FROM story_candidates LIMIT 1")
    except sqlite3.OperationalError:
        sys.exit("No scoring board found. Run migrate_v3.sql and refresh_board.sql first.")
    if not irrelevant_allowed(conn):
        sys.exit("Your database does not accept 'irrelevant' yet. Run migrate_v4.sql once "
                 "in DB Browser (Execute SQL, then Write Changes), then run this script again.")

    try:
        print("Which phase?  1 = preclinical startup, 2 = clinical trial, 3 = academic finding, Enter = all")
        phase = PHASES[ask("> ", list(PHASES))]
        only_flagged = ask("Only underreported regions?  y / n (Enter = n): ", ["y", "n", ""]) == "y"
        print("Which candidates?  1 = not yet scored, 2 = all marked 'to review', "
              "3 = shortlist (re-score), 4 = marked irrelevant (to recheck)")
        which = ask("> (Enter = 1): ", ["1", "2", "3", "4", ""]) or "1"
    except Quit:
        return

    sql = "SELECT * FROM story_candidates WHERE 1 = 1"
    params = []
    if phase:
        sql += " AND story_phase = ?"
        params.append(phase)
    if only_flagged:
        sql += " AND underreported_region = 1"
    if which == "1":
        sql += " AND decision = 'to review' AND " + " AND ".join(f"{col} IS NULL" for col, *_ in RUBRIC)
    elif which == "2":
        sql += " AND decision = 'to review'"
    elif which == "3":
        sql += " AND decision = 'shortlist'"
    else:
        sql += " AND decision = 'irrelevant'"
    sql += " ORDER BY story_phase, candidate_id"
    candidates = conn.execute(sql, params).fetchall()

    if not candidates:
        print("Nothing to score with those choices.")
        return
    print(f"\n{len(candidates)} candidates. Type q at any prompt to stop; finished ones are saved.")

    saved = irrelevant = 0
    try:
        for n, c in enumerate(candidates, 1):
            show_candidate(conn, c, n, len(candidates))
            try:
                scores = score_one(c)
            except Skip:
                print("  Skipped.")
                continue
            except Irrelevant:
                note = ask_note()
                save(conn, c["candidate_id"], {}, "irrelevant", note)
                irrelevant += 1
                print("  Marked irrelevant. Scores left untouched.")
                continue

            total = sum(v for v in scores.values() if v is not None)
            filled = sum(v is not None for v in scores.values())
            print(f"\n  Total: {total} of 16 ({filled} of 8 criteria scored)")
            print("  Decision?  1 = shortlist, 2 = writing, 3 = dropped, 4 = irrelevant, "
                  f"Enter = keep '{c['decision']}'")
            answer = ask("  > ", list(DECISIONS))
            decision = DECISIONS[answer] if answer else c["decision"]
            note = ask_note()
            save(conn, c["candidate_id"], scores, decision, note)
            saved += 1
            print("  Saved.")
    except Quit:
        print("\nStopped.")
    except sqlite3.OperationalError as err:
        print(f"\nCould not save: {err}. If it says 'locked', close DB Browser or click Write Changes there.")
    finally:
        conn.close()
    print(f"{saved} candidate(s) scored, {irrelevant} marked irrelevant. "
          "Open the scoring_board view to see the ranking.")


if __name__ == "__main__":
    main()
