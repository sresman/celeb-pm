# Stale artifacts — do not trust as current

## attribution_audit_precorpus_restore/ (+ its log)
46 per-episode attribution audit files produced on 2026-09-08 against the
corpus as it stood BEFORE the git restore (i.e. before Bankless 2026-05-28 and
Heller House 2026-06-08 were removed and a16z 2026-08-31 was ingested).

Thesis IDs in these files do not reliably map to the current 614-thesis corpus.
Kept only as a record of the original measurement (73% subject / 11% other /
16% indeterminate on named-ticker slots). Parked here 2026-09-08 per the
attribution handoff, step 1.

Current audit output lives in `analysis/attribution_audit_pass1/`,
`analysis/attribution_audit_pass2/`, and the reconciled
`analysis/attribution_resolved.json`.
