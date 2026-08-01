## Handoff -- transcripts -- 2026-08-01

**Session duration**: extended (full pipeline run + fixes)
**Workstream**: transcripts (Baker corpus → signal events)
**Branch**: `main` (baker-corpus-audit-rescore-2026-07 was merged to main + deleted). Pushed: `17b1488`.

### What was built
6 new Baker appearances processed end-to-end through the transcript→step4 pipeline (corpus 39→45
transcripts, 507→562 theses) → new deliverable **v7**.
- `tools/transcripts/targets.py` — +3 YouTube entries (All-In E125 `WvTTDxMuAis`, All-In tariffs
  `wu-p5xrJ8-E`, Heller House `jOgbqt04eUk`); Heller re-add documented as a reversal of the 2026-07-08 removal.
- `transcripts/whisper/2021-08-09_cnbc_sharpe_angle_spacs_2021aug.txt`,
  `transcripts/whisper/2026-07-20_cnbc_spacex_drawdown_2026jul.txt` — Whisper `small` transcriptions of
  the two caption-less CNBC videos (HLS `hls-264` audio → mp3 → whisper on CPU).
- `transcripts/web/2021-12-03_sohn_australia_2021_coinbase.txt` — labeled `secondary_coverage` web
  transcript (primary source gated/404, no YT mirror) + `transcripts/web/_manifest.json` entry.
- `transcripts/{youtube,whisper,web}/_manifest.json` + `transcripts/_master_manifest.json` (45) +
  `transcripts/master_manifest_v2.json` (49 = 45 + 4 BIC placeholders) rebuilt/reconciled.
- `analysis/thesis_extractions/` (+6), `thesis_audits/` (+55), `thesis_reaudits/`, `thesis_timeline*.json`,
  `all_summaries.json`, `_extraction/_audit/_reaudit_log.json` — regenerated (extract→aggregate→audit→reaudit).
- `analysis/theme_baskets_v3.json` — new theme `Crypto / Coinbase (COIN)` + 3 keys.
  `tools/transcripts/theme_returns_v2.py` — `COIN` added to UNIVERSE.
- `analysis/manual_overrides.json` — 15 Heller `cluster_override` null removals; **all 73 dated
  event-overrides date-anchored** (mention_number stripped).
- `tools/transcripts/build_repeat_mention_events.py` — OUTPUT bumped v6→v7.
- Deliverable: `analysis/step4_signal_events_v7_with_returns_extended.{csv,xlsx}` (+ v5.csv regen).
- Docs: `analysis/v6_to_v7_changelog.md`, `analysis/six_new_appearances_curation_gate.md`,
  `analysis/six_new_appearances_implementation_notes.md`, `journal.txt` (created fresh).

### Decisions made
SD-6NEW-1…3 in `workstreams/transcripts-decisions.md` (2026-08-01). In brief:
- **Heller House → 0 scored.** Video is Baker *interviewing* the SpaceX CFO; the 11 extracted theses are
  the CFO's operational claims, not Baker's views, and they clustered into tradeable AI/space baskets.
  Operator chose full removal (matches the earlier red-herring removal). Kept extractions on disk.
- **Coinbase → new theme + UNIVERSE entry** (clear high-conviction single-stock pick; no crypto basket existed).
- **3 new keys, blackwell/hopper declined** — only added ticker/basket-connected keys with a small,
  operator-reviewed blast radius; declined the 15/4-thesis blackwell/hopper keys.
- **Event overrides date-anchored (root-cause fix).** Renumbering from earlier-dated appearances broke
  `(date, mention_number)` overrides (9 SpaceX reverted baskets). `mention_number` is redundant+fragile;
  `(theme,date)` is unique in the grain. Stripped it from all 73 dated matches → renumbering-proof.

### Current state
Fully done and **pushed to main** (`17b1488`). v6→v7: +15 events, 0 removed, 0 basket/return changes on
pre-existing rows, 21 pure mention renumbers. mypy --strict clean on touched modules. Price cache refreshed
through 2026-07-21 (COIN fetched). Wrap-up doc changes (this handoff + workstream + decisions updates) are a
separate follow-on commit.

### Known issues
- **All-In E125 (2023-04-21) Starship theses** likely trace to co-guest Antonio Gracias, not Baker — they
  drive the new SpaceX/Optical 2023-04-21 events. Operator to decide keep/drop (standard All-In multi-speaker caveat).
- **`journal.txt` created fresh** — no prior journal existed in-repo or git history; confirm intended location/format.
- **2026-07-20 events** have INSUFFICIENT_DATA returns (2 days old at run time) — refresh once ~1q accrues.
- Private tickers (Anthropic/OpenAI/xAI/SpaceX) remain in tickers_direct → resolve NO_DATA (harmless).
- Untracked `docs/specs/monitoring_system_spec.md` is NOT from this work — left alone (belongs to another effort).
- Whisper `small` garbles some proper nouns (drawdown: "Motron"→Nemotron, "Kimi K3") — audit mitigates tickers.

### Next step
Operator decides the All-In E125 Gracias-attribution question. If dropping those theses: add
`cluster_override` null removals for the (theme, 2023-04-21, thesis_id) pairs in `analysis/manual_overrides.json`,
then re-run `python -m tools.transcripts.theme_returns_v2 && python -m tools.transcripts.build_repeat_mention_events`
(with `.env` sourced; cache is fresh so no `--force-refetch` needed) and re-diff v6→v7.

### Parallel work available
- Cross-reference transcript theses ↔ 13F signals (`thesis_timeline_v2_flat.json` ↔ `13f_signal_triggers_clean.csv`
  on ticker+date) — now that basket resolutions + Coinbase theme are settled.
- Presentation/deliverable layer (operator's `analysis/trigger_analysis with graphs.xlsx`).

### Context to load
`workstreams/transcripts.md` (2026-08-01 Current State), `workstreams/transcripts-decisions.md`
(2026-08-01 / SD-6NEW-1…3), `analysis/v6_to_v7_changelog.md`,
`analysis/six_new_appearances_implementation_notes.md`, `analysis/PIPELINE_MAP.md`.
