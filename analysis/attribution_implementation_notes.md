# Attribution audit — implementation notes

Append-only. One section per working session, newest last.

---

## 2026-09-08 — audit passes, reconciliation, timeline wiring

Continues the 2026-09-08 attribution session (SD-ATTR-1…9). Picking up at steps
1–3 of the handoff's ordered list.

### SD-ATTR-10 — stale pre-restore audit parked, not deleted

`analysis/_attribution_audit_precorpus_restore/` (46 files) + its log moved to
`analysis/_stale/` with a README stating why they cannot be trusted. Kept rather
than deleted: they are the record of the original 73/11/16 measurement, and the
corpus they were computed against is recoverable from git if the numbers ever
need re-deriving.

### SD-ATTR-11 — the attribution audit was keyed on date; changed to label

**Found before spending on pass 1.** `audit_attribution` selected episodes with
`select_dates()`, resolved transcripts with `transcript_by_date()`, and wrote
`OUT_DIR/{date}.json`. Both functions carried docstrings warning that date is not
unique, and an unused `transcript_by_label()` sat beside them — the label-keyed
path had been written but never wired in.

Concretely: 2026-05-12 holds two appearances of the one Sohn NY event —
`sohn_ny_2026_khaira_writeup` (4 theses, HedgeFundAlpha write-up) and
`sohn_ny_2026_tech_investor` (8 theses, YouTube fireside). Their thesis_ids
collide on T1..T4. A date-keyed pass bundled all 12 theses into a single API call
against whichever transcript the date map happened to retain, so up to 8 quotes
could not be located (→ forced `indeterminate`), and the single output file could
not be joined back to an appearance at all. `(date, thesis_id)` is unique
everywhere in the 614-thesis corpus **except** those four rows.

Changed:
- new `label_by_date_source()` — reconstructs `(date, "{source} — {topic}")` →
  label from the extraction files, because the flat timeline carries no label.
  Verified 47/47 against the current timeline; every label resolves in the master
  manifest.
- `select_dates()` → `select_episodes()`, grouping the timeline on
  `(date, source)` (47 groups) and returning label-keyed tuples.
- transcript lookup via `transcript_by_label()`; output file `{label}.json`;
  `label` added to the episode record and the per-episode summary rows.
- dead `host_by_date()` / `transcript_by_date()` / `select_dates()` removed —
  orphaned by this change, not pre-existing cleanup.
- `--dates` still filters on date, and now selects *both* appearances that share
  one.

Dry run after the change: 47 episodes, 614 theses, both 2026-05-12 appearances
separate and each fully located (4/4 and 8/8).

