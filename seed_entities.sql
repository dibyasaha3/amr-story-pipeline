-- Run this ONCE in DB Browser's "Execute SQL" tab, against amr_pipeline.db.
-- Click "Write Changes" afterward to save it.
-- Not safe to re-run: it is a plain INSERT, so a second run adds all 30 rows again.
--
-- Source: CARB-X active portfolio, https://carb-x.org/portfolio/portfolio-companies/
-- (checked 2026-11-03). This covers the 30 of 43 active CARB-X developers
-- working on therapeutics/vaccines -- the other 13 are diagnostics
-- developers, out of scope for this project.
--
-- entity_type is a best-effort read of each organization's stage from its
-- name and public role (startup / academic spinout / mid-size biotech /
-- large pharma) -- funding stage, headcount and incorporation status were
-- not individually verified. Treat this column as a draft to correct as
-- you research each company, not as a confirmed fact.
-- country and founded_year are left NULL -- fill these in as you verify
-- each one; don't leave them as guesses.

INSERT INTO entities (name, entity_type, carb_x_funded, notes) VALUES
('AdJane', 'startup', 1, 'CARB-X portfolio: gonorrhea vaccine. Verify stage/country before citing.'),
('Basilea Pharmaceutica', 'mid-size biotech', 1, 'CARB-X portfolio: novel class antibiotic targeting LptA. Established Swiss company, verify current stage.'),
('Baxiva', 'startup', 1, 'CARB-X portfolio: multivalent glycoconjugate vaccine.'),
('Bugworks', 'startup', 1, 'CARB-X portfolio: gyrase-topoisomerase inhibitor.'),
('Centauri Therapeutics', 'startup', 1, 'CARB-X portfolio: large molecule immunotherapy.'),
('Clarametyx Biosciences', 'startup', 1, 'CARB-X portfolio: anti-biofilm vaccine.'),
('Debiopharm', 'mid-size biotech', 1, 'CARB-X portfolio: narrow-spectrum FabI inhibitor. Established Swiss pharma, verify stage.'),
('GangaGen Biotechnologies', 'startup', 1, 'CARB-X portfolio: engineered antibiotic proteins.'),
('GlaxoSmithKline', 'large pharma', 1, 'CARB-X portfolio: Group A Streptococcus vaccine. Large pharma -- included for completeness, not a startup.'),
('Helmholtz Centre for Infection Research', 'academic', 1, 'CARB-X portfolio: small-molecule inhibitor of S. aureus alpha-hemolysin.'),
('Immunartes', 'startup', 1, 'CARB-X portfolio: monoclonal antibody vaccine.'),
('Immunethep', 'startup', 1, 'CARB-X portfolio: conjugated peptide-based vaccine.'),
('Innoviva Specialty Therapeutics', 'mid-size biotech', 1, 'CARB-X portfolio: small molecule targeting penicillin-binding proteins. Publicly traded parent, verify stage.'),
('Justus Liebig University Giessen', 'academic', 1, 'CARB-X portfolio: peptide antibiotic inhibiting the BamA protein.'),
('Kinvard Bio', 'startup', 1, 'CARB-X portfolio: enhancements to lincosamide antibiotics.'),
('LimmaTech Biologics', 'startup', 1, 'CARB-X portfolio: gonorrhea vaccine.'),
('Locus Biosciences', 'startup', 1, 'CARB-X portfolio: CRISPR-Cas3 bacteriophage.'),
('Lumen Bioscience', 'startup', 1, 'CARB-X portfolio: oral antimicrobial immunotherapy (monoclonal antibody).'),
('Macro Biologics', 'startup', 1, 'CARB-X portfolio: next-generation local antimicrobial.'),
('Myers Research Group', 'academic', 1, 'CARB-X portfolio: lipoprotein transport inhibitors for MDR Enterobacteriaceae.'),
('Peptilogics', 'startup', 1, 'CARB-X portfolio: engineered peptide for fracture-related infections.'),
('PHIOGEN', 'startup', 1, 'CARB-X portfolio: phage-based therapeutic.'),
('Seres Therapeutics', 'mid-size biotech', 1, 'CARB-X portfolio: novel live biotherapeutic. Publicly traded, verify current stage.'),
('SNIPR BIOME', 'startup', 1, 'CARB-X portfolio: CRISPR-engineered precision preventative.'),
('Syntiron', 'startup', 1, 'CARB-X portfolio: alloy vaccine.'),
('Tamrisa', 'startup', 1, 'CARB-X portfolio: non-beta-lactam PBP inhibitor.'),
('University of Melbourne (Doherty Institute)', 'academic', 1, 'CARB-X portfolio: PBT2 oral therapeutic.'),
('University of Maryland', 'academic', 1, 'CARB-X portfolio: maternal vaccine.'),
('Vaxdyn', 'startup', 1, 'CARB-X portfolio: trivalent vaccine to prevent bacterial pneumonia.'),
('Vedanta Biosciences', 'mid-size biotech', 1, 'CARB-X portfolio: live biotherapeutic. Later-stage biotech, verify current status.');
