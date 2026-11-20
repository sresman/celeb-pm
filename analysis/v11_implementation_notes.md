# v11 implementation notes — TBPN 2026-10-27, All-In 2025-08-09, June TBPN re-audit

Append-only. Operator-approved scope (2026-10-28): add `crdg4X5BZPc` (TBPN Baker
segment) and `NpJ4RYSdVK4` (All-In 2025-08-09), fix the June TBPN host and
re-audit that episode, regenerate v11. Stop before basket curation.

## 2026-10-28 — Source selection

- **TBPN 2026-10-27: four alerts, one appearance.** Full show `OV1QfQ3C29Q`
  (RSS `5981bd4c…`, 2:10:58) and Baker segment `crdg4X5BZPc` (RSS `5f02cbc6…`,
  41:27). A fifth copy, `xwf7CyOa9r8`, is the full show re-uploaded to John
  Coogan's personal channel. Segment chosen: the full show's Baker chapter is
  1:21:12–2:02:40 = 2,488s vs the segment's 2,487s, and ~2/3 of the full show is
  unrelated guests (Rebuild Manufacturing, Ramp). Caption check after fetch:
  77.3% of segment 5-grams occur in the full show's Baker chapter, 0.4% anywhere
  else in the show. The shortfall from 100% is independent ASR per upload, not
  missing content. Confirmed contained.
- **Gap sweep 2026-09-01 → 2026-10-28.** All 10 Baker-keyword RSS feeds current
  (latest items 15–28 Oct); only Baker hits are the two TBPN items. Two
  non-allowlisted items (Huang/Musk America.gov panel 2026-09-29, GTC Berlin
  pregame 2026-10-24) left out by operator: moderator/co-host formats.
- **Aria `0ZHX7J6vXT4` is a SEPARATE session, not a re-cut.** The corpus clip
  `MmNWwIYFBeI` ends with Karam: "we're going to bring you back on stage to wrap
  up at the end". `0ZHX7J6vXT4` is described as Baker and Karam "close the event
  with a conversation"; its chapters do not overlap the corpus clip's. Text
  overlap could not be measured (HTTP 429 on captions). NOT added — reported to
  the operator for a decision.

## 2026-10-28 — Metadata

- **June TBPN host was wrong.** `"Foxy (Gavin Baker guest)"` → `"John Coogan,
  Jordi Hays (Gavin Baker guest; Atreides analyst Andrew 'Foxy' Fox in room)"`.
  At 01:58 Baker says "this is Foxy in the back… one of the analysts here at
  Atreides". Foxy is a co-speaker the audit must consider, not a host.
- **October TBPN `subject_role: guest`.** One guest, two hosts; no third voice in
  the Baker chapter ("Jordy" named on-air; Gerstner only mentioned).

## 2026-10-28 — fetch_youtube: HTTP 429 was recorded as `no_captions`

`_download_caption` returned None on any missing file, so a YouTube throttle on a
video that HAS captions was written to the manifest as `no_captions` — a
permanent-sounding status for a transient condition. Added a `rate_limited`
branch mirroring the existing `bot_wall` one. No behavior change otherwise.

## 2026-10-28 — June TBPN re-audit

