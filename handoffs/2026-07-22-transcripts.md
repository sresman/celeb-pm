## Handoff -- transcripts -- 2026-07-22

**Session duration**: extended (multi-task)
**Workstream**: transcripts (Baker corpus thesis-scoring + 13F AI-signal layer)
**Working branch**: `baker-corpus-audit-rescore-2026-07`

### What was built
Baker thesis-scoring (basket resolutions finalized):
- `analysis/basket_reresolution_v2.csv` (+ `_implementation_notes.md`) — second-opinion re-resolution of all
  241 events via `claude-opus-4-6` (review artifact; nothing auto-applied).
- `analysis/manual_overrides.json` — applied operator's v4 review (102 event overrides) + 2 theme-level
  NO_BASKET macro themes; 42 `cluster_override` removals of misclustered theses + 8 NO_BASKET flags; 3
  targeted corrections (Edge-AI→DRAM, China embargo→NO_BASKET, TPU-roundtripping→NVDA-moat).
- `tools/transcripts/theme_returns_v2.py` — added cluster_override removal support (null `to_theme`) +
  `thesis_id` matching; extended `UNIVERSE` (WMT/HD/LOW/COST/KR/000660.KS); fixed `OUTPUT_FIELDS` (was
  missing override_note + flag cols → DictWriter crash).
- `analysis/step4_signal_events_v6_with_returns_extended.{xlsx,csv}` + `step4_signal_events_v5.csv` +
  `13f_signal_triggers_clean.csv` — regenerated outputs. Diffs: `analysis/basket_v4_application_diff.md`,
  `analysis/clustering_fix_diff.md`.

13F AI-signal layer:
- `analysis/ai_basket_reclassification.json` — added `U → "AI/World Models"` (RBLX deliberately excluded).
- `analysis/ai_basket_definition.json` — regenerated (AI/World Models in ramp + thematic).
- `tools/transcripts/build_13f_analysis.py` — ramp trigger rebuilt on **net buying** (`compute_net_buying`
  from positions.json share deltas, ≥5% of portfolio) instead of weight drift; per-ticker detail + per-filing
  units normalization; new CSV columns.
- `tools/transcripts/build_trigger_workbook.py` — added 8 buying-detail columns (net/gross %, $,
  tickers_bought/sold/new/exited) to the **Ramp** and **RampBasket** sheets.
- `analysis/trigger_analysis.xlsx` — regenerated.
- `docs/implementation_notes/13f_signal_triggers_implementation_notes.md` — decision log (Unity, net-buying, detail cols).

### Decisions made
Full rationale in `workstreams/transcripts-decisions.md` (2026-07-22). Key ones:
- **cluster_override removal is `from_theme`-scoped** (multi-clustered theses survive in the correct theme);
  matched removals by CONTENT because the task's `Tn` labels were ~45% wrong vs the timeline.
- **Ramp = deliberate net buying, not weight drift** — weight rises on price alone (May-2026 fired +13.7pt
  while a net seller). Fires on net_buying_pct ≥ 5%.
- **Exits NOT counted as selling** (`COUNT_EXITS=False`) — spec text said count them, but excluding exits
  reproduces the operator's exact targets (May-2025 = $561,990,623 ≈ $562M). Toggle documented.
- **value_reported units normalized per filing** ($thousands pre-2023-Q4 vs whole-$ after; detect via max
  implied price/share ≥$15). Percent columns are ratios so unit-safe.
- **Two macro themes → theme-level NO_BASKET**, superseding an earlier v4 NVDA CHANGE (latest review wins).

### Current state
Both threads complete and operator-reviewed. `mypy --strict` clean on all four touched modules
(theme_returns_v2, build_repeat_mention_events, build_13f_analysis, build_trigger_workbook). Both deliverable
workbooks/sheets regenerated and verified (May-2025 ramp fires at +$562M; May-2026 does not; Unity in every
held ramp filing incl. May-2026; other trigger sheets untouched — NewSubtheme 15 / NewPosition 31 / Cross4pct
22 / Cross2pct 28). Committing this session's work on `baker-corpus-audit-rescore-2026-07`.

### Known issues
- **DRAM = 9 scored mentions, not the requested 7** — all 9 are genuine HBM/DRAM theses; the 7 target
  predates the corpus gap-fill. Operator to decide which 2 (if any) to drop.
- **Unity absent from NewPosition sheet** — its Q4-2024 entry equity weight is 1.88% (< 2% threshold), so it
  fires NEW_AI_SUBTHEME not NEW_AI_POSITION_2PCT. Operator's 2.7%/6.7% figures are a non-13F-equity basis.
- **May-2026 net-buying = −$122M vs operator's stated ~−$109M** (~$13M gap; both net-selling → no fire either
  way). Basis of the −$109M unknown.
- **Minor**: `15.0`/`1000.0` units constants in `compute_net_buying` are inline (documented) — could be module constants.
- Not committed: `analysis/trigger_analysis with graphs.xlsx` is the operator's own Jul-17 presentation copy (left untracked).

### Next step
Await operator direction on the DRAM 9-vs-7 question (which 2 mentions to drop, if any). If dropping: add the
`cluster_override` null removals for the chosen (theme, date, thesis_id) pairs in `analysis/manual_overrides.json`,
then re-run `python -m tools.transcripts.theme_returns_v2 && python -m tools.transcripts.build_repeat_mention_events`
(with `.env` sourced) and re-verify DRAM count in `step4_signal_events_v6_with_returns_extended.xlsx`.

### Parallel work available
- Cross-reference transcript theses ↔ 13F signals (join `thesis_timeline_v2_flat.json` to
  `13f_signal_triggers_clean.csv` on ticker+date) — now that basket resolutions are settled.
- Presentation/deliverable layer (operator's `trigger_analysis with graphs.xlsx`) — only after analysis sign-off.

### Context to load
`workstreams/transcripts.md`, `workstreams/transcripts-decisions.md` (2026-07-22 section),
`analysis/basket_v4_application_diff.md`, `analysis/clustering_fix_diff.md`,
`docs/implementation_notes/13f_signal_triggers_implementation_notes.md`.
