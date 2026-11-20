## Handoff -- transcripts -- 2026-11-20

**Session duration**: one long session (discovery → appearances → attribution → re-audit → curation → v12)
**Workstream**: transcripts

### What was built
Branch `transcripts-nov-2026` (pushed, NOT merged): `ee84d1e` v11 unchanged · `56eca2f` Nov appearances · `ee0f8c2` first wrap-up · `e9363c7` re-audit catch-up · `0ded55d` v12 · plus this wrap-up commit.
- Corpus 51 → 54 appearances, 648 → 673 theses (CNBC Squawk 2026-11-17, TomorrowX opening 2026-11-17, Sourcery 2026-11-19; Boston 2026-10-29 has no recording and is a comment only).
- `analysis/thesis_reaudits/` +6, `_reaudit_log.json`, 21 audit files gained attribution overlay fields (values identical to the timeline).
- `analysis/theme_baskets_v3.json`: keyword additions to 7 themes and a new theme "Enterprise on-prem AI factories" (DELL).
- `analysis/thesis_audits/2026-11-17_tomorrowx_opening_session_2026nov_T3.json`: TSMC → TSM.
- `tools/transcripts/build_repeat_mention_events.py`: output constant v11 → v12.
- `analysis/step4_signal_events_v12_with_returns_extended.{csv,xlsx}` (234 rows / 177 repeat / 80 criteria); `step4_signal_events_v5.csv` regenerated.
- Log: `analysis/transcripts_nov2026_implementation_notes.md`.

### Decisions made
See `workstreams/transcripts-decisions.md` (both 2026-11-20 entries). Key points: moderator sessions are excluded (Heller House); unclustered theses get keyword additions, not cluster_overrides; malformed tickers are fixed in the audit file; Opening T8 (retail) stays unthemed; supply-constraint theses go in TSMC capacity discipline.

### Current state
v12 is built on the original attribution instrument, subject filter. Rows before 2026-10-27 differ from v11 only in `total_theme_mentions` and one `tickers_direct` display. Signals since 2026-10-27: mention 2 = ALAB / copper vs fiber 2026-11-19 (ALAB). TomorrowX opening fires high-profile-venue rows on AI bubble not happening (SMH), TSMC capacity discipline (NVDA, AVGO, MU) and Broad AI bullish (NO_BASKET). Enterprise AI factories 2026-11-19 fires first-with-tickers (DELL). No new row has returns yet (prices end 2026-11-19). mypy clean, pytest green.

### Known issues
- The v11 curation backlog was not done: TBPN Oct 11/14 and All-In 2025-08-09 7/9 subject theses are still unthemed.
- `reaudit_tickers` is corpus-wide with no scope filter; `fetch_youtube <ids>` truncates the YouTube manifest (the PIPELINE_MAP minimal re-run shows that form). Neither changed.
- CNBC and Sourcery were recorded at TomorrowX but aren't high-profile venues (their source strings lack "iconn"). That's the existing rule, kept by the operator.
- `.env` line 6 breaks shell sourcing (harmless; the modules use dotenv).

### Next step
Operator: review/merge `transcripts-nov-2026`. Then either curate the v11 backlog (TBPN Oct + All-In unthemed theses; `analysis/theme_baskets_v3.json`) or start v13 = roster cleanup in `tools/transcripts/targets.py` → cue-instrument corpus re-audit (see the workstream's "next run" block).

### Parallel work available
- `q3-2026-13f` merge decision (main workstream).
- A returns refresh after ~2026-12-17 (1m on the Nov rows).

### Context to load
`analysis/transcripts_nov2026_implementation_notes.md` · `workstreams/transcripts-decisions.md` · `analysis/v11_implementation_notes.md` · `analysis/theme_baskets_v3.json`.
