"""Generate import_step3_2026-11-09.sql from the two WHO spreadsheets + C-CAMP list."""
import re
import sys
from pathlib import Path

import pandas as pd

if len(sys.argv) != 4:
    sys.exit(
        "This script needs three file names:\n"
        "  python make_step3_sql.py <WHO preclinical .xlsx> <WHO clinical .xlsx> <output .sql>\n"
        "Example:\n"
        "  python make_step3_sql.py who_amr_preclinical_data_2025_final.xlsx "
        "who_amr_antibacterial_clinical_dataset_2025_final.xlsx import_step3_new.sql\n"
        "You only need it for a NEW WHO edition; import_step3_2026-11-09.sql is already built."
    )
PRE, CLIN, OUT = (Path(p) for p in sys.argv[1:4])
TODAY = "2026-11-09"
PRE_TAG = "WHO preclinical 2025"
CCAMP_TAG = "C-CAMP AMR start-ups"


def q(v):
    """SQL literal."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "NULL"
    s = str(v).replace("\xa0", " ").strip()
    s = re.sub(r"\s+", " ", s)
    if s == "" or s.lower() in ("nan", "na", "none"):
        return "NULL"
    return "'" + s.replace("'", "''") + "'"


COUNTRY_SHORT = {
    "United States of America": "USA",
    "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
}
REGION = {
    "USA": "North America", "Canada": "North America",
    "India": "South Asia", "Pakistan": "South Asia",
    "Malaysia": "Southeast Asia", "Singapore": "Southeast Asia",
    "Japan": "Japan", "Republic of Korea": "South Korea", "China": "China",
    "Uruguay": "Latin America", "Chile": "Latin America", "Brazil": "Latin America",
    "Israel": "Middle East",
    "Australia": "Australia/NZ", "New Zealand": "Australia/NZ",
}
EUROPE = {
    "Austria", "Belgium", "Denmark", "Finland", "France", "Germany", "Iceland", "Ireland",
    "Italy", "Netherlands", "Norway", "Portugal", "Spain", "Sweden", "Switzerland",
    "United Kingdom",
}
for _c in EUROPE:
    REGION[_c] = "Europe"

# The first version of this script (9 November 2026, morning) labelled every
# country missing from its short list as "Europe". These were its explicit keys;
# any other non-European country was mislabelled and is corrected below.
FIRST_VERSION_KEYS = {"USA", "Canada", "India", "Pakistan", "Malaysia", "Singapore",
                      "Uruguay", "Israel", "Australia", "New Zealand"}

UNMAPPED = set()
def region_of(country):
    """Region label for the board. Never guesses: an unknown country gets
    no region (NULL) and is reported when the script finishes."""
    if country not in REGION:
        UNMAPPED.add(country)
        return None
    return REGION[country]

# WHO name -> name already in your entities table (from seed_entities.sql)
SEED_ALIAS = {
    "Basilea Pharmaceutica Int. Ltd, Allschwil": "Basilea Pharmaceutica",
    "Bugworks Research Inc": "Bugworks",
    "Debiopharm International": "Debiopharm",
    "Gangagen": "GangaGen Biotechnologies",
    "Justus-Liebig-University Giessen": "Justus Liebig University Giessen",
    "Seres Therapeutics, Inc.": "Seres Therapeutics",
    "University of Melbourne/Doherty Institute": "University of Melbourne (Doherty Institute)",
}


def entity_type(kind, size):
    kind, size = str(kind).lower(), str(size).lower()
    if "academic" in kind:
        return "academic"
    if "non-profit" in kind:
        return "non-profit"
    if "government" in kind:
        return "government institute"
    if "large" in size:
        return "large pharma"
    if "medium" in size:
        return "mid-size biotech"
    return "startup"  # micro or small company


def modality(t):
    t = str(t).lower()
    for key, val in [("bacteriophage", "phage"), ("antibody", "antibody"), ("peptide", "peptide"),
                     ("small molecule", "small molecule"), ("large molecule", "biologic"),
                     ("immunomod", "immunomodulator"), ("microbiome", "microbiome"),
                     ("nucleic", "nucleic acid"), ("decoloni", "decolonisation agent")]:
        if key in t:
            return val
    return "other"


def match_clause(names):
    names = sorted({n.lower() for n in names})
    return "lower(name) IN (" + ", ".join(q(n) for n in names) + ")"


def entity_upsert(names, display, etype, country, region, website, via, note):
    m = match_clause(names)
    disc = (f"CASE WHEN discovered_via IS NULL THEN "
            f"(CASE WHEN carb_x_funded = 1 THEN 'CARB-X; ' ELSE '' END) || {q(via)} "
            f"WHEN instr(discovered_via, {q(via)}) = 0 THEN discovered_via || '; ' || {q(via)} "
            f"ELSE discovered_via END")
    return (
        f"INSERT INTO entities (name, entity_type, country, region, website, discovered_via, notes)\n"
        f"SELECT {q(display)}, {q(etype)}, {q(country)}, {q(region)}, {q(website)}, {q(via)}, {q(note)}\n"
        f"WHERE NOT EXISTS (SELECT 1 FROM entities WHERE {m});\n"
        f"UPDATE entities SET\n"
        f"    country = COALESCE(country, {q(country)}),\n"
        f"    region = COALESCE(region, {q(region)}),\n"
        f"    website = COALESCE(website, {q(website)}),\n"
        f"    entity_type = COALESCE(entity_type, {q(etype)}),\n"
        f"    discovered_via = {disc},\n"
        f"    notes = CASE WHEN notes IS NULL THEN {q(note)} "
        f"WHEN instr(notes, {q(note)}) = 0 THEN notes || ' | ' || {q(note)} ELSE notes END,\n"
        f"    updated_at = datetime('now')\n"
        f"WHERE {m};\n"
    )


out = [f"""-- ============================================================
-- Step 3 import: global preclinical startups + WHO clinical cross-check
-- Generated {TODAY} from (version 2: section 1b corrects region labels
-- for Japan, South Korea and Chile that version 1 got wrong):
--   * who_amr_preclinical_data_2025_final.xlsx  (WHO, data as of 15 Feb 2025)
--   * who_amr_antibacterial_clinical_dataset_2025_final.xlsx (WHO, 90 products)
--   * https://www.amrccamp.in/start-ups (C-CAMP; page footer (c) 2023)
--
-- Run in DB Browser > Execute SQL > open this file > play > Write Changes.
-- Run check_database.sql first: it must return no rows.
-- Safe to re-run: nothing is duplicated.
--
-- What it does:
--   1. Adds WHO preclinical developers and C-CAMP therapeutic start-ups to
--      `entities`. Organisations you already have (e.g. Bugworks, GangaGen,
--      Basilea) are NOT duplicated: they get country, region and source added.
--   2. Adds each WHO preclinical product to `assets`, linked to its developer.
--   3. Stores the WHO clinical pipeline in a new table and creates the view
--      `who_clinical_coverage`, showing which WHO-listed trials your
--      database already holds and which it is missing.
--
-- Afterwards run refresh_board.sql to put the new startups on your board.
--
-- Cite as: WHO Global Observatory on Health R&D, antibacterial pipeline reviews 2025.
-- ============================================================

