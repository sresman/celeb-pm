# Baker Transcript → Signal-Events Pipeline Map

> Audit as of 2026-07-22. Covers the full chain from a raw YouTube URL to
> `analysis/step4_signal_events_v6_with_returns_extended.{xlsx,csv}`.
> All code in `tools/transcripts/`; all data in `transcripts/` + `analysis/`.
> Run from repo root using `.venv/bin/python -m tools.transcripts.<module>` with `.env` sourced.

## Prerequisites
- `.venv/bin/python` (3.11). `yt-dlp` + `ffmpeg` on PATH (present). `whisper` NOT installed (only needed for audio-only fallback).
- `.env` must hold real keys: `ANTHROPIC_API_KEY` (must start `sk-ant-`; loaded with `override=True`), `EODHD_API_KEY`.
- Models are operator-chosen constants: extraction/audit = `claude-sonnet-4-6`; basket re-resolution review = `claude-opus-4-6`.

---

## THE PIPELINE (transcript → step4 deliverable)

```
STEP 0: Register the appearance  [MANUAL — hand-edit]
  File: tools/transcripts/targets.py
  Action: add one entry to YOUTUBE_VIDEOS, keyed by the 11-char video ID:
     "<VIDEO_ID>": {"label": "...", "date": "YYYY-MM-DD", "source": "...",
                    "host": "...", "topic": "..."}
  Notes: targets.py is a hardcoded registry. A URL/ID passed on the CLI that is
         NOT already in the dict is SKIPPED with a WARN. There is no "pass a URL"
         path — you must add it here first. (Non-YouTube sources use ScrapeTarget/
         TextTarget/RssTarget dicts and the fetch_web/fetch_text/fetch_audio_whisper
         fetchers instead.)

STEP 1: Fetch transcript(s)
  Script: tools/transcripts/fetch_youtube.py   (yt-dlp English auto-captions → json3 → [MM:SS] text)
  Command: .venv/bin/python -m tools.transcripts.fetch_youtube <id1> ... <id6>   # or no args = all
  Input:  targets.YOUTUBE_VIDEOS
  Output: transcripts/youtube/<date>_<label>_<id>.txt  +  transcripts/youtube/_manifest.json
  Notes:  Idempotent (skips existing unless --force). "Sign in to confirm" → status
          `bot_wall`; would need cookies (no CLI flag today) or Whisper fallback.
  Other sources (run only if that source applies):
    fetch_colossus / fetch_web / fetch_text / fetch_cnbc  → transcripts/{colossus,web,text}/
    fetch_audio_whisper (audio-only, no YT mirror; needs `whisper` binary) → transcripts/whisper/
  Orchestrator: `run_all.py [--force] [--whisper]` runs ALL fetchers + build_manifest
    in order (youtube→colossus→web→text→cnbc→[whisper]→manifest). Corpus only —
    does NOT run extraction or anything downstream.

STEP 2: Build master manifest
  Script: tools/transcripts/build_manifest.py
  Command: .venv/bin/python -m tools.transcripts.build_manifest
  Input:  every transcripts/*/_manifest*.json (per-step manifests)
  Output: transcripts/_master_manifest.json  (git-tracked; keeps only rows whose file exists)
  Notes:  9 fields/entry: date, source, label, host, topic, filepath, quality, status, url.
          Regenerates ONLY _master_manifest.json — does NOT touch master_manifest_v2.json (see Known Issues).

STEP 3: Extract theses  [Anthropic API — claude-sonnet-4-6]
  Script: tools/transcripts/extract_theses.py
  Command: .venv/bin/python -m tools.transcripts.extract_theses          # skips existing; add --force to redo all
  Input:  transcripts/_master_manifest.json + each transcript file + extraction_prompt.py
  Output: analysis/thesis_extractions/<date>_<label>.json (one per transcript) + analysis/_extraction_log.json
  Notes:  Schema enforced via API structured output (output_config.format = json_schema) →
          guaranteed-valid JSON. MAX_TOKENS 8192 (retry 16000 on max_tokens). Transcript
          truncated at 150k chars. ~$2 for the full corpus. Idempotent unless --force.
          Flags: --limit N, --single PATH.

STEP 4: Aggregate  [local, no API]
  Script: tools/transcripts/aggregate_theses.py
  Command: .venv/bin/python -m tools.transcripts.aggregate_theses
  Input:  analysis/thesis_extractions/*.json
  Output: analysis/all_summaries.json  +  analysis/thesis_timeline.json  (v1, LOSSY — drops detail/evidence/etc.)
  Notes:  Always fully rebuilds both files from whatever is on disk (old + new).

STEP 5: Audit theses  [Anthropic API — claude-sonnet-4-6]
  Script: tools/transcripts/audit_theses.py
  Command: .venv/bin/python -m tools.transcripts.audit_theses            # skips existing; --force to redo
  Input:  analysis/thesis_extractions/*.json (source of truth) + audit_prompt.py
  Output: analysis/thesis_audits/*.json (one per thesis) + analysis/_audit_log.json
          + analysis/thesis_timeline_v2.json  AND  analysis/thesis_timeline_v2_flat.json
            (identical content; rebuilt from ALL on-disk audit files)
  Notes:  Expands summary→summary_extended (3-5 sentences), cleans/classifies tickers
          (tickers_direct = DIRECT_SUBJECT + DIRECT_BENEFICIARY). MAX_TOKENS 2048. ~$2.3 corpus.
          thesis_timeline_v2_flat.json is AUTHORITATIVE downstream. Flags: --limit, --single IDX.

STEP 6: Re-audit tickers (strict removal pass)  [Anthropic API — claude-sonnet-4-6]
  Script: tools/transcripts/reaudit_tickers.py
  Command: .venv/bin/python -m tools.transcripts.reaudit_tickers        # skips existing; --force to redo
  Input:  analysis/thesis_timeline_v2_flat.json + analysis/thesis_audits/*.json
  Output: rewrites thesis_timeline_v2.json + _flat IN PLACE; analysis/thesis_reaudits/*.json;
          patches thesis_audits/*.json (so rebuilds don't revert); analysis/_reaudit_log.json
  Notes:  Only theses meeting A/B/C criteria (>=5 tickers, orphan mega-caps, or an ETF)
          hit the model — removal-only. Idempotent (re-applies stored decision even when skipping).

--- MANUAL CURATION (hand-maintained JSON — edit as new tickers/themes appear) ---
  analysis/theme_baskets_v3.json      59 themes: regex keys/exclude (clustering) + basket tickers +
                                      direction + date_segments. Add a theme/keys for any new sub-thesis.
  analysis/manual_overrides.json      cluster_overrides (re-theme/remove a thesis) + event_overrides
                                      (force basket/source/direction/flags). Survives rebuilds; overrides win.
  (Optional review aid) reresolve_baskets.py [claude-opus-4-6] → analysis/basket_reresolution.csv
                                      Second-opinion "is this a trade + which tickers" over every event.
                                      APPLIES NOTHING. Operator triages rows into manual_overrides.json.

STEP 7: Compute returns — criterion grain (v5)  [EODHD API]
  Script: tools/transcripts/theme_returns_v2.py
  Command: .venv/bin/python -m tools.transcripts.theme_returns_v2 [--force-refetch]
  Input:  analysis/thesis_timeline_v2_flat.json + theme_baskets_v3.json + manual_overrides.json
  Output: analysis/step4_signal_events_v5.csv   (ONE ROW PER CRITERION-TRIGGERED EVENT)
  Notes:  cluster → 7-type event state machine → date-aware basket → EODHD adj-close → EW basket
          return + SMH benchmark + excess at 1m/1q/1y/2y. Benchmark = SMH; SPY = trading calendar only.

STEP 8: Build the DELIVERABLE — mention grain (v6 extended)  [EODHD API]
  Script: tools/transcripts/build_repeat_mention_events.py
  Command: .venv/bin/python -m tools.transcripts.build_repeat_mention_events [--force-refetch]
  Input:  analysis/thesis_timeline_v2_flat.json + theme_baskets_v3.json + manual_overrides.json
          (regenerates independently; does NOT read step4_signal_events_v5.csv)
  Output: *** analysis/step4_signal_events_v6_with_returns_extended.csv + .xlsx ***  (THE DELIVERABLE)
  Notes:  ONE ROW PER (theme, unique-mention-date). Adds is_repeat_mention + the 4 criteria as
          separate booleans + meets_existing_criteria. Returns at 7 horizons
          (1m/1q/6m/9m/1y/18m/2y) vs BOTH SMH and SPY (excess vs each). SPY also = calendar.
          xlsx has a second `slice_summary` sheet (population / signal / control 3-way slice).
          Reuses all clustering/basket/override/price logic from theme_returns_v2 via import.
```

