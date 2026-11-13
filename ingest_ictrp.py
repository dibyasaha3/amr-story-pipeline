"""
Global trials import: WHO ICTRP export -> amr_pipeline.db

What it does:
  1. Reads a file you exported from the WHO ICTRP Search Portal
     (https://trialsearch.who.int), XML or CSV.
  2. Skips ClinicalTrials.gov records (ingest.py already covers those).
  3. Catches duplicates: if a ChiCTR/CTRI/... record lists an ID you
     already have (e.g. an NCT number), it is linked to that row instead
     of being added twice.
  4. Adds new trials, and logs an event when a trial you already have
     changes phase or recruitment status, exactly like ingest.py.
  5. Prints a summary, including a count per registry.

Needs: migrate_v3.sql run once first. No extra packages, no password.

Run it (from the folder that holds amr_pipeline.db):
  python ingest_ictrp.py ictrp_export.xml

If you leave out the file name, it uses the newest file in this folder
whose name starts with "ictrp" and ends in .xml or .csv.

Safe to re-run with the same file: nothing is duplicated.

Data terms: WHO asks you to credit "WHO ICTRP" and show the date the
data were processed. The import date is stored in last_checked.
"""

import csv
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "amr_pipeline.db"

# ICTRP field names vary slightly between XML and CSV exports and over
# time, so each field we need is matched against several spellings.
# Matching ignores case, spaces and underscores.
FIELD_ALIASES = {
    "trial_id":       ["TrialID", "Trial ID", "Main ID"],
    "title":          ["Public_title", "Public title", "Scientific_title", "Scientific title"],
    "sponsor":        ["Primary_sponsor", "Primary sponsor"],
    "registered":     ["Date_registration3", "Date_registration", "Date registration", "Date of registration"],
    "start_date":     ["Date_enrollement", "Date_enrollment", "Date enrollement", "Date of first enrolment"],
    "register":       ["Source_Register", "Source Register", "Source register"],
    "url":            ["web_address", "Web address", "url"],
    "status":         ["Recruitment_Status", "Recruitment Status"],
    "enrollment":     ["Target_size", "Target size"],
    "phase":          ["Phase"],
    "countries":      ["Countries", "Countries of recruitment"],
    "condition":      ["Condition", "Conditions"],
    "intervention":   ["Intervention", "Interventions"],
    "primary_outcome": ["Primary_outcome", "Primary outcome"],
    "secondary_ids":  ["SecondaryIDs", "Secondary_ID", "Secondary IDs", "Secondary ID"],
}
REQUIRED = ["trial_id"]

# Registry -> coarse region label used for filtering on the board.
# Checked against the Source_Register value first, then the ID prefix.
REGISTRY_REGION = [
    # (registry label, ID prefix regex, region)
    ("ChiCTR",  r"^ChiCTR",          "China"),
    ("ITMCTR",  r"^ITMCTR",          "China"),
    ("CTRI",    r"^CTRI",            "South Asia"),
    ("SLCTR",   r"^SLCTR",           "South Asia"),
    ("jRCT",    r"^jRCT",            "Japan"),
    ("JPRN",    r"^JPRN",            "Japan"),
    ("KCT",     r"^KCT",             "South Korea"),
    ("TCTR",    r"^TCTR",            "Southeast Asia"),
    ("IRCT",    r"^IRCT",            "Middle East"),
    ("LBCTR",   r"^LBCTR",           "Middle East"),
    ("PACTR",   r"^PACTR",           "Africa"),
    ("REBEC",   r"^RBR-",            "Latin America"),
    ("RPCEC",   r"^RPCEC",           "Latin America"),
    ("REPEC",   r"^PER-",            "Latin America"),
    ("ANZCTR",  r"^ACTRN",           "Australia/NZ"),
    ("DRKS",    r"^DRKS",            "Europe"),
    ("EUCTR",   r"^EUCTR",           "Europe"),
    ("CTIS",    r"^\d{4}-\d{6}-\d{2}", "Europe"),
    ("NTR",     r"^(NTR|NL)\d",      "Europe"),
    ("ISRCTN",  r"^ISRCTN",          "UK/International"),
]

ID_PATTERN = re.compile(
    r"(NCT\d{8}|ChiCTR[-\w]*\d+|ITMCTR\d+|CTRI/\d{4}/\d+/\d+|jRCT\w+|JPRN-\w+|"
    r"KCT\d+|TCTR\d+|IRCT\w+|PACTR\d+|RBR-\w+|ACTRN\d+|DRKS\d+|ISRCTN\d+|"
    r"EUCTR\d{4}-\d{6}-\d{2}|\d{4}-\d{6}-\d{2}(?:-00)?|SLCTR/\d{4}/\d+|LBCTR\d+)",
    re.IGNORECASE,
)


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _pick(record, key):
    """Return the first non-empty value among a field's alias spellings."""
    for alias in FIELD_ALIASES[key]:
        value = record.get(_norm(alias))
        if value and value.strip():
            return value.strip()
    return None