"""]

# ---------------- preclinical ----------------
pre = pd.read_excel(PRE, sheet_name="Data", header=1)
pre.columns = [str(c).replace("\xa0", " ").strip() for c in pre.columns]
pre = pre[pre["Unique Identifier Number"].notna()].copy()
cols = list(pre.columns)
pathogen_cols = cols[cols.index("A. baumannii"): cols.index("Other") + 1]
priority_cols = [c for c in pathogen_cols if c != "Other"]

out.append("-- ---------- 1. Entities from the WHO preclinical list ----------\n")
inst_rows = pre.groupby("Company/Institution", sort=True).first().reset_index()
for _, r in inst_rows.iterrows():
    who_name = re.sub(r"\s+", " ", str(r["Company/Institution"]).strip())
    seed = SEED_ALIAS.get(who_name)
    country = COUNTRY_SHORT.get(str(r["Country"]).strip(), str(r["Country"]).strip())
    names = [who_name] + ([seed] if seed else [])
    note = (f"WHO 2025: {str(r['Type of company/institution']).strip()}, "
            f"{str(r['Size of company/institution']).strip()}")
    out.append(entity_upsert(names, who_name, entity_type(r["Type of company/institution"],
               r["Size of company/institution"]), country, region_of(country),
               r["Website"], PRE_TAG, note))

# 1b. Repair what the first version got wrong. Harmless if that version was
# never run: each statement only touches rows still labelled 'Europe'.
fixes = []
for _, r in inst_rows.iterrows():
    who_name = re.sub(r"\s+", " ", str(r["Company/Institution"]).strip())
    seed = SEED_ALIAS.get(who_name)
    country = COUNTRY_SHORT.get(str(r["Country"]).strip(), str(r["Country"]).strip())
    right = REGION.get(country)
    if country in FIRST_VERSION_KEYS or right in (None, "Europe"):
        continue
    m = match_clause([who_name] + ([seed] if seed else []))
    fixes.append(
        f"UPDATE entities SET region = {q(right)}, updated_at = datetime('now')\n"
        f"WHERE {m} AND region = 'Europe';\n"
        f"UPDATE story_candidates SET region = {q(right)}\n"
        f"WHERE region = 'Europe' AND entity_id IN (SELECT entity_id FROM entities WHERE {m});\n")
if fixes:
    out.append("\n-- ---------- 1b. Region corrections ----------\n"
               "-- The first version of this file labelled organisations in Japan, South Korea\n"
               "-- and Chile as 'Europe'. These statements correct them, on the organisation\n"
               "-- and on any board row already created. Rows not labelled 'Europe' are untouched.\n")
    out.extend(fixes)

out.append("\n-- ---------- 2. Assets (one per WHO preclinical product) ----------\n")
for _, r in pre.iterrows():
    uid = int(r["Unique Identifier Number"])
    who_name = re.sub(r"\s+", " ", str(r["Company/Institution"]).strip())
    names = [who_name] + ([SEED_ALIAS[who_name]] if who_name in SEED_ALIAS else [])
    pname = str(r["Product/Program name"]).strip()
    if pname.lower() in ("undisclosed", "not yet decided", "nan", "", "not disclosed"):
        pname = f"Undisclosed programme ({who_name})"
    targets = [c.strip() for c in pathogen_cols if str(r[c]).strip().lower() == "yes"]
    priority = int(any(str(r[c]).strip().lower() == "yes" for c in priority_cols))
    moa = " - ".join(x for x in [str(r["Mode of action"]).strip(), str(r["Mode of action (details)"]).strip()]
                     if x and x.lower() not in ("nan", "unknown", "undisclosed", "not disclosed"))
    key = f"{PRE_TAG} #{uid}"
    note = (f"{key}. Stage: {str(r['Pre-clinical development stage']).strip()}. "
            f"Indication: {str(r['Primary indication']).strip()}. "
            f"New chemical class: {str(r['New chemical class']).strip()}. "
            f"Description: {str(r['Product description']).strip()}")
    out.append(
        f"INSERT INTO assets (entity_id, name, modality, mechanism_of_action, target_pathogen, who_priority_pathogen, notes)\n"
        f"SELECT (SELECT entity_id FROM entities WHERE {match_clause(names)} ORDER BY entity_id LIMIT 1),\n"
        f"       {q(pname)}, {q(modality(r['Treatment modality']))}, {q(moa)}, {q('; '.join(targets))}, {priority}, {q(note)}\n"
        f"WHERE NOT EXISTS (SELECT 1 FROM assets WHERE notes LIKE {q(key + '.%')});\n")

# ---------------- C-CAMP ----------------
CCAMP = [
    # (name, website or None, description as listed, animal health?)
    ("Abgenics", "https://www.abgenics.in", "Antibody-based solutions in three formats: camelid VHH, human scFv, mouse scFv", False),
    ("Bugworks", None, "Clinical-stage biopharma developing affordable anti-infectives", False),
    ("GangaGen Biotechnologies", None, "Protein antibacterials and bacteriophages for drug-resistant bacterial infections", False),
    ("Aasya", None, "BacNo Gel: antibacterial, osteoinductive hydrogel for post-tooth-extraction wounds", False),
    ("Biotide Solutions", None, "Cationic helical peptides as antimicrobials against multidrug-resistant bacteria", False),
    ("PepThera Laboratories", "https://pepthera.com", "Guwahati-based start-up by IIT Guwahati alumni; peptide-based therapeutics", False),
    ("Aristogene Biosciences", "https://www.aristogene.com", "Bacteriophage products for infections in livestock, poultry, aquaculture and agriculture", True),
    ("Vitulomics", None, "Topical phyto-therapeutic for clinical mastitis", True),
    ("Ariviya", None, "Naturally derived post-milking teat dip to prevent mastitis", True),
    ("UltraNutri", None, "Insect proteins with antimicrobial properties for aquaculture and animal feed", True),
]
out.append("\n-- ---------- 3. Therapeutic start-ups from the C-CAMP list ----------\n"
           "-- Diagnostics, environmental and non-AMR entries on that page are left out.\n"
           "-- 'Meril Diagnostics' is left out: the page's layout makes its description ambiguous.\n")
for name, site, desc, animal in CCAMP:
    names = [name] + (["Gangagen"] if name.startswith("GangaGen") else []) + \
            (["Bugworks Research Inc"] if name == "Bugworks" else [])
    note = (f"C-CAMP list: {desc}." + (" One Health / animal health, not human therapeutics." if animal else "")
            + " Stage and funding not stated on the page; verify.")
    out.append(entity_upsert(names, name, "startup", "India", "South Asia", site, CCAMP_TAG, note))
out.append(
    "INSERT INTO assets (entity_id, name, modality, notes)\n"
    "SELECT (SELECT entity_id FROM entities WHERE lower(name) = 'aasya' LIMIT 1), 'BacNo Gel', 'other',\n"
    "       'C-CAMP list: antibacterial hydrogel for post-tooth-extraction wounds. Verify stage.'\n"
    "WHERE NOT EXISTS (SELECT 1 FROM assets WHERE name = 'BacNo Gel');\n")

# ---------------- clinical ----------------
cl = pd.read_excel(CLIN, sheet_name="Master DataDrugID")
cl.columns = [str(c).strip() for c in cl.columns]
cl = cl[cl["Product Name"].notna()].copy()
ID_RE = re.compile(r"NCT\d{8}|ChiCTR\s?\d+|CTR\d{8}|ACTRN\d{14}|ISRCTN\d+|JapicCTI\d+|jRCT\w+|CTRI/\d{4}/\d+/\d+",
                   re.IGNORECASE)

out.append("""
-- ---------- 4. WHO clinical pipeline (reference table) ----------
CREATE TABLE IF NOT EXISTS who_clinical_pipeline (
    who_drug_id        INTEGER PRIMARY KEY,
    product_name       TEXT,
    alternative_name   TEXT,
    phase              TEXT,
    developer          TEXT,
    developer_hq       TEXT,
    product_type       TEXT,   -- traditional / non-traditional
    category           TEXT,
    antibacterial_class TEXT,
    indications        TEXT,
    route              TEXT,
    innovative         TEXT,
    trial_codes        TEXT,   -- as written by WHO
    who_update_date    TEXT
);
CREATE TABLE IF NOT EXISTS who_clinical_trial_codes (
    who_drug_id  INTEGER REFERENCES who_clinical_pipeline(who_drug_id),
    trial_code   TEXT,
    registry     TEXT,
    PRIMARY KEY (who_drug_id, trial_code)
);
""")
def registry_of(code):
    c = code.upper()
    for p, n in [("NCT", "ClinicalTrials.gov"), ("CHICTR", "ChiCTR"), ("CTR", "China regulator (chinadrugtrials)"),
                 ("ACTRN", "ANZCTR"), ("ISRCTN", "ISRCTN"), ("JAPICCTI", "JapicCTI (Japan)"),
                 ("JRCT", "jRCT"), ("CTRI", "CTRI")]:
        if c.startswith(p):
            return n
    return None

for _, r in cl.iterrows():
    did = int(r["DrugID"])
    date = r["Date of update"]
    date = str(date)[:10] if pd.notna(date) else None
    out.append(
        "INSERT OR REPLACE INTO who_clinical_pipeline VALUES ("
        + ", ".join([str(did), q(r["Product Name"]), q(r["Alternative name"]) if str(r["Alternative name"]).strip() != "-" else "NULL",
                     q(r["Phase of development"]), q(r["Developer"]), q(r["Developer Geography (HQ)"]),
                     q(r["Product type"]), q(r["Non-traditionals categories"]) if str(r["Product type"]).startswith("Non") else q(r["Therapeutic entity"]),
                     q(r["Antibacterial class"]), q(r["Indications"]), q(r["Route of administration"]),
                     q(r["Innovative?"]), q(r["Clinical trials"]), q(date)]) + ");\n")
    for code in sorted({re.sub(r"\s", "", m.group(0)) for m in ID_RE.finditer(str(r["Clinical trials"]))}):
        code = code.replace("chictr", "ChiCTR")
        out.append(f"INSERT OR IGNORE INTO who_clinical_trial_codes VALUES ({did}, {q(code)}, {q(registry_of(code))});\n")

out.append("""
-- ---------- 5. Coverage view: which WHO-listed trials do you hold? ----------
DROP VIEW IF EXISTS who_clinical_coverage;
CREATE VIEW who_clinical_coverage AS
SELECT
    p.product_name,
    p.phase,
    p.developer,
    p.developer_hq,
    c.trial_code,
    c.registry,
    CASE WHEN t.trial_id IS NOT NULL THEN 'in database' ELSE 'MISSING' END AS in_your_database,
    t.trial_id,
    p.indications
