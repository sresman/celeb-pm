# Removed / Corrected Corpus Files — Log

Track any file removed from the Gavin Baker corpus, with reason, so nothing
silently disappears.

---

## 2026-07-08 — `2026-02-15_heller_house_spacex_cfo_2026.json` (REMOVED)

**Location:** `analysis/thesis_extractions/2026-02-15_heller_house_spacex_cfo_2026.json`
**Action:** `git rm` (removed from corpus and thesis-extraction set).

**Reason — RED HERRING, not a Baker appearance.** The source is
"Heller House / Mission Control," a reporter/host segment profiling **SpaceX CFO
Bret Johnson** during SpaceX IPO week. Gavin Baker is not the speaker; this is
third-party coverage of SpaceX, not a Baker public appearance. Its 3 extracted
"theses" were therefore mis-attributed to Baker and would contaminate the
thesis timeline.

**Impact:** Corpus drops from 27 → **26** confirmed Baker appearances.
The extracted theses (3) from this file are no longer part of the Baker set.

**Downstream note (not yet actioned — audit step only):** this date/source may
still be referenced in `transcripts/_master_manifest.json`,
`analysis/thesis_timeline*.json`, `analysis/all_summaries.json`, and the
`analysis/thesis_audits/` / `thesis_reaudits/` derived files. Those derived
artifacts were built from the 27-file set and will need regeneration (or a
targeted purge of the heller_house theses) in a later cleanup pass. Flagged
here so the contamination is not forgotten.