def read_export(path):
    """Read an ICTRP XML or CSV export into a list of {normalised_field: value}."""
    raw = path.read_bytes().decode("utf-8", errors="replace")
    if path.suffix.lower() == ".csv" or not raw.lstrip().startswith("<"):
        reader = csv.DictReader(raw.splitlines())
        return [{_norm(k): (v or "") for k, v in row.items() if k} for row in reader]

    # Strip characters XML forbids; registry text sometimes contains them.
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    root = ET.fromstring(raw.encode("utf-8"))
    records = []
    for trial in root.iter():
        children = list(trial)
        if not children:
            continue
        fields = {_norm(c.tag): "".join(c.itertext()) for c in children}
        if any(_norm(a) in fields for a in FIELD_ALIASES["trial_id"]):
            records.append(fields)
    return records


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def iso_date(text):
    """Registries write dates many ways; store YYYY-MM-DD so date filters work.
    Unrecognised formats are kept as written."""
    if not text:
        return None
    t = text.strip()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", t)                     # 20240320
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", t)                  # 2024-03-20
    if m:
        return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", t)                  # 20/03/2024 (ICTRP is day-first)
    if m:
        return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})", t)  # 20 March 2024
    if m and m[2].lower() in MONTHS:
        return f"{m[3]}-{MONTHS[m[2].lower()]:02d}-{int(m[1]):02d}"
    m = re.match(r"^([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", t)  # March 20, 2024
    if m and m[1].lower() in MONTHS:
        return f"{m[3]}-{MONTHS[m[1].lower()]:02d}-{int(m[2]):02d}"
    return t


def parse_enrollment(text):
    """'240' -> 240; 'Experimental:120;Control:120' -> 240 (arms are added up)."""
    if not text:
        return None
    arms = re.findall(r":\s*(\d+)", text)
    if len(arms) > 1:
        return sum(int(a) for a in arms)
    first = re.search(r"\d+", text)
    return int(first.group()) if first else None


def region_for(register, trial_id):
    reg = (register or "").lower()
    for label, prefix, region in REGISTRY_REGION:
        if reg and label.lower() in reg:
            return label, region
    for label, prefix, region in REGISTRY_REGION:
        if re.match(prefix, trial_id or "", re.IGNORECASE):
            return label, region
    return (register or "unknown"), None


def is_ctgov(register, trial_id):
    return "clinicaltrials" in (register or "").lower() or (trial_id or "").upper().startswith("NCT")


def check_fields(records):
    if not records:
        sys.exit("The file contains no trial records. Check that it is an ICTRP export.")
    present = set().union(*[set(r.keys()) for r in records])
    missing = [k for k in FIELD_ALIASES if not any(_norm(a) in present for a in FIELD_ALIASES[k])]
    for k in REQUIRED:
        if k in missing:
            sys.exit(
                "Could not find the trial ID column in this file. "
                "Columns found: " + ", ".join(sorted(present))
            )
    return missing


