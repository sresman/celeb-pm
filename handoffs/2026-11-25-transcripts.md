## Handoff -- transcripts -- 2026-11-25

**Session duration**: one session (discovery → fetch → attribution → curation → v12 rebuild)
**Workstream**: transcripts

### What was built
Branch `transcripts-nov-2026` (pushed, NOT merged): `b95317c` new appearance · `babbe26` curation + v12 rebuild · plus this wrap-up commit.
- `tools/transcripts/targets.py`: registered `2XhpxKX3d0M` (Monetary Matters, 2026-11-23).
- Transcript + manifests (YouTube 38 → 39, master 54 → 55); extraction, 9 audits, 1 re-audit, attribution pass files (both instruments), resolved files, timelines.
- `analysis/theme_baskets_v3.json`: 5 keyword additions across Nvidia GPU moat, AI bubble not happening, Anthropic valuation.
- `analysis/step4_signal_events_v12_with_returns_extended.{csv,xlsx}` rebuilt in place (238 / 181 / 80); `step4_signal_events_v5.csv` regenerated.
- `analysis/transcripts_nov2026_implementation_notes.md`: two 2026-11-25 sections.

### Decisions made
See `workstreams/transcripts-decisions.md` 2026-11-25. Dated to publication; podcast + YouTube counted once; no hand attribution fix (T7 stays `other`); T6 (auditor-inferred tickers only) and T8 (risk statement) unthemed; v12 rebuilt in place.

### Current state
Corpus 55 appearances / 682 theses / 536 subject. v12: 238 mention rows, 181 repeat, 80 meet criteria (unchanged). No signal rows dated after 2026-11-19. Existing theses, verdicts and theme assignments unchanged; existing v12 rows differ only in `total_theme_mentions` (4 themes) and benchmark windows that completed with prices through 2026-11-25. mypy (`-p tools.transcripts`) clean, pytest green.

### Known issues
- Monetary Matters T7 is likely a false `other` (caption marker missing at [10:37]); left by operator decision.
- Carried over: v11 curation backlog (TBPN Oct, All-In 2025-08-09 unthemed); `reaudit_tickers` has no scope filter; `fetch_youtube <ids>` truncates the YouTube manifest (re-run no-args); `PIPELINE_MAP.md` minimal re-run still shows the ID form; `mypy tools/transcripts` (path form) prints a package-base note — use `-p tools.transcripts`.

### Next step
Operator: review/merge `transcripts-nov-2026`. Then either the v11 curation backlog (`analysis/theme_baskets_v3.json`) or v13 roster cleanup in `tools/transcripts/targets.py` → cue-instrument corpus re-audit.

### Parallel work available
- Returns refresh after ~2026-12-17 (1m on the Nov rows; 2026-11-23 rows after ~2026-12-23).
- `q3-2026-13f` merge decision (main workstream).

### Context to load
`analysis/transcripts_nov2026_implementation_notes.md` · `workstreams/transcripts-decisions.md` · `analysis/theme_baskets_v3.json`.
