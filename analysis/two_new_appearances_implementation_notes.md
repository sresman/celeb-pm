# Implementation Notes — 2 New Appearances (task started 2026-08-10)

Source: fomo-fund-monitor YouTube triage surfaced 25 candidate IDs; operator
confirmed exactly 2 as genuine new Baker appearances to run through the pipeline:
- `NGsi2PC4y68` — Invest Like the Best, "Why the Markets Are Pricing AI Wrong" (2026-08-04, 1:18:44)
- `MmNWwIYFBeI` — Aria Networks launch, "MFU Is the Most Important Metric in AI" (2026-04-16, 9:31)

Pipeline: targets → fetch → manifest → extract → aggregate → audit → reaudit →
[PAUSE: basket curation gate] → returns. Per operator, stop at the gate.

## 2026-08-10 — STEP 0 (targets.py)
- Added both IDs to `YOUTUBE_VIDEOS` in a dated block. Both are solo Baker
  appearances (interviewee / featured speaker) → full attribution to Baker, no
  co-guest split (unlike the All-In / Heller House entries from the 6-new task).

## 2026-08-10 — STEP 1/2 DEVIATION + RECOVERY (manifest truncation)
- **What happened:** Following PIPELINE_MAP's "Minimal re-run" recipe, I ran
  `fetch_youtube NGsi2PC4y68 MmNWwIYFBeI` (specific IDs) then `build_manifest`.
  `write_step_manifest` OVERWRITES `youtube/_manifest.json` with only the current
  run's rows, so it dropped from 31→2 rows. `build_manifest` keeps only rows
  present in per-step manifests, so `_master_manifest.json` truncated 45→16.
- **Root cause:** `fetch_youtube <ids>` is not additive to the per-step manifest;
  the documented minimal-re-run recipe is unsafe when passing specific IDs.
- **Fix:** re-ran `fetch_youtube` with NO args (all 33 IDs; idempotent —
  existing files return `skipped_exists`, no network), then `build_manifest`.
  Verified master = 47 = 45 prior + the 2 new; LOST set empty. No coverage lost.
- **GUARD / recommendation for operator:** always run `fetch_youtube` with no
  args (full corpus) before `build_manifest`, OR make `write_step_manifest`
  merge-by-id instead of overwrite. Flagged to operator. Did NOT modify the tool
  (out of task scope).

## 2026-08-10 — STEPS 3–6 results
- extract_theses: Aria=7, ILTB=20 (27 new), 0 errors, $0.28. aggregate → 589.
- audit_theses: 27 ok, 0 errors, $0.24. timeline_v2 = 589.
- reaudit_tickers: 0 of 27 new qualified (verified via selection_reason: max 4
  tickers < A(≥5); no ETFs (C); T3/T4 mega-caps in-text so not orphan (B)). Correct no-op.

## 2026-08-10 — CURATION GATE analysis (see two_new_appearances_curation_gate.md)
- Clustering (regex, dry — cluster_theses only, no EODHD): 12 clustered / 15 unclustered.
- **Substring false positives found** (regex keys lack \b boundaries): ARIA T1
  (tpu←"output"), ARIA T5 (dram←"dramatically"), ILTB T14 (cien←"sample-efficient"),
  ILTB T3 (compute.*scale on hyperscaler compute repricing). Recommended null via
  cluster_overrides. Systemic corpus-wide regex issue flagged, NOT fixed (scope).
- UNIVERSE (78 names): all real new tickers present; only SPACEX/HYNIX/SAMSUNG NO_DATA.
- PAUSED at gate per operator instruction. No overrides applied, returns NOT run.

## 2026-08-10 — POST-GATE: operator decisions + returns
- Operator decisions: (1) null the 4 false positives — APPLIED as cluster_overrides
  in manual_overrides.json; (2) leave T4/T7/T9 as noise — no action; (3) no new themes.
- Verified overrides: re-clustered new theses + apply_cluster_overrides → all 4
  removed, legit clusters (Orbital T11/T12, Inference-econ T3/T6, AI-networking T2) kept.
- Deliverable version bump v7→v8: edited OUTPUT_CSV/XLSX in build_repeat_mention_events.py
  (v7 preserved on disk for diff, matching the 6-new task's v6→v7 convention).
- STEP 7 theme_returns_v2 --force-refetch: extended EODHD cache to 2026-08-07; v5 = 150 rows.
- STEP 8 build_repeat_mention_events → v8: **238 rows (+8 vs v7), 0 dropped, 0 return
  changes on 230 pre-existing events, 4 mention renumbers (Apr-16 insertion).** See
  v7_to_v8_changelog.md. Slice: signal n=45 ret_1y 240.5% (unchanged); control n=134.
- Commit: held per operator until after returns; one coherent commit (see below).
