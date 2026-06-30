## Handoff -- transcripts -- 2026-06-30

**Session duration**: extended (two tasks: corpus build, then thesis extraction)
**Workstream**: transcripts (new — `workstreams/transcripts.md`)
**Branch**: `gavin-baker-transcript-corpus` (3 commits this session; pushed)

### What was built
Task 1 — **Transcript corpus** (`tools/transcripts/`, `transcripts/`):
- `targets.py` (single source of truth), `common.py` (UA session, json3→`[MM:SS]`, writers/manifest).
- Fetchers: `fetch_youtube.py` (yt-dlp auto-subs), `discover_youtube.py` (ytsearch review gate),
  `fetch_colossus.py`, `fetch_web.py`, `fetch_text.py`, `fetch_cnbc.py`, `fetch_audio_whisper.py`
  (optional, unused), `build_manifest.py`, `run_all.py`, `README.md`.
- Output: 27 transcripts in `transcripts/{youtube,colossus,web,text}/` + `_master_manifest.json`.

Task 2 — **Thesis extraction** (`tools/transcripts/`, `analysis/`):
- `extraction_prompt.py` — operator's SYSTEM_PROMPT/USER_TEMPLATE + EXTRACTION_SCHEMA (JSON Schema).
- `extract_theses.py` — `claude-sonnet-4-6` runner; `.env` key load w/ override; schema enforced via
  `output_config.format`; stop-reason + retry handling; token/cost log; `--force/--limit/--single`.
- `aggregate_theses.py` — `all_summaries.json` + flat date-sorted `thesis_timeline.json`.
- Output: 27 per-transcript JSONs, 319 theses total, `_extraction_log.json`.

### Decisions made
- **yt-dlp over youtube-transcript-api**: the spec's tool was uninstalled and IP-block-prone; yt-dlp
  was installed and confirmed working from this network. Drove Step 1 of the corpus.
- **Structured outputs** (`output_config.format` with the spec's schema): guarantees valid JSON, so
  the spec's prompt-only "JSON + `.raw` fallback" path becomes a near-dead safety net. Operator-confirmed.
- **Model claude-sonnet-4-6**: operator-chosen for cheap/fast structured extraction (vs the usual
  Opus default). $3/$15 per MTok; full corpus ≈ $3.36.
- **Key from `.env` with `override=True`**: the shell `ANTHROPIC_API_KEY` is a 15-char placeholder;
  the real `sk-ant-` key is in `.env`. Loader asserts the prefix and fails fast.
- **Pragmatic rigor** (operator-approved): type hints + structure, no mocked pytest; corpus committed.
- **Gate-2 discovery** added 10 confirmed appearances (incl. YouTube mirrors of both audio-only
  episodes → Whisper became unnecessary); excluded All-In 2026 (not Baker) + a Koyfin dup; included
  VS Partners (Baker confirmed in description).

### Current state
Both tasks COMPLETE. 27/27 transcripts extracted, 319 theses, mypy clean, all committed and pushed.
Spot-checks verified the three spec targets (Sohn NY 2026 → TSMC/Trainium/orbital compute; All-In
2025 → HBM/DRAM/robotics; ILTB Dec 2025 → Nvidia-vs-Google/scaling laws). `thesis_timeline.json` is
valid and date-sorted. The pre-existing `src/celebpm` SMH/View-3 working changes were left untouched.

### Known issues
- **Corpus gaps (documented in `tools/transcripts/README.md`):** 4 older ILTB episodes
  (AI-semis-robotic 2024, cyclone 2022, bear-market 2020, tech-consumer 2019) — no YouTube mirror,
  Colossus transcripts are JS-gated; CNBC Sharpe Angle video has no caption track. Not extracted.
- **1 zero-thesis extraction:** `themarket_semiconductors_magic` — a ~278-char paywalled lede;
  expected for sparse input, not a bug.
- **Data flag:** `allin_dram_bottleneck_2024mid` (`w8ah_tA0yfg`) title suggests a mid-2025 episode;
  its `2024-06-15` date is suspect — reconcile if dates are used downstream.
- **youtube_auto garbling:** proper nouns occasionally mangled (TSMC→"TSM C"); the extractor infers
  from context, but a cleanup pass before any re-extraction would help.

### Next step
Begin the **second-pass cross-reference**: join `analysis/thesis_timeline.json` (theses tagged with
date/source/confidence/themes/tickers_named/tickers_implied) against the Atreides 13F position data
(`src/celebpm`, CIK 0001777813) — e.g. does a high_conviction thesis precede a corresponding 13F
add/new position, and how did it perform on the filing-date anchor. The timeline is the join-ready shape.

### Parallel work available
- Proper-noun cleanup pass over the youtube_auto transcripts (independent of the 13F join).
- Closing corpus gaps (4 older ILTB episodes via Whisper on the ILTB RSS audio; CNBC via Whisper).
- The 13F pipeline workstream (`workstreams/main.md`) is fully independent.

### Context to load
`workstreams/transcripts.md`, `tools/transcripts/README.md`, `tools/transcripts/extraction_prompt.py`,
`transcripts/_master_manifest.json`, `analysis/thesis_timeline.json`. For the join: `workstreams/main.md`
(13F pipeline outputs: `data/<slug>/{changes,returns,positions}.json` + view CSVs).