**Open, pre-existing, not fixed:** `cnbc_sharpe_angle_spacs_2021aug` has 6/6
quotes unlocated, so all 6 theses force to `indeterminate`. Confirmed
pre-existing — the parked pre-restore audit shows the same 6/6. It is a Whisper
transcript; the quote fragments do not survive the transcription. Conservative
failure (nothing is attributed to Baker that shouldn't be), so left alone.

### SD-ATTR-12 — reconciliation is a separate tool, and it renames the verdict

New `tools/transcripts/reconcile_attribution.py`. Reads two pass directories,
keys on `(label, thesis_id)`, applies the operator's two-of-two rule
(disagreement → `indeterminate`), writes `analysis/attribution_resolved.json`.

Two decisions inside it:
- **Vocabulary is translated once, here.** `audit_attribution` emits `baker`;
  everything downstream speaks `subject`/`other`/`indeterminate` (the
  investor-agnostic vocabulary `audit_theses` and the filtering layer expect, and
  the one CLAUDE.md's investor-agnostic rule asks for). The map lives in
  `VERDICT_MAP`.
- **`speaker_name` survives only on full agreement.** It is kept only when both
  passes say `other` *and* name the same person; otherwise it is blanked. A name
  that the two passes disagree about is noise, and a wrong name is worse than no
  name for the operator's later review.

A thesis present in only one pass resolves to `indeterminate` with a
`missing_in_passN` note rather than being dropped, so the resolved file always
covers the full corpus.

The report prints the resolved split *and* what pass 1 alone would have said, so
the cost of the two-of-two rule is visible as a line item rather than inferred.

### SD-ATTR-13 — attribution is overlaid at timeline rebuild, not baked into audits

`audit_theses.rebuild_timelines()` reassembles the timeline from the 614
per-thesis files in `analysis/thesis_audits/`, **not** from `_build_v2_entry()`.
Those on-disk files predate the attribution work and carry no speaker field, so
the fields added to `_build_v2_entry` last session would only have appeared for
theses re-audited after the change — i.e. none of them. That is why the current
`thesis_timeline_v2_flat.json` has no `speaker_attribution` key at all.

Fixed by overlaying at rebuild time: `rebuild_timelines()` now loads
`attribution_resolved.json` and merges the three attribution fields into each
entry as it is read. `_build_v2_entry` writes honest placeholders
(`indeterminate`/`""`) instead of reading from the extraction, which no longer
emits them.

Consequence, deliberate: re-running the attribution audit never requires
re-running the thesis audit (the expensive one, ~$2.29), and the per-thesis audit
files stay untouched.

Also added `appearance_label` to every timeline entry, recovered from the audit
filename (`{date}_{label}_{thesis_id}`). The timeline previously had no label
field, which is what forced the extraction-file join in `label_by_date_source()`;
the filtering layer and the aggregate comparison both need it.

### Also fixed (mypy gate was red on this workstream)

- `targets.py`: `subject_role` was written into all 50 entries by
  `fix_participants --apply` but never added to the four target TypedDicts — 51
  `typeddict-unknown-key` errors. Added as `NotRequired[str]` to
  `YoutubeTarget` / `ScrapeTarget` / `SearchTarget` / `RssTarget`.
- `fix_participants.py:137`: `.text` on an unnarrowed SDK content block — 11
  `union-attr` errors. Switched to `getattr(b, "text", "")`, matching the
  `getattr(b, "type", "")` idiom already on the same line.

`mypy tools/transcripts --explicit-package-bases` → clean, 33 files.

**Note on invoking mypy:** bare `python -m mypy .` fails outright with
`Source file found twice under different module names` on `targets.py`. Use
`.venv/bin/python -m mypy tools/transcripts --explicit-package-bases`.

### Open questions for the operator

1. The two Sohn write-ups (`sohn_ny_2026_khaira_writeup`,
   `sohn_montreal_2025_skhynix_writeup`) are `subject_role: secondary` — Baker
   spoke, but the text is a third party's rendering, so every quote is
   paraphrase. The audit will read them as Baker's words because they are
   presented as such. Carried forward from the previous session's known issues;
   still unresolved.
2. 19 transcripts have no `>>` speaker markers at all (`turns=1`), so attribution
   on those rests entirely on self-identification and register. Expect a high
   `indeterminate` share there; worth checking whether it concentrates in
   episodes that matter.

### Pass 1 results (2026-09-08)

`audit_attribution --all --force` over the restored 614-thesis corpus. 47
episodes, 614 theses, 705 named-ticker slots — an exact match to the corpus, so
nothing was dropped or double-counted by the label-keyed rewrite.

| grain | subject | other | indeterminate |
| --- | ---: | ---: | ---: |
| theses (614) | 422 (69%) | 71 (12%) | 121 (20%) |
| named tickers (705) | 502 (71%) | 80 (11%) | 123 (17%) |

Close to the pre-restore measurement (73/11/16 on tickers), which is the expected
result and a decent check on both runs. Cost $2.25 for 531K in / 44K out —
higher than the $1.32 quoted in the handoff because that figure came from a
narrower selection; `--all` over 47 episodes is the honest number, so budget
~$4.50 for the two-pass protocol.

**The `other` verdicts name real participants.** Antonio Gracias (11), Jason
Calacanis (11), Patrick O'Shaughnessy (10), Brad Gerstner (5), David George (4)
— each on episodes those people are actually on. The audit is not inventing
names to justify a verdict. The confirmed AMZN/Calacanis case reproduces.

Worst episodes by named-ticker contamination: All-In liquidity/secondaries
2026-06-07 (100%), TBPN 2026-06-15 (100%), a16z AI-bubble 2025-10-30 (92%),
iConnections 2026-02-24 (83%).

**Flag — cold-open false positives, 5 of 71 `other` verdicts (8 named
tickers).** Five verdicts rest on the quote landing in turn 0 and the model
reading turn 0 as a host intro. Some are genuinely the host ("So, Gavin, were you
at the Coldplay concert" is plainly a question *to* Baker). But podcasts also
cold-open with a replayed clip of the *guest*, and `bg2_spacex_ipo_2026jun` T1
and `iltb_gpus_tpus_ai_economics_2025dec_yt` T8 look like exactly that. The
two-of-two rule will not catch these — both passes see the same cue and can make
the same mistake. ~1% of named tickers, and the error direction is conservative
(a Baker claim excluded, never a co-host claim included), so flagged for the
operator rather than fixed.

### SD-ATTR-14 — the audit had no request timeout; pass 2 hung for 55 minutes

Pass 2 stopped writing after 41 of 47 episodes and sat with the process alive and
zero output for 55 minutes. Cause: `anthropic.Anthropic(...)` was constructed
with `max_retries=3` but no `timeout`, and the per-episode call wraps a bare
`except Exception` around a second attempt — so a stalled request can burn the
SDK default timeout three times, then do it all again.

Added `API_TIMEOUT_SECONDS = 180.0` (constant at module top, per the
no-hardcoded-values rule) and passed it to the client. 180s is well clear of the
slowest observed episode (a16z 2026-08-31, 543 turns, ~40s).

Recovered without re-spending on the 41 completed episodes by re-running
**without** `--force`, which the module's idempotency rule (settled decision 6)
turns into `skipped_exists` — and those skipped records are still loaded into the
summary, so the aggregate and the log come out complete. Cost of the incident:
one stopped process, no re-billed episodes.

Console logs are also now captured with `python -u`; stdout redirected to a file
is block-buffered, so the earlier run's progress was invisible until exit, which
is why the hang took a while to spot.

### Pass 2 + reconciliation (2026-09-08)

Pass 2: 69% baker / 10% other / 21% indeterminate on theses; 73/10/18 on named
tickers. Close to pass 1 (69/12/20; 71/11/17).

**Two-of-two agreement: 95.0% — 583 agreed, 31 disagreed.** Resolved corpus:

| grain | subject | other | indeterminate |
| --- | ---: | ---: | ---: |
| theses (614) | 416 (68%) | 56 (9%) | 142 (23%) |
| named tickers (705) | 492 (70%) | 56 (8%) | 157 (22%) |

Cost of the rule vs pass 1 alone: −6 subject theses, −10 subject named tickers.

The disagreement is **not** where it would hurt most. `subject`→`subject` held
416 of pass 1's 422 calls (98.6%): when a pass says the subject spoke, it is
stable. The instability sits in `other`↔`indeterminate` (17 of the 31), which is
a distinction the filter does not act on — both are excluded. So the two-of-two
rule costs very little precision and buys a defensible floor.

Confusion matrix (pass1 → pass2): subject→subject 416, other→other 56,
indeterminate→indeterminate 111, other→indeterminate 11, indeterminate→other 6,
indeterminate→subject 4, other→subject 4, subject→indeterminate 4,
subject→other 2.

### The aggregate comparison — the answer to the operator's question

`analysis/attribution_filter_comparison.md` (+ `_by_theme.csv`). No returns
computed.

| measure | all | subject | delta |
| --- | ---: | ---: | ---: |
| theses | 614 | 416 | −32% |
| named-ticker slots | 705 | 492 | −30% |
| distinct named tickers | 141 | 118 | −16% |
| themes with >=1 mention | 61 | 51 | −16% |
| mention rows | 257 | 179 | −30% |
| repeat mentions | 196 | 128 | −35% |
| meets existing criteria | 86 | 65 | −24% |
| scored rows (basket resolved) | 142 | 100 | −30% |
| basket ticker universe | 71 | 61 | −14% |

**The hypothesis in the handoff — "if BAKER_NAMED's composition barely moves, the
contamination was noise around a stable signal" — does not hold at the aggregate
level.** A third of the corpus and a third of the scored rows go away.

**But the loss is highly non-uniform, and that is the more useful finding.** The
ticker-anchored, high-conviction themes are untouched:

- DRAM / HBM memory bottleneck 10 → 10
- Reasoning / inference-time compute 7 → 7
- Trainium / Amazon custom silicon 5 → 5
- Metaverse / gaming as platform 5 → 5
- Frontier model concentration, Intel recovery, Target/omnichannel, Crossover
  philosophy — all unchanged

The damage concentrates in panel-driven narrative themes, which is exactly where
co-hosts talk over the subject:

- SpaceX ecosystem / Starship economics 17 → 10
- Orbital / space-based compute 13 → 7
- AI bubble not happening 7 → 2
- xAI competitive position 13 → 9
- Humanoid robotics / Tesla Optimus 9 → 5

Ten themes vanish entirely (Bottleneck trade ending, CDN / token delivery path,
Custom ASIC failure thesis, Datacenter power equipment, Defense tech
consolidation, Legacy software bottom / PE take-privates, Merchant silicon
alternative, Sovereign AI, TSMC capacity discipline, Uranium enrichment). TSMC
capacity discipline disappearing is worth the operator's eye — it is a real Baker
theme elsewhere in the corpus, so its loss here may be an artifact of which
mentions happened to land on panels.

Ten tickers drop out of resolved baskets: AVGO, AVGO(short), CAT, CMI, DLR, EQIX,
GEV, LEU, SIEGY, WDAY.

**Returns remain held** pending the operator's read of this.

### SD-ATTR-16 — Most of the `indeterminate` bucket is a quote-locator failure, not ambiguity

Triggered by spot-checking the one theme loss that looked wrong. `TSMC capacity
discipline` disappears entirely under the filter, and it clusters exactly three
theses — all `indeterminate` in both passes. Reading their evidence, all three
failed the same way: **the audit was shown the wrong turn.**

- `iltb_gpus_tpus_..._2025dec` T17 — "Turn 196 … does not contain the TSMC
  mistake quote"
- `sohn_ny_2026_tech_investor` T2 — "turn 2 contains only 'Thank you, and let me
  introduce you, Jas' — the actual T2 quote…"
- `iltb_watts_wafers_2026may` T9 — "Turn 38 (the marked quote turn) contains only
  'Yeah. I'm getting Say just like a little bit more about…'"

The model behaved correctly in all three: given a window that does not contain
the claim, it declined to guess. The failure is in `locate_turn`'s fuzzy
fallback, which places a quote on a plausible-looking but wrong turn instead of
returning `None`.

Classifying all 142 indeterminate theses by cause:

| cause | theses | named tickers |
| --- | ---: | ---: |
| `quote_not_located` (locator returned None) | 54 | 47 |
| window landed on the wrong turn (per evidence) | 27 | 41 |
| genuine ambiguity | 61 | 69 |

**81 of 142 (57%), carrying 88 of 157 named tickers (56%), are quote-location
failures rather than attribution ambiguity.** The second row is the worse one:
`quote_not_located` at least fails loudly, whereas a mislocated window produces a
confident-looking `indeterminate` that is really "wrong input".

**This changes how the aggregate comparison should be read.** A large share of
the ~30% the filter removes is tooling limitation, not co-host contamination. The
true contamination signal is the `other` bucket (56 theses / 56 tickers, 8%),
which is well-evidenced and names real participants. The `indeterminate` bucket
is mostly "the audit could not see the claim".

Rough scale of what is recoverable: at the ~70% subject base rate observed among
*located* theses, fixing the locator would return on the order of 55-60 theses
and ~60 named tickers to `subject`.

**Not fixed this session** — improving `locate_turn` is a new piece of work and
the operator's ordering puts the aggregate comparison first. Recommended before
the filter default is flipped, because the filter's cost is currently dominated
by this bug rather than by the contamination it was built to remove.

## 2026-09-08 (cont.) — locator fix, targeted re-audit

### SD-ATTR-17 — `locate_turn` had two independent defects

**(a) A normalisation bug broke exact matching.** `_norm` substitutes each
punctuation character with a single space and never collapses runs, so a quote
carrying punctuation the caption track lacks could not match at all:
`"Nvidia, and AMD"` normalises to `nvidia··and·amd` (two spaces) and fails
against `nvidia and amd`. `_norm` cannot simply be fixed — it is deliberately
length-preserving because `_char_window` maps a position found in the normalised
string back onto the raw text. Added `_squash()` (whitespace collapse) used only
on the matching path, where offsets are irrelevant.

**(b) The pass-3 fallback was close to a random-number generator.**
`difflib.SequenceMatcher(None, q, t[:400]).quick_ratio()`. Two problems
compounding: `quick_ratio()` is an *upper bound* computed from character-multiset
intersection and ignores ordering entirely, so it measures little more than "do
these two strings use similar letters"; and `t[:400]` truncates every turn, so a
quote late in a long turn scores badly while an unrelated turn's opening can
score well. That is precisely the machine for placing quotes on
plausible-but-wrong turns.

Replaced with windowed character-n-gram containment: score = fraction of the
quote's 4-grams present in the best `max(2·len(q), 160)`-char window of the turn.
N-grams degrade gracefully under caption garbling (a mangled proper noun costs
only the grams spanning it), and the window is what prevents a long rambling turn
from scoring well merely by containing a lot of everything.

Also widened pass 2 (shingle sizes 8/6/5/4/3, words >2 chars rather than >3).

**Threshold calibration** (this is why 0.70). Three measurements:
- On 311 quotes with a unique exact match, pass 3 alone picks the correct turn
  311/311 at every threshold — it is not confused when the quote is present.
- Under simulated caption garbling (word mangling + dropped words) at 35%, the
  correct turn still ranks first 120/120 and scores p05 = 0.81.
- Negative control — scoring a quote against a *different episode's* transcript,
  n=200: max 0.66, p99 0.64. 3% of negatives clear 0.55.

So 0.55 (my first guess) would admit real false positives, and there is a clean
gap between 0.66 and 0.81. **0.70** sits in it: rejects every observed negative,
accepts even heavily garbled positives.

**Result over the 614-thesis corpus:**

| | located | unlocated |
| --- | ---: | ---: |
| before | 560 (91.2%) | 54 |
| after | 599 (97.6%) | 15 |

48 newly located, 9 no longer located (the old difflib sweep had guessed; the new
pass correctly declines), and **62 placed on a different turn** — corrections to
placements that were previously wrong and invisible.

### SD-ATTR-18 — the re-audit set is 119 theses, not the 81 previously identified

The 81 were theses whose *verdict* looked placement-driven. The set the fix
actually touches is the 119 whose *window changed*: 48 newly located + 62
relocated + 9 now-unlocated. The two overlap on 67.

- **14 of the 81 keep the same window** — the fix did not help them; either
  genuine ambiguity my evidence keyword scan mis-classified, or a locator limit
  that remains.
- **52 window-changed theses were not in the 81**, and 32 of those carried a
  *decided* verdict (18 `other`, 14 `subject`). Those verdicts were formed on
  input the fix now says was wrong, so re-auditing only the 81 would have left
  32 conclusions standing on discredited windows while fixing the ones that
  merely looked broken.

Re-auditing 119 of 614 (19%) rather than the whole corpus, and running it twice
so the two-of-two protocol still holds.

**New in `audit_attribution`:** `--only <json list of [label, thesis_id]>` audits
just those theses and **merges** them into the existing episode file, preserving
order and every verdict the run did not examine; `--out-dir` targets a copy. The
pass directories were copied to `_v2` first, so the originals remain as the
pre-fix record.

### SD-ATTR-19 — `audit_theses.py` client now has a timeout too

Same defect as SD-ATTR-14, second location, fixed on the operator's instruction:
`API_TIMEOUT_SECONDS = 180.0`. The 55-minute hang cost nothing only because the
module happened to be idempotent; that is luck, not a safeguard.

### Post-fix results — the filter's real cost is ~15-19%, not 30%

Targeted re-audit of the 119 window-changed theses, run twice ($0.45 per pass),
merged into copies of the original pass directories (`*_v2`), reconciled under the
same two-of-two rule. Agreement improved 95.0% -> **96.2%**.

**Corpus attribution, before vs after the locator fix:**

| grain | | subject | other | indeterminate |
| --- | --- | ---: | ---: | ---: |
| theses (614) | before | 416 (68%) | 56 (9%) | 142 (23%) |
| | after | **467 (76%)** | 42 (7%) | 105 (17%) |
| named tickers (705) | before | 492 (70%) | 56 (8%) | 157 (22%) |
| | after | **573 (81%)** | 36 (5%) | 96 (14%) |

**Verdicts on the 119 re-audited theses:** 65 subject (55%), 50 indeterminate
(42%), 4 other (3%). On their 152 named tickers, 98 resolved to subject (**64%**)
— close to the ~70% base rate projected, and it moved 81 named-ticker slots back
into the subject population.

**Aggregate comparison, after the fix:**

| measure | all | subject | delta | (was) |
| --- | ---: | ---: | ---: | ---: |
| theses | 614 | 467 | −23.9% | (−32.2%) |
| named-ticker slots | 705 | 573 | **−18.7%** | (−30.2%) |
| distinct named tickers | 141 | 121 | −14.2% | (−16.3%) |
| themes with >=1 mention | 61 | 54 | −11.5% | (−16.4%) |
| mention rows | 257 | 205 | −20.2% | (−30.4%) |
| repeat mentions | 196 | 151 | −23.0% | (−34.7%) |
| meets existing criteria | 86 | 74 | **−14.0%** | (−24.4%) |
| scored rows (basket resolved) | 142 | 118 | **−16.9%** | (−29.6%) |
| basket ticker universe | 71 | 63 | −11.3% | (−14.1%) |

Themes lost entirely: 10 -> **7**. Tickers lost from resolved baskets: 10 -> 8.
26 of 61 themes are now completely unchanged by the filter.

**`TSMC capacity discipline` is fully recovered** — the diagnostic case that
exposed the bug. All three of its theses were `indeterminate` on a mislocated
window; all three now resolve to `subject`, and the theme survives the filter.

**Residual indeterminate, by cause** (105 theses / 96 named tickers):

| cause | theses | tickers | (was) |
| --- | ---: | ---: | ---: |
| `quote_not_located` | 15 | 11 | (54 / 47) |
| window on wrong turn | 19 | 14 | (27 / 41) |
| genuine ambiguity | 71 | 71 | (61 / 69) |

Placement failures fell from 81 theses / 88 tickers to **34 / 25**. What remains
is now dominated by genuine ambiguity, which is the honest floor: 19 transcripts
carry no `>>` speaker markers at all, so some theses simply cannot be attributed
from the text.

**Interpretation.** On the measures that drive the strategy — scored rows
(−17%), meets-criteria (−14%), named-ticker slots (−19%) — this reads as a stable
signal with a real but bounded contamination haircut, not a materially different
corpus. The `other` bucket, which is the actual contamination, is now just 42
theses / 36 named tickers (5% of slots). The default is still NOT flipped,
pending the operator.

---

## 2026-09-15 — default flipped to `subject`; v10 regenerated

**Operator decision (2026-09-15): flip the default to `subject` and unhold
returns.** The comparison above was accepted as the cost of the filter.

**SD-ATTR-20 — the flip was already in the working tree, uncommitted.**
`DEFAULT_ATTRIBUTION = "subject"` (comment dated 2026-09-09) and both argparse
defaults already pointed at it when this session opened; the operator's brief
described the default as still `all`. Verified by reading the source rather than
re-applying the change: no second flip was needed. The docstrings and `--help`
text still asserted `all` was the default, so those were corrected to match
behaviour. Also corrected `_mode_path`'s docstring, which claimed "a filtered run
must never overwrite the unfiltered deliverable" — the logic keys on
*differs-from-default*, so with the flip it is the **unfiltered** (`all`) run
that gets the `_all` suffix and the filtered run that writes the deliverable
path. That is the intended outcome, but the comment described the old polarity.

**SD-ATTR-21 — `--force-refetch` on `theme_returns_v2` only.** Both modules call
the same `fetch_prices` over the same 78-ticker `UNIVERSE` (the function is
imported from `theme_returns_v2`), so a second forced refetch in
`build_repeat_mention_events` would re-pull the identical 78 tickers the first
run had just written to `analysis/eod_prices/`. Operator's call: run the first
with `--force-refetch`, let the second read the warm cache. The prices are
equally fresh; 78 redundant EODHD calls avoided.

**Branch resolution.** `trigger-denominator-ex-spcx` was a strict fast-forward of
`main` (merge-base == `origin/main` tip, zero commits on main the branch lacked),
so it landed as a ref update, not a merge. v10 therefore runs off `main`.

**Pre-run commit.** The working tree carried 15 modified tracked files (including
both pipeline modules) and ~80 untracked artifacts. Committed before the run, so
the diff the run produces is exactly the run's effect.