### Minimal re-run after adding N new transcripts
```
# 0. hand-edit targets.py  (add the N video IDs)
.venv/bin/python -m tools.transcripts.fetch_youtube <ids...>
.venv/bin/python -m tools.transcripts.build_manifest
.venv/bin/python -m tools.transcripts.extract_theses          # new only
.venv/bin/python -m tools.transcripts.aggregate_theses
.venv/bin/python -m tools.transcripts.audit_theses            # new only
.venv/bin/python -m tools.transcripts.reaudit_tickers         # new only
# (curate theme_baskets_v3.json / manual_overrides.json for any new tickers/themes)
.venv/bin/python -m tools.transcripts.theme_returns_v2 --force-refetch          # --force-refetch to extend price cache
.venv/bin/python -m tools.transcripts.build_repeat_mention_events --force-refetch
```

---

## SEPARATE CHAIN — 13F AI-signal triggers (different deliverable)
Fed by the `src/celebpm` 13F reconstruction output, NOT transcripts. Produces `analysis/trigger_analysis.xlsx`.
```
build_13f_analysis.py [--skip-universal]   (CANONICAL)  →  13f_signal_triggers_clean.csv,
                                             filing_to_filing_returns_universal.csv, ai_basket_definition.json
build_trigger_workbook.py                              →  trigger_analysis.xlsx (6 sheets)
  Inputs: data/atreides_management/views/{position_lifecycles,new_ideas}.csv + positions.json
          + analysis/ai_basket_reclassification.json (hand-maintained)
  Ramp trigger fires on NET BUYING >= 5% of portfolio (from positions.json share deltas), not weight drift.
  SUPERSEDED (still on disk, do not use): generate_13f_triggers.py + add_trigger_returns.py
    → 13f_signal_triggers.csv, 13f_signal_triggers_with_returns.csv, filing_to_filing_returns.csv
```