FROM who_clinical_pipeline p
JOIN who_clinical_trial_codes c ON c.who_drug_id = p.who_drug_id
LEFT JOIN trials t
       ON upper(t.nct_id) = upper(c.trial_code)
       OR upper(t.registry_id) = upper(c.trial_code)
       OR instr(upper(COALESCE(t.secondary_ids, '')), upper(c.trial_code)) > 0
ORDER BY in_your_database DESC, p.developer_hq, p.product_name;

-- ---------- Summary ----------
SELECT 'entities from WHO preclinical' AS item, COUNT(*) AS n FROM entities WHERE discovered_via LIKE '%WHO preclinical 2025%'
UNION ALL SELECT 'entities from C-CAMP', COUNT(*) FROM entities WHERE discovered_via LIKE '%C-CAMP%'
UNION ALL SELECT 'WHO preclinical assets', COUNT(*) FROM assets WHERE notes LIKE 'WHO preclinical 2025 #%'
UNION ALL SELECT 'WHO clinical products', COUNT(*) FROM who_clinical_pipeline
UNION ALL SELECT 'WHO trial codes already in your database', COUNT(*) FROM who_clinical_coverage WHERE in_your_database = 'in database'
UNION ALL SELECT 'WHO trial codes MISSING from your database', COUNT(*) FROM who_clinical_coverage WHERE in_your_database = 'MISSING';
""")

OUT.write_text("".join(out), encoding="utf-8")
print("wrote", OUT, sum(1 for _ in OUT.open(encoding="utf-8")), "lines")
if UNMAPPED:
    print("WARNING: no region label for these countries; their organisations get an empty region:")
    for c in sorted(UNMAPPED):
        print("  " + c)
    print("Add them to REGION (or EUROPE) at the top of this script and run it again.")
