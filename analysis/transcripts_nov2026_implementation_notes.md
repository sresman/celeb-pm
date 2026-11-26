# Transcripts Nov 2026 — implementation notes

Branch `transcripts-nov-2026` (cut from `main`). Task: add Baker appearances
since the v11 build (TBPN 2026-10-27), standard re-run sequence
(`analysis/PIPELINE_MAP.md`), stop at basket curation. No code, prompt,
attribution-method, basket or rule changes.

## 2026-11-20 — Setup

- v11 was uncommitted on `q3-2026-13f`, not on `main` as the task stated. None
  of the dirty files overlapped the Q3 commits, so the tree moved to `main` as it was.
  Committed unchanged as `ee84d1e` "v11 build, stopped before basket curation".
- `.env`: the modules load it themselves (python-dotenv, `override=True`).
  Shell-sourcing `.env` fails on an unquoted value on line 6; not needed.

## 2026-11-20 — Discovery (operator-approved)

Added (3 fetched + 1 comment-only):

| date | label | source | transcript |
|---|---|---|---|
| 2026-11-17 | `cnbc_squawk_nvidia_letter_2026nov` | CNBC Squawk on the Street (Sara Eisen), live from TomorrowX | yt-dlp audio + whisper medium |
| 2026-11-17 | `tomorrowx_opening_session_2026nov` (`OmEfHDQ3B6c`) | TomorrowX opening session; Eisen moderates Baker, Gracias, Biscardi | YouTube auto-captions |
| 2026-11-19 | `sourcery_nvidia_jensen_tomorrowx_2026nov` (`drpASO63CJc`) | Sourcery (Molly O'Shea), recorded at TomorrowX | YouTube auto-captions |
| 2026-10-29 | — | Boston Investment Conference, with Ted Seides | NO RECORDING — comment in `targets.py` + line in `corpus_audit.md` |

Excluded: White House / America.gov 2026-09-29 (Baker moderated; Heller House
rule, operator decision); every TomorrowX session where Baker interviews
someone else (Musk, Dell, Solomon, Johnsen, Feldman, Xu, Mohan, Lochmiller,
Qiao, Micron); Sourcery compilation `cTFNOTt-jGs` (duplicate segment); Chinese
/ Spanish re-uploads; clip channels; Aleph 2026-08-12 compilation; G&D Spring
2026 (DeSpirito interview).

**Decision (ambiguous spec):** there is no "private-event placeholder" convention
in the repo, so Boston is recorded as a dated comment, not a registry entry.
Operator approved.

**Decision:** Sourcery is dated to its 2026-11-19 publication. It was recorded at
TomorrowX on 11-17 or 11-18; publication is when it became public
(filing-date-anchor logic).

## 2026-11-20 — Whisper

The existing install is in this project's venv (`.venv/bin/whisper`,
openai-whisper 20250625). It was missed by `which -a` because the venv isn't
on PATH. Model cache `~/.cache/whisper/medium.pt` (July 2026). Used medium, matching
`cnbc_squawk_spacex_debut_2026jun`. Nothing installed. The CNBC transcript
follows the June file's header format; its manifest row is appended to
`transcripts/whisper/_manifest_cnbc.json` and its metadata added to
`SUPPLEMENTARY_METADATA`. This is the same hand route as the two earlier 2026
CNBC files, which no fetcher covers.

## 2026-11-20 — Pipeline gotchas hit

1. **`fetch_youtube <ids>` overwrites `transcripts/youtube/_manifest.json`
   with only the passed IDs** (36 → 2 rows). `build_manifest` would then have
   dropped 34 YouTube appearances from the master manifest. Fixed by re-running
   `fetch_youtube` with no args (all skipped_exists, 38 rows). The minimal
   re-run in `PIPELINE_MAP.md` shows the ID form; it should say no-args.
   NOT changed (doc/code fix out of scope) — flag.
2. **`reaudit_tickers` has no scope filter.** None of the 25 new theses met
   its A/B/C criteria. Instead it re-audited 6 EXISTING theses for the first
   time: All-In 2025-08-09 T3; a16z 2026-08-31 T1, T5 and T14; TBPN 2026-10-27
   T7 and T9. Earlier builds skipped this step for them. It changed tickers
   on two:
   All-In T3 `META, MSFT, GOOGL, AMZN` → `META, MSFT`; a16z T1 `NVDA, META` → `[]`.
   It also wrote attribution overlay fields into 21 unrelated audit files.
   **Reverted** (the task is new appearances only, and v11's
   inputs must not move). The 23 audit files and `_reaudit_log.json` went back to HEAD, the 6
   new re-audit files moved to the session scratchpad (`deferred_reaudits/`),
   and the timeline was rebuilt. Verified: all 648 existing theses are identical to HEAD
   in both v2 timelines. **Open question for the operator:** apply those 6
   re-audits in the next build (they are what the standard sequence would do)?

## 2026-11-20 — Counts

- Manifest 51 → 54 (none lost). Extraction (prompt unchanged): CNBC 8,
  TomorrowX opening 8, Sourcery 9 → timeline 648 → 673. Cost: extraction $0.22,
  audit $0.21, re-audit $0.05 (reverted), attribution 4 × $0.11.
- Attribution, original instrument, two passes into `attribution_audit_pass{1,2}_v2/`
  with `--all --dates 2026-11-17 2026-11-19`: **25/25 subject, 100% agreement.**
  Existing pass files md5-verified unchanged; 0 existing verdicts changed.
  Resolved: 528 subject / 45 other / 100 indeterminate (theses); 628/44/94
  named tickers (766).