---

## AUTOMATION STATUS

**Fully automated (idempotent module runs):** fetch_youtube, build_manifest, extract_theses,
aggregate_theses, audit_theses, reaudit_tickers, theme_returns_v2, build_repeat_mention_events.

**Manual / human-in-the-loop:**
- Adding an appearance = hand-edit `targets.py` (no URL-passthrough).
- `theme_baskets_v3.json` (theme regex + baskets) and `manual_overrides.json` (basket resolutions) are hand-curated.
- `basket_reresolution.csv` is a review artifact; operator triages it into overrides (nothing auto-applies).
- No single orchestrator spans transcript→step4. `run_all.py` covers ONLY corpus fetch + manifest.

**Missing / stale / gotchas (see Known Issues below).**

---

## KNOWN ISSUES / STATE (2026-07-22)
1. **Deliverable is IN SYNC.** step4_v6_extended.{xlsx,csv} (Jul 17 08:03) is newer than all inputs
   (timeline Jul 9, baskets Jul 9, overrides Jul 17 08:03). step4_v5.csv rebuilt same time.
2. **Price cache is STALE for recent events.** analysis/eod_prices/SPY.json ends 2026-06-29 (today 07-22).
   Events after ~2026-05 get INSUFFICIENT_DATA on longer horizons; new July transcripts need `--force-refetch`
   to extend the cache to current dates before returns are meaningful.
3. **No orchestrator** transcript→step4 — each step is a separate manual module invocation.
4. **master_manifest_v2.json** (untracked, Jul 22) is an out-of-tree superset: 49 rows = the 39 real files
   + 10 not-yet-captured/private-event placeholders (filepath: null). No code reads or writes it.
   build_manifest.py regenerates v1 only and will NOT pick up v2's audit rows — divergence risk.
5. **Whisper transcripts produced out-of-tree.** whisper/ has 5 .txt (4 ILTB whisper_small + 1 CNBC Squawk
   whisper_medium) whose model/target are NOT in targets.py — re-running run_all won't reproduce them
   (they ARE in _master_manifest.json, so extraction still consumes them).
6. **Stale docstrings/README:** theme_returns_v2 docstring says "319 theses / 52 themes" (actual 507 / 59);
   README says "27 transcripts / empty whisper dir" (actual 39 files). Cosmetic.
7. **reaudit_tickers is NOT in run_all** — must be invoked manually after audit_theses.