def sync_records(conn, records):
    """Write ICTRP records into trials/events. Returns a summary dict."""
    today = datetime.now(timezone.utc).date().isoformat()
    cur = conn.cursor()
    summary = {"new_trials": 0, "status_changes": 0, "phase_changes": 0, "unchanged": 0,
               "skipped_clinicaltrials_gov": 0, "linked_duplicates": 0, "per_registry": {}}

    def log(trial_id, kind, text, url):
        cur.execute(
            "INSERT INTO events (trial_id, event_type, event_date, description, source_url) "
            "VALUES (?, ?, ?, ?, ?)", (trial_id, kind, today, text, url))

    for rec in records:
        tid = _pick(rec, "trial_id")
        register = _pick(rec, "register")
        if not tid:
            continue
        if is_ctgov(register, tid):
            summary["skipped_clinicaltrials_gov"] += 1
            continue

        registry, region = region_for(register, tid)
        status, phase = _pick(rec, "status"), _pick(rec, "phase")
        url = _pick(rec, "url")
        sec_text = _pick(rec, "secondary_ids") or ""
        other_ids = {m.group(0) for m in ID_PATTERN.finditer(sec_text)} - {tid}
        nct = next((i.upper() for i in other_ids if i.upper().startswith("NCT")), None)

        # 1. Already have this exact registry record? -> update, log changes.
        cur.execute("SELECT trial_id, phase, status FROM trials WHERE registry_id = ?", (tid,))
        row = cur.fetchone()
        if row:
            db_id, old_phase, old_status = row
            changed = False
            if status and status != old_status:
                log(db_id, "status_change", f"Status changed: {old_status} -> {status}", url)
                summary["status_changes"] += 1
                changed = True
            if phase and phase != old_phase:
                log(db_id, "phase_change", f"Phase changed: {old_phase} -> {phase}", url)
                summary["phase_changes"] += 1
                changed = True
            cur.execute(
                "UPDATE trials SET status = COALESCE(?, status), phase = COALESCE(?, phase), "
                "last_checked = ?" + (", updated_at = datetime('now')" if changed else "") +
                " WHERE trial_id = ?", (status, phase, today, db_id))
            if not changed:
                summary["unchanged"] += 1
            continue

        # 2. Same trial already stored under another ID? -> link, don't duplicate.
        dup = None
        for other in other_ids:
            cur.execute("SELECT trial_id, secondary_ids FROM trials "
                        "WHERE registry_id = ? COLLATE NOCASE OR nct_id = ? COLLATE NOCASE",
                        (other, other))
            dup = cur.fetchone()
            if dup:
                break
        if dup:
            db_id, existing_sec = dup
            ids = set(filter(None, (existing_sec or "").split(";")))
            if tid not in ids:
                ids.add(tid)
                cur.execute("UPDATE trials SET secondary_ids = ? WHERE trial_id = ?",
                            (";".join(sorted(ids)), db_id))
            summary["linked_duplicates"] += 1
            continue

        # 3. Genuinely new -> insert and log.
        enrollment = parse_enrollment(_pick(rec, "enrollment"))
        title = _pick(rec, "title")
        cur.execute(
            """INSERT INTO trials
                 (asset_id, nct_id, registry, registry_id, title, phase, status, start_date,
                  enrollment, sponsor_name, primary_endpoint, condition_text, intervention_text,
                  countries, region, registered_date, secondary_ids, source_url, last_checked)
               VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (nct, registry, tid, title, phase, status, iso_date(_pick(rec, "start_date")), enrollment,
             _pick(rec, "sponsor"), _pick(rec, "primary_outcome"), _pick(rec, "condition"),
             _pick(rec, "intervention"), _pick(rec, "countries"), region,
             iso_date(_pick(rec, "registered")), ";".join(sorted(other_ids)) or None, url, today))
        log(cur.lastrowid, "new_trial", f"New {registry} trial: {title or tid}", url)
        summary["new_trials"] += 1
        summary["per_registry"][registry] = summary["per_registry"].get(registry, 0) + 1

    conn.commit()
    return summary


# Every column this script reads or writes, and which upgrade file adds it.
NEEDED_COLUMNS = {
    "trials": {
        "trial_id": "schema.sql", "asset_id": "schema.sql", "nct_id": "schema.sql",
        "phase": "schema.sql", "status": "schema.sql", "start_date": "schema.sql",
        "enrollment": "schema.sql", "primary_endpoint": "schema.sql",
        "last_checked": "schema.sql", "updated_at": "schema.sql",
        "sponsor_name": "migrate_v2.sql",
        "registry": "migrate_v3.sql", "registry_id": "migrate_v3.sql", "title": "migrate_v3.sql",
        "condition_text": "migrate_v3.sql", "intervention_text": "migrate_v3.sql",
        "countries": "migrate_v3.sql", "region": "migrate_v3.sql",
        "registered_date": "migrate_v3.sql", "secondary_ids": "migrate_v3.sql",
        "source_url": "migrate_v3.sql",
    },
    "events": {
        "trial_id": "schema.sql", "event_type": "schema.sql", "event_date": "schema.sql",
        "description": "schema.sql", "source_url": "schema.sql",
    },
}


def check_columns(conn):
    """Stop with a plain explanation, before writing anything, if the
    database is missing a column this script needs."""
    missing = []
    for table, columns in NEEDED_COLUMNS.items():
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        missing += [(table, col, src) for col, src in columns.items() if col not in have]
    if not missing:
        return
    files = sorted({src for _, _, src in missing})
    lines = [f"  {t}.{c}  (added by {s})" for t, c, s in missing]
    sys.exit(
        "Stopped before importing: your database is missing these columns:\n"
        + "\n".join(lines)
        + "\n\nFix: in DB Browser, run " + " and then ".join(files)
        + " in the Execute SQL tab, click Write Changes, then run this script again."
        + "\nTo list every missing column at once, run check_database.sql."
    )


def find_export():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    candidates = sorted(
        [p for p in HERE.iterdir() if p.name.lower().startswith("ictrp")
         and p.suffix.lower() in (".xml", ".csv")],
        key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        sys.exit("No export file given, and no file named ictrp*.xml or ictrp*.csv found in this folder.")
    return candidates[0]


def main():
    path = find_export()
    print(f"Reading {path.name} ...")
    records = read_export(path)
    missing = check_fields(records)
    print(f"Found {len(records)} records.")
    if missing:
        print("Note: these optional fields were not in the file and stay empty: " + ", ".join(missing))

    if not DB_PATH.exists():
        sys.exit(f"Could not find {DB_PATH.name} next to this script. Put both in the same folder.")
    conn = sqlite3.connect(DB_PATH)
    check_columns(conn)
    summary = sync_records(conn, records)
    conn.close()

    per_registry = summary.pop("per_registry")
    print("Import complete:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    if per_registry:
        print("New trials per registry:")
        for k, v in sorted(per_registry.items(), key=lambda kv: -kv[1]):
            print(f"  {k}: {v}")
    print("\nNext: run refresh_board.sql in DB Browser to put new trials on your scoring board.")


if __name__ == "__main__":
    main()
