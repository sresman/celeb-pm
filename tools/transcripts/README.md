# Gavin Baker transcript corpus

Standalone data-acquisition tooling that downloads transcripts of Gavin Baker
(Atreides Management) public appearances into `transcripts/` for later NLP/signal
analysis against his 13F filings. **Independent of the `src/celebpm` 13F pipeline.**

## Run it

```bash
# full corpus (idempotent -- skips files that already exist)
.venv/bin/python -m tools.transcripts.run_all

# force re-download everything
.venv/bin/python -m tools.transcripts.run_all --force
```

Individual steps:

```bash
.venv/bin/python -m tools.transcripts.fetch_youtube           # Step 1 (all known IDs)
.venv/bin/python -m tools.transcripts.fetch_youtube <id> ...  # Step 1 (specific IDs)
.venv/bin/python -m tools.transcripts.discover_youtube        # find new IDs (review gate)
.venv/bin/python -m tools.transcripts.fetch_colossus          # Step 2
.venv/bin/python -m tools.transcripts.fetch_web               # Step 3
.venv/bin/python -m tools.transcripts.fetch_text              # Step 4
.venv/bin/python -m tools.transcripts.fetch_cnbc              # Step 6
.venv/bin/python -m tools.transcripts.build_manifest          # master manifest + coverage
```

## Dependencies

`yt-dlp`, `requests`, `beautifulsoup4`, `lxml`, `pypdf` (all installed).
`ffmpeg` present. Whisper (Step 5) is optional and NOT installed -- see below.

## Design

- **`targets.py`** is the single source of truth: every video ID, URL, search
  query, output path, and the User-Agent. Fetchers contain no embedded targets.
- **`common.py`** holds the shared HTTP session, the yt-dlp json3 -> `[MM:SS]`
  converter, the file writer, and manifest helpers.
- Every fetcher is **idempotent** (skips existing files unless `--force`) and
  writes a per-step `_manifest.json` with a `status` per target.
- **YouTube uses `yt-dlp`** (not `youtube-transcript-api`) -- it is installed,
  works from this network, and avoids the transcript-API IP blocking.

## Output layout

```
transcripts/
  youtube/    <date>_<label>_<id>.txt   + _manifest.json   (21 files, auto-captions)
  colossus/   _manifest.json            (no full transcripts -- see gaps)
  web/        <date>_<label>.txt        + _manifest.json   (HedgeFundAlpha writeups)
  text/       <date>_<label>.txt        + _manifest.json   (themarket ledes, G&D PDF)
              + _manifest_cnbc.json
  whisper/    (empty -- Step 5 not needed)
  _master_manifest.json                 (every obtained transcript + coverage)
```

Quality tiers (in the manifest `quality` field): `youtube_auto`,
`writeup_public_portion`, `pdf_extracted`, `paywalled_lede`,
`article_summary_no_captions`, `whisper_<model>`.

## Coverage (as built)

**27 transcripts obtained.** 21 YouTube auto-transcripts (Nov 2019 -> Jun 2026,
including On The Tape + Thematic Investors, which were originally audio-only), the
Graham & Doddsville Issue 43 interview (full, ~42k chars), 2 HedgeFundAlpha
conference writeups (public portion), and 3 themarket.ch ledes (paywalled).

### Known gaps / decisions

- **happyscribe** -- dropped (hard 403 from this network). Its All-In "2025
  Predictions" episode is covered via YouTube (`HxNUAwBWX4I`).
- **Colossus full transcripts** -- the site renders transcripts client-side; the
  static HTML carries only a ~130-word teaser. The 2 newest episodes
  (watts-wafers, GPUs/TPUs) are covered by their YouTube mirrors. The 4 older
  ILTB episodes (AI-semis-robotic 2024, cyclone 2022, bear-market 2020,
  tech-consumer 2019) have **no YouTube mirror** and the spec's Colossus slugs
  404 -- they remain **uncovered**. To close: find the correct Colossus URL and
  JS-render it, or Whisper the ILTB RSS audio.
- **themarket.ch** -- hard paywall; only the public lede (~300-400 chars) is
  saved per interview, tagged `paywalled_lede`.
- **CNBC Sharpe Angle video** -- no caption track (verified) and the article
  blurb is too thin to save; uncovered without Whisper.
- **Date fields** are best-effort. Note: `allin_dram_bottleneck_2024mid`
  (`w8ah_tA0yfg`) has a title implying a mid-2025 episode -- its `2024-06-15`
  date is suspect and should be reconciled if dates are used downstream.

## Step 5 (Whisper) -- optional, not run

Both originally audio-only targets were found as YouTube mirrors, so Whisper is
unnecessary for the current corpus. `fetch_audio_whisper.py` remains as ready
tooling for any future audio-only appearance with no YouTube mirror:

```bash
pip install openai-whisper        # pulls torch (~2-3 GB); ffmpeg already present
.venv/bin/python -m tools.transcripts.fetch_audio_whisper --model medium
```

## Adding new appearances

1. Run `discover_youtube.py` (or add URLs/IDs you already have).
2. Add confirmed entries to the relevant list in `targets.py`.
3. Re-run the relevant fetcher (or `run_all`) -- only new targets are pulled.

## Post-processing (future, not built)

YouTube auto-captions garble some proper nouns (TSMC -> "TSM C", Trainium ->
"training him"). A simple find/replace cleanup pass could be added before NLP.