Two passes, `--dates 2026-06-15 --force` into the `_v2` pass dirs (pre-fix copies
kept in the session scratchpad). Resolved verdicts 0 subject / 2 other / 11
indeterminate → 9 subject / 2 other / 2 indeterminate (T5 split → indeterminate).
**Caveat:** several new `subject` calls cite register ("consistent with a fund
CIO's quantitative framing") rather than a handoff cue. Both passes agree, but
two-of-two cannot catch a cue both passes share. Foxy is an Atreides analyst
with the same register, so a Foxy turn could read as Baker.

## 2026-10-28 — Audit of `no_captions` records (operator follow-up 1)

**Zero episodes lost to the 429 misreport.** Checked every step manifest on disk
and every committed version of `youtube/_manifest.json` and
`text/_manifest_cnbc.json` in git history. No YouTube record was ever committed
as `no_captions` / `empty_captions`. The only `no_text (video has no captions)`
record is `cnbc_sharpe_angle_spacs_2021aug`, from `fetch_cnbc` (cnbc.com HLS,
genuinely captionless) — it is in the corpus via `whisper_small`. The three
YouTube IDs ever removed from `targets.py` (`_Tua32QoR6w`, `jOgbqt04eUk`,
`yosv2UDCm9M`) were all removed for content reasons (not a Baker appearance /
Baker as interviewer), never for captions. Limitation: the YouTube step manifest
is rewritten every run, so an uncommitted transient `no_captions` would leave no
trace — but every target that exists today has a transcript on disk except the
one now correctly marked `rate_limited`.

## 2026-10-28 — June TBPN 0 → 9: what grounds the nine (operator follow-up 2)

The transcript names "Gavin" exactly once (00:00, the welcome) and addresses
"Foxy" once (03:07, "Foxy? Do you remember for which deal?", which he answers).
There is NO naming cue anywhere in the remaining ~30 minutes. So no verdict in
this episode can rest on naming, before or after the fix.

| thesis | tickers | P1 | P2 | resolved | grounding |
|---|---|---|---|---|---|
| T1 | — | other | other | other | host pushback (agreed) |
| T2 | NVDA | indet | indet | indet | no cue (agreed) |
| T3 | — | baker | baker | subject | register only ("I am increasingly looking at EV/net PP&E") |
| T4 | META | baker | baker | subject | continuity from T3's turn, no `>>` between |
| T5 | CRWV | baker | indet | **indet** | split — reconciliation decided |
| T6 | NET FSLY AKAM | baker | baker | subject | register only ("my gut is", bps estimate) |
| T7 | — | other | other | other | host-style tangent (agreed) |
| T8 | SpaceX | baker | baker | subject | register only (first-person orbital math) |
| T9 | — | baker | baker | subject | register only (sustained first person) |
| T10 | — | baker | baker | subject | P1 continuity; P2 register + interviewer affirmation at T161 |
| T11 | — | baker | baker | subject | **structural**: reply to host setup at turn 94; P2 adds "we track" |
| T12 | — | baker | baker | subject | continuity from the T11 answer chain |
| T13 | — | baker | baker | subject | register only ("Look, I think a few things") |

Of the nine: 0 naming, 1 structural reply-to-host (T11), 3 continuity from an
adjacent Baker-judged turn (T4, T12, T10-P1), 5 register alone. All nine agreed
two-of-two; the reconciliation decided only T5. Five named-ticker slots enter
`subject` (META, NET, FSLY, AKAM, SpaceX).

**The cues did not change — the threshold did.** Old evidence on the same turns
read "no direct address or self-identification cue … to distinguish Baker from
another participant" → indeterminate. New evidence on the same turns reads the
same register as sufficient → baker. The only input that differed was the
participants line. Even T11's structural cue (answers a host) does not separate
Baker from Foxy, who also answers when asked.

**Roster metadata is load-bearing for attribution corpus-wide, not bookkeeping.**
A host-field correction moved one episode 0 → 9 subject on identical transcript
cues. Two-of-two does not guard against this: both passes see the same roster,
so a roster-induced shift is agreed-upon by construction. Every episode whose
host field is first-name-only, caption-garbled ("Jas", "Guy", "Ron") or
`unknown` should be presumed to carry roster-driven attribution error of
unknown sign. No change made — recorded for the operator.

## 2026-10-28 — Operator decision: June TBPN runs as resolved (nine subject)

Not held out. (a) Style-only verdicts run throughout the existing subject set;
carving out one episode would apply a stricter standard to it than to the other
47 and break v10/v11 comparability. (b) Single-guest interview: sustained
first-person investment reasoning belongs to the fund manager, not the two
hosts. **Both facts stand: the correction was right, and the evidence behind it
is weak.**

## 2026-10-28 — New audit field `cue_type` (operator)

`audit_attribution` now emits `cue_type` ∈ {naming, structural, continuity,
style, none} per verdict (schema-required, prompt appended — the verdict
instructions above it are byte-identical). `reconcile_attribution` carries each
pass's cue and resolves to the WEAKER of the two when the verdicts agree; a
disagreement-forced indeterminate gets `none`; any file audited before the field
existed gets `not_recorded` (kept distinct from `none` so the backfill can find
them). Summary adds `subject_by_cue`. `audit_theses` overlays it into the
timeline as `attribution_cue_type`. Applied to the new episodes in this run only;
no corpus backfill (next piece of work). Reconcile regression check: rebuilt
from the `_v2` dirs into the scratchpad, identical to the live resolved file
except the 9 June TBPN rows changed by the re-audit.

**Validation — the prompt addition shifts verdicts; the shift is direction-neutral
on the sample.** Re-ran the new prompt (scratch out-dir, nothing wired) on 5
panel episodes / 77 theses (All-In E125, iConnections 2024, BG2 2026-06, All-In
2026-08, a16z 2026-08). New-vs-old single-pass agreement 80.5% / 81.8%, against
93.5% old pass1-vs-pass2 on the same theses. Against the old resolved verdicts:
subject 36 → 37, indeterminate 22 → 21, other 19 → 19 — 5 baker→indeterminate
(all `none`, model now says "no naming cue"), 6 indeterminate→baker (4
`continuity`, 2 `naming`). Reads as the cue question changing what the model
attends to — stricter on some turns, more willing to chain continuity on others
— rather than a bias. 77 theses is too few to rule out a small directional
effect. **Consequence for v11:** the new episodes are audited with a slightly
different instrument from the other 48; both of their passes use the same one,
so two-of-two is internally consistent. Cost $0.26. Cue mix on that sample:
baker = 16 naming / 3 structural / 9 continuity / 8 style / 1 none.

## 2026-10-28 — Operator decision: v11 stays on one instrument

The cue-field audit does NOT produce v11 verdicts. `audit_attribution` now holds
two instruments: the default (`SYSTEM_PROMPT` + `AUDIT_SCHEMA`, verified
byte-identical to HEAD) and `--cue-type` (`SYSTEM_PROMPT_CUE` +
`AUDIT_SCHEMA_CUE`, default out dir `analysis/attribution_audit_cue/`). For the
new/re-audited episodes the original instrument's two passes go into
`attribution_resolved.json` → timeline → returns; the cue instrument's two passes
go to `analysis/attribution_audit_cue_pass{1,2}/` → `analysis/attribution_resolved_cue.json`,
which nothing reads. June TBPN was already re-audited on the original instrument
(before the field existed), so it is on the right side. v11's delta vs v10 is
therefore attributable to content only.

**v12** (next handoff): roster cleanup FIRST, then re-audit the full corpus on the
cue instrument against the corrected metadata, reporting the shift vs stored
verdicts at thesis and named-ticker level.

### STANDING RULE (extends the extraction-prompt rule to the auditor)

> The attribution audit prompt is a measuring instrument. Any change to it —
> including one that only appears to add an output field — changes the verdicts,
> not just their labels. No change to it ships without a before-and-after
> measured on enough episodes to see the shift, and no run mixes two versions of
> it in the numbers that feed the returns.

Both the extractor (one sentence: 21 theses → 1) and the auditor (one output
field: ~19% verdict churn vs 6.5% baseline) have now produced a case where a
change that looked like bookkeeping moved the data.

## 2026-10-28 — TBPN Oct attribution, and a gap in the cue categories

Original instrument, two passes: 14 subject / 0 other / 1 indeterminate (T10,
quote not located), 100% agreement. Cue instrument agrees on every verdict.
**Category gap for v12:** self-identification ("my firm is an investor in them",
"at Atreides we co-led Crusoe" — captioned "Trafigura") has no category. The
cue instrument filed it as `naming` once (T4) and `style` twice (T11, T13),
though it is the audit prompt's own second-strongest cue. Add a
`self_identification` value (or fold it into `naming` explicitly) before the
v12 corpus re-audit, or `style` will be overstated.

## 2026-10-28 — All-In 2025-08-09: two silent data defects caught before extraction

1. **Translated caption track.** First successful fetch wrote word salad ("I To
   Freiburg One thing I have to say. I More Have power…"): the video's `en` track
   is a machine translation from a mis-detected source language; `en-orig` holds
   the real English ASR. `fetch_youtube.SUB_LANG_CANDIDATES` now tries `en-orig`
   first (it is the original ASR whenever present, so never worse than `en`).
   Garbled file kept in the session scratchpad. Corpus scan of all 36 YouTube
   transcripts (mid-sentence capitalised words per 1k: garbled file 330, every
   corpus file ≤ 46): no other transcript affected.
2. **Roster.** Provisional entry listed the four besties; the transcript intro
   says Chamath and Sacks bailed 90 minutes before recording — Jason moderates a
   "fivesome": Friedberg, Baker, Ben Shapiro, Phil Deutsch (NGP ETP). Corrected
   before extraction (extraction also reads `host`). Chapter list misspells
   Deutsch as "Deutch".

NOTICED, NOT TOUCHED: `subject_role` has never reached `_master_manifest.json`
(None on all 51 rows, HEAD included) — `fetch_youtube.fetch_one` does not put it
in the row. Harmless today (`audit_attribution.metadata_by_label` reads targets
first) but the manifest field is dead.

## 2026-10-28 — Pipeline counts

Manifest 48 → 51 (NEW: All-In 2025-08-09, Aria wrap-up, TBPN Oct; LOST: none).
Extraction (prompt unchanged, low-yield guard did not fire): TBPN 15 (floor 4),
All-In 12 (floor 8), Aria 7 (floor 3). Flat timeline 614 → 648, attribution
overlay 648/648 matched. Original-instrument resolved: 503 subject / 45 other /
100 indet (theses); 608 / 44 / 94 (746 named tickers); agreement 96.5%. Aria
wrap-up audited via `--only` so the same-date existing Aria clip was NOT
re-audited (its pass file md5-verified unchanged).

| episode | theses subj/oth/ind | named tickers subj/oth/ind |
|---|---|---|
| TBPN 2026-10-27 | 14 / 0 / 1 | 18 / 0 / 0 |
| All-In 2025-08-09 | 9 / 2 / 1 | 7 / 8 / 1 (8 energy names → Phil Deutsch) |
| Aria wrap-up 2026-04-16 | 4 / 1 / 2 | 5 / 0 / 2 |
| June TBPN (re-audit) | 9 / 2 / 2 (was 0 / 2 / 11) | 5 / 0 / 2 (was 0 / 0 / 7) |

Cue instrument (`attribution_resolved_cue.json`, feeds nothing) agrees with the
original on all 34 new theses; subject cues: naming 7, structural 5,
continuity 10, style 5.

Returns: `theme_returns_v2 --force-refetch` (78 tickers, through 2026-10-27;
CRSO + 000660.KS NO_DATA as always) → 143 events (v10 139). Then
`build_repeat_mention_events` on the warm cache → 218 mention rows / 162 repeat
(v10 205 / 151) → `analysis/step4_signal_events_v11_with_returns_extended.{csv,xlsx}`.
v10 untouched.

## 2026-10-28 — v10 → v11 delta by component

Method: 16 counterfactual builds (every subset of the four components) on the
same warm cache, paths redirected to the scratchpad. Checks: the all-components
build is byte-identical to live v11; the no-components build reproduces v10's
rows and triggers exactly, so base − v10 is the price refresh alone.

| | signal n | sig 9m | sig 1y | sig excess 1y | control n | ctl 9m | ctl 1y | ctl win 1y |
|---|---|---|---|---|---|---|---|---|
| v10 | 38 | 100.14 | 228.53 | 167.95 | 112 | 23.38 | 29.68 | 47.1 |
| price refresh only | 38 | 100.14 | **215.24** | **155.01** | 112 | 23.38 | 31.37 | 54.5 |
| + All-In 2025-08-09 | 38 | — | — | — | +2 | **26.81** | **37.66** | 56.5 |
| + TBPN Oct | — | — | — | — | +2 | — | — | — |
| + June re-audit | **39** | — | — | — | +3 | — | — | — |
| + Aria wrap-up | — | — | — | — | +2 | — | — | — |
| interaction (June × TBPN) | — | | | | +1 | | | |
| v11 | 39 | 100.14 | 215.24 | 155.01 | 122 | 26.81 | 37.66 | 56.5 |

(each component row is its marginal effect added to the price-refresh base; "—" = no change)

- **Price refresh** (prices 2026-09-14 → 10-27) moves EVERY headline return
  change on the signal slice: 6 cells newly crossed 1y, 15 crossed 1q, 6 crossed
  1m; 2 previously computed cells revised. Signal 1y 228.53 → 215.24.
- **All-In** is the only content component that moves returns: its 2025-08-09
  `China AI distillation` m4 row (control; semicap basket, 1y +175.96) lifts the
  control slice 1y 31.37 → 37.66 and 9m 23.38 → 26.81. It also moves a trigger
  EARLIER: `AI capex ROI positive` third-within-1yr now fires 2025-08-09 (was
  2025-10-30, which drops to m4/control) — NO_BASKET both, so no return impact.
- **June re-audit** adds the only new signal row: `Datacenter physical assets`
  2026-06-15 m2 first_hc_not_first_mention (EQIX, DLR; 1q −3.66, 9m/1y not yet
  computable), plus `CDN / token delivery path` m1 first_with_tickers (not a
  repeat), and shifts Orbital/SpaceX mention numbers by one.
- **TBPN Oct** adds 3 rows (Neoclouds m6, SpaceX m15, Sovereign AI m2), none
  firing, none with returns yet. Sovereign AI m2 exists only jointly with the
  June re-audit (TBPN alone makes it m1).
- **Aria wrap-up** adds 2 non-firing rows (AI networking m3, Neoclouds m2) and
  renumbers the later Neoclouds rows; the 2026-05-12 hc_high_profile_venue
  trigger survives as m3.

**Clustering gap (for basket curation, not acted on):** 11 of TBPN's 14 subject
theses and 7 of All-In's 9 match no theme regex — incl. GPU-compute contango,
in-the-money compute contracts, Anthropic S-1, DGX Pod, Apple AI strategy.