- Cue instrument (`attribution_audit_cue_pass{1,2}/` →
  `attribution_resolved_cue.json`, feeds nothing): agrees on all 25.
- Stopped before basket curation. `theme_baskets_v3.json` and
  `manual_overrides.json` untouched; no returns run.

## 2026-11-20 — Re-audit applied (operator-approved), curation proposal (pending)

- Re-ran `reaudit_tickers` (no args) + `audit_theses --rebuild-only`: 6 ok, 17 skipped,
  ~$0.05. Timeline changes on 2 existing theses, `tickers_direct` only:
  All-In 2025-08-09 T3 `META, MSFT, GOOGL, AMZN` → `META, MSFT`;
  a16z 2026-08-31 T1 `NVDA, META` → `NVDA` (the earlier note said `[]`; that was
  wrong). The 21 other audit files gain only attribution overlay fields that
  match the timeline. Correction: `tickers_subject` did not change on either.
- v11 effect: one mention event, "AI capex ROI positive" 2025-08-09 (mention 3),
  `tickers_direct` display column only. Baskets resolve from the theme, not the
  thesis, so no basket, return or criterion changes. a16z T1 is in no theme.
- Convention finding: `cluster_overrides` need a `from_theme`, so they cannot pick
  up an unclustered thesis. For a thesis that matched no theme, the convention is
  a keyword addition in `theme_baskets_v3.json` (the v11 precedent:
  'anthropic s1', 'grok 4.7').
- The proposal (keys, two new themes, TSMC→TSM in the opening-session T3 audit
  file) was simulated read-only: all 25 placed, 0 existing theses gained or lost.
  Only mention 2: ALAB / copper vs fiber (Sourcery T9; basket ALAB). Awaiting approval.

## 2026-11-20 — Curation applied, v12 built (operator-approved)

- Re-audit committed as `e9363c7`.
- `theme_baskets_v3.json`: the keyword additions as proposed (7 themes), plus a new
  theme "Enterprise on-prem AI factories" (DELL, BAKER_NAMED, LONG). The retail
  theme was NOT created (operator decision), so Opening T8 stays unthemed.
- TSMC → TSM fixed by hand in
  `thesis_audits/2026-11-17_tomorrowx_opening_session_2026nov_T3.json`
  (ticker lists + ticker_audit, with a note), then `--rebuild-only`.
- v12: output constant bumped v11→v12 in `build_repeat_mention_events.py`,
  following the v10→v11 precedent. `theme_returns_v2 --force-refetch` and
  `build_repeat_mention_events --force-refetch`; prices through 2026-11-19 (CRSO and
  000660.KS NO_DATA as always). 234 mention rows (v11 218), 177 repeat, 80
  meet criteria. Rows before 2026-10-27 differ from v11 only in
  `total_theme_mentions` and the All-In 2025-08-09 `tickers_direct` display.
- Correction to the proposal: Broad AI bullish is NO_BASKET for every mention
  because of the existing theme-level event override (operator 2026-07-16, "never-a-trade").
  The proposal's "SMH" was wrong. Opening T1/T5/T6 and Sourcery T1 therefore carry no basket.
- All new rows: returns INSUFFICIENT_DATA (prices end 2026-11-19; 1m needs ~2026-12-17).

## 2026-11-25 — Nov round 2: Monetary Matters (operator-approved), stopped at curation

- Branch `transcripts-nov-2026` (not merged, so continued on it).
- Discovery: fomo `state/` diffed against the 2026-11-19 snapshot (44 new YouTube
  IDs, 0 RSS, 5 digest-queue items), plus YouTube date search and web search.
  One new first-party appearance: Monetary Matters with Jack Farley
  `2XhpxKX3d0M`, published 2026-11-23 (recorded 2026-11-18 at TomorrowX), 941s,
  `en-orig` captions. Podcast episode (929s) is the same conversation.
  Excluded: Baker-moderated iConnections uploads (Musk, Feldman, Xu, Jensen
  montage), clips/Shorts, Korean/Chinese re-uploads, commentary, Aschenbrenner
  noise, one private video.
- **Decision:** dated 2026-11-23 (publication), the Sourcery precedent.
- `fetch_youtube 2XhpxKX3d0M` then no-args: YouTube manifest 38 → 39 rows, none
  lost. Master manifest 54 → 55.
- Extraction 9 theses (673 → 682), ~$0.08. Audit ~$0.10. `reaudit_tickers`
  touched only the new T7 (1 ok, 21 skipped), ~$0.01; no existing audit file changed.
- Attribution, original instrument, `--all --dates 2026-11-23` into
  `attribution_audit_pass{1,2}_v2/`; reconciled to `attribution_resolved.json`.
  Two passes byte-identical. 8 subject / 1 other (T7). Cue instrument
  (`attribution_audit_cue_pass{1,2}/` → `attribution_resolved_cue.json`, feeds
  nothing): agrees on T1–T8, T9 indeterminate (cue: none). Existing pass files
  md5-unchanged; 0 existing resolved verdicts changed; all 673 existing timeline
  entries identical to before. ~$0.12.
- **FLAG (not changed): T7 looks like a false `other`.** The captions drop the
  `>>` marker between Farley's ASIC question ([10:19]) and Baker's answer
  ([10:37] "He was the one pushing Nvidia ... a godsend for all of Nvidia's
  competitors"), so the quote sits inside the host's turn. No precedent for a
  hand attribution correction; method unchanged per task. Impact if it were
  subject: it would join Nvidia GPU moat on the same date as T1, so no row change.
- Curation proposal simulated read-only (scratchpad `sim_curation.py`):
  0 existing theses gain or lose a theme. Awaiting approval.
