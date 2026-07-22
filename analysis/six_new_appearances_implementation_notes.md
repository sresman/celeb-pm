# Implementation Notes — Processing 6 New Baker Appearances

Working log for the task "Process 6 New Baker Appearances Through the Pipeline"
(branch `baker-corpus-audit-rescore-2026-07`). Append-only, timestamped.

## 2026-07-22 — Start

### 6 target appearances
YouTube (3): allin_e125_spacex_starship_2023apr (WvTTDxMuAis, 2023-04-21),
allin_tariffs_agi_prize_2025jul (wu-p5xrJ8-E, 2025-07-17),
heller_house_spacex_cfo_2026jun (jOgbqt04eUk, 2026-06-08).
Non-YouTube (3): cnbc_sharpe_angle_spacs_2021aug (2021-08-09),
cnbc_spacex_drawdown_2026jul (2026-07-20), sohn_australia_2021_coinbase (~2021-12-03).

### CONFLICT FLAGGED — Heller House reversal (SD-6NEW-1)
`jOgbqt04eUk` / heller_house_spacex_cfo_2026jun was **previously removed** from the corpus
on 2026-07-08 (`analysis/_removed_files_log.md`): judged a RED HERRING — a reporter/host
segment profiling SpaceX CFO Bret Johnsen, "Gavin Baker is not the speaker." The removed
file was `2026-02-15_heller_house_spacex_cfo_2026.json` (note: dated 2026-02-15, vs the new
entry's 2026-06-08 — may be a different cut, or a re-dating).
The new task explicitly re-adds it, framed as "Baker as INTERVIEWER" of the CFO, WITH explicit
handling for the exact CFO-attribution risk that caused removal ("we want Baker's views, not
Johnsen's statements... flag/remove Johnsen's claims"). Read as an intentional, informed
reversal by the operator. DECISION: proceed to fetch (reversible), extract, then surface the
Heller House extraction for explicit operator sign-off at the manual gate before it flows into
scoring. Do NOT silently include Johnsen's claims as Baker theses.

### Pre-existing state discovered
- CNBC Sharpe Angle 2021 already exists in targets.py as `CNBC_TARGET` (same URL+label) — never
  captured (no file, not in _master_manifest.json). Fetch via existing fetch_cnbc pathway / yt-dlp.
- CNBC "Squawk SpaceX debut" 2026-06-12 is ALREADY captured (transcripts/whisper/...). That is a
  DIFFERENT video from the task's "CNBC SpaceX drawdown 2026-07-20". The drawdown one is new.
- `fetch_cnbc.py` handles a single `CNBC_TARGET` only — the 2026 drawdown needs a separate path.
- No `journal.txt` exists in the repo (Step 10). Will flag / propose format.
- master_manifest_v2.json is an out-of-tree planning superset (49 rows = 39 real + 6 my targets +
  4 BIC private-event placeholders). The live pipeline (extract_theses) reads v1 only.

## 2026-07-22 — Fetch results

### Heller House confirmation (SD-6NEW-1 supporting evidence)
yt-dlp actual_title = "Gavin Baker interviews SpaceX CFO Bret Johnsen at Mission Control" — Baker
IS the interviewer (Q&A format). Supports the reversal. Auto-captions do NOT label speakers
(`>>` turn markers only), so extraction cannot mechanically separate Baker from Johnsen — the
attribution risk is real and will be checked at the gate.

### Non-YouTube handling (SD-6NEW-2)
- CNBC 2021 (15:33) + CNBC 2026 drawdown (11:33): CNBC serves muxed HLS, NO captions. Downloaded
  smallest format (hls-264) audio, transcribed with local whisper `small` on CPU (openai-whisper
  installed in venv; MPS avoided as unreliable). Wrote to transcripts/whisper/ as quality
  `whisper_small`. CNBC 2026 "full interview" URL used (the .../baker-drawdown.html is a shorter cut).
- CNBC 2021 uses the same label as the existing CNBC_TARGET in targets.py (fetch_cnbc article path);
  I did NOT run fetch_cnbc — the whisper transcript supersedes the article fallback. No dup (no text/
  file for that label).
- Sohn AU 2021 Coinbase: primary URL 404s, no YouTube mirror. Built a labeled SECONDARY-COVERAGE
  web transcript (transcripts/web/, quality `secondary_coverage`) from Sohn H&M Foundation + AFR
  write-ups, with Baker's Coinbase Cloud / web3 thesis + reported quotes. NOT a verbatim transcript.

### Manifest fix (root cause logged)
Running `fetch_youtube <3 ids>` overwrote youtube/_manifest.json with only 3 entries (the 28 existing
.txt files were untouched). build_manifest then produced only 17. Fix: re-ran `fetch_youtube` with NO
args → full 31-entry step manifest → master manifest = **45** transcripts (39 + 6 new). Lesson: after a
targeted fetch, re-run the fetcher with no args before build_manifest.
master_manifest_v2.json reconciled to 49 (45 captured + 4 BIC placeholders carried forward).

## 2026-07-22 — Extraction/audit + curation gate

Extract: 6 ok / 39 skipped, ~$0.65 (55 new theses). Audit: 22 new theses audited (background job was
killed once at 218/562; idempotent re-run finished). Reaudit: 21 theses cleaned. Timeline 507 → **562**.
Audit correctly stripped the wrong `SPCE` tag from drawdown T1 ("SpaceX" is private ≠ Virgin Galactic).

### Gate decisions (operator, via AskUserQuestion)
- **D1 Heller House → REMOVE ALL 11** (SD-6NEW-1 resolved). 15 `cluster_override` null removals added to
  manual_overrides.json (44 → 59), one per (theme, thesis_id) the 2026-06-08 theses clustered into
  (SpaceX/Orbital/DRAM/Optical/Power/Intel/Google-TPU/xAI). Extractions kept on disk, out of scoring.
- **D2 Coinbase → NEW THEME** `Crypto / Coinbase (COIN)` LONG [COIN] added to theme_baskets_v3.json
  (keys: coinbase, web ?3, programmable crypto, crypto exchange); `COIN` added to UNIVERSE in
  theme_returns_v2.py. Keys match 4 theses: the 3 Sohn 2021 + 2022-03-25 T17 (a web3-infra thesis) —
  minor, defensible dual use; flagged.
- **D3 keys → 3 committed, blackwell/hopper DECLINED** (operator reviewed blast radius). Added:
  `lowest.?cost token` → Inference economics (+tariffs T7, +Google-TPU T3 dual); `electricity generation`
  → Power/watts (+tariffs T14); `structurally short (of )?compute` → Reasoning/inference-time compute
  (+drawdown T3). Declined blackwell/hopper (15/4-thesis blast, re-clusters many already-clustered theses).
  Consequence: tariffs T5/T6 (Grok/Hopper, Blackwell) stay unclustered (NO_BASKET) by choice.

### Applied-by-default ticker hygiene
Private names (Anthropic/OpenAI/xAI/SpaceX) left in tickers_direct — resolve NO_DATA harmlessly.
FOX/FDX/UPS/SMCI/TSM not added to UNIVERSE (no basket uses them post-Heller-removal). E125 Starship
theses (likely Gracias) remain but their SpaceX/Optical clustering is unchanged — flagged, not actioned.

### Deliverable versioning
build_repeat_mention_events.py OUTPUT bumped v6 → **v7** (step4_signal_events_v7_with_returns_extended.
{csv,xlsx}); v6 preserved for the changelog diff. theme_returns_v2.py still writes v5.csv (criterion grain).

## 2026-07-22 — Override regression + global date-anchoring (SD-6NEW-3)
Renumbering (from inserting earlier-dated SpaceX/Optical/etc. mentions) broke event-overrides keyed by
`(date, mention_number)`: stale mention numbers stopped matching → 9 SpaceX events silently reverted
baskets. Root cause: `mention_number` is a fragile derived key; `(theme,date)` is unique in the mention
grain. **Fix (operator-approved): global date-anchoring** — stripped `mention_number` from all 73 dated
event-overrides (0 used mention_number without a date → lossless). Immunizes the file against future
renumbering. Net vs interim SpaceX-only fix: 3 DRAM basket-label changes (MU → MU,000660.KS; activated
dormant overrides), 0 return changes (000660.KS is NO_DATA). v6→v7 final: +15 events, 0 removed, 0
return changes on pre-existing events. Full detail: analysis/v6_to_v7_changelog.md §3–4.
