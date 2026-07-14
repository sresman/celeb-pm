# Gavin Baker Corpus Gap-Fill — Report

**Date:** 2026-07-09
**Scope:** data-integrity fixes + fetch/extract missing appearances. **No signal scoring re-run**
(operator will re-score after review). Follows `analysis/corpus_audit.md`.
**Pipeline:** `tools/transcripts/` (targets.py → fetch_youtube / fetch_audio_whisper → extract_theses,
model `claude-sonnet-4-6`). Baseline corpus before this work: **26 files / 24 distinct events / ~316 theses**.

---

## Summary

- **⭐ The Unity gap is closed.** Ticker **U (Unity)** now appears in the corpus for the **first time**,
  via the Limitless/Bankless episode (2026-05-28): thesis **T5 — "Unity Software is a world-model
  builder for robotics and AGI training… a sleeper AI infrastructure play."**
- **13 new appearances fetched + extracted** (+191 theses). CNBC + 4 ILTB via Whisper included.
- **5 mis-dated files corrected at all layers** + **1 red herring (Heller) removed at source.** The
  date errors were feeding date-anchored signal scoring with dates wrong by up to ~2 years.
- **Net-new top-10 13F tickers introduced:** **U (Unity)** and **CRWV (CoreWeave)**.
- **Corpus now: 39 files / 507 theses / 2019-11-26 → 2026-07-08.**
- **Downstream aggregates are now stale** (contain Heller, carry the old wrong dates, miss all new
  files) — must be regenerated in the re-score pass. See **§Stale aggregates**.

---

## 1. Data-integrity fixes

All corrected at every layer: `targets.py` (source of truth) → transcript filename + header →
`_master_manifest.json` → extraction JSON (`metadata.date/source/topic`) + filename. Verified via
`yt-dlp` upload dates (podcasts publish same-day, so upload date = episode date) and content checks.

| File (old → new label) | Old date | **Corrected date** | Evidence |
|---|---|---|---|
| aleph_semis_globalwarming (`2024feb`→`2025oct`) | 2024-02-14 | **2025-10-22** | YT upload 20251022; content discusses DeepSeek R1, Lip-Bu Tan as Intel CEO, US gov't Intel stake — all 2025 events |
| allin `dram_bottleneck`→`allin_ai_memory_micron_2026jun` | 2024-06-15 | **2026-06-27** | YT upload 20260627; title "Socialists Sweep NYC… Micron's Blowout, ep 278" |
| allin `secondary_markets`→`allin_liquidity_secondaries_2026jun` | 2024-06-15 | **2026-06-07** | YT upload 20260607; "All-In Liquidity Secondary Markets Panel" |
| tbpn `token_factories_2025`→`tbpn_spacex_sovereign_ai_2026jun` | 2025-11-15 | **2026-06-15** | YT upload 20260615; "SpaceX Might Be the Greatest Company" |
| iconn `globalalts_2024_gracias_gurley`→`_2026_gracias_baker` | 2024-01-15 | **2026-02-24** | YT upload 20260320; = iConnections Global Alts Miami **2026** (Feb 23-26) |
| **heller_house_spacex_cfo_2026** | 2026-02-15 | **REMOVED** | Not Baker (reporter profiling SpaceX CFO). Removed from targets.py + transcript + manifest; extraction JSON already deleted. See `_removed_files_log.md`. |

**Note — the iConnections correction created a real gap that was then filled.** The file we believed
was the 2024 panel was actually the **2026** event. The genuine **2024** iConnections panel
(Gracias/Baker/**Gurley**) was therefore never in the corpus — it has now been fetched (see §2,
`iconn_globalalts_2024_gracias_baker_gurley`, 2024-01-30).

### Aleph (2025-10-22) — 15 theses feeding signal scoring (recompute needed)
Per the downstream trace, the Aleph file produces ~8 signal events; moving 2024-02-14 → 2025-10-22
shifts every `ret_/smh_/excess_` column for them. Its 15 theses:

| ID | Summary (short) |
|---|---|
| T1 | Scaled foundation-model cos are far better investments post-reasoning (data flywheel) |
| T2 | xAI & Google have the most unique data among frontier labs (data moats) |
| T3 | Nvidia extremely hard to displace; "out-GPU the GPU" a fool's errand (NVDA, AMD) |
| T4 | SRAM-architecture niche chips (Cerebras, Groq) viable by being different |
| T5 | Next Silicon doing something fundamentally differentiated (niche accelerator) |
| T6 | SpaceX = highest risk-adjusted (Sharpe) asset in any market |
| T7 | Must-have exposure to frontier AI labs (OpenAI/Anthropic/xAI/Google DeepMind) |
| T8 | Semis structurally advantaged — AI makes global GDP more silicon-intensive |
| T9 | Intel real recovery path under Lip-Bu Tan + US gov't support; ~100% American-wafer premium |
| T10 | US export controls on China are working; Western lead now multi-decade |
| T11 | Global warming is a solved problem (solar + battery economics) |
| T12 | Humanoid robots ubiquitous in homes/factories within 10 years |
| T13 | ASI within 10 years; economic returns unknowable but trajectory supportive |
| T14 | Edge/on-device AI is a real risk to the centralized data-center boom |
| T15 | Israeli venture semis/cyber attractive — experienced (~50yo) operator-founders |

---

## 2. New appearances added (13 fetched + extracted)

`reit` = theses whose themes overlap an existing corpus theme (i.e. would likely enter an existing
signal basket on re-score). `net-new` = tickers not present anywhere in the prior 26-file corpus.

| Date | Source | Theses | Top-10 13F tickers | Net-new tickers | reit |
|---|---|---:|---|---|---:|
| 2024-01-30 | iConnections Global Alts **2024** (Gracias/Baker/Gurley) | 14 | CIEN, COHR, NVDA | Cohere, Figure AI, Mistral, Perplexity, Neuralink (all private) | 13/14 |
| 2024-02-23 | FII Institute — "Rise of the Gigafirm" panel | 11 | NVDA | — | — |
| 2024-08-07 | This Week in Startups **E1990** (Liquidity Summit, w/ Gracias) | 16 | AMD, MU, NVDA | power basket: Vistra (VST), Constellation (CEG), NRG, Talen (TLN) | 14/16 |
| 2025-01-28 | iConnections Global Alts **2025** — Future of AI | 13 | AMD, NVDA | — | 13/13 |
| 2025-03-29 | All-In **E221** — CoreWeave IPO, AI cold war | 10 | **CRWV**, MU, NVDA | **CRWV**, Samsung | 9/10 |
| 2026-05-22 | All-In **E274** — SpaceX $2T, Nvidia selloff | 19 | MU, NVDA | — | 17/19 |
| 2026-05-28 | **Limitless (Bankless)** — Unity / world models | 14 | ALAB, MU, NVDA, **U** | **U (Unity)** | 14/14 |
| 2026-06-12 | CNBC Squawk on the Street — SpaceX debut (Whisper) | 7 | NVDA | (SpaceX post-IPO, neoclouds) | 7/7 |
| 2026-07-08 | Generating Alpha **Ep.56** — career arc, AI infra | 15 | AMD, NVDA | SONY | 14/15 |
| 2024-08-27 | ILTB **EP.385** — AI, Semiconductors, Robotic Frontier (Whisper) | 20 | AMD, NVDA | — | 20/20 |
| 2022-01-25 | ILTB **EP.260** — The Cyclone Under the Surface (Whisper) | 17 | — | — | 17/17 |
| 2020-04-02 | ILTB **EP.167** — Investing Through a Bear Market (Whisper) | 15 | — | — | 12/15 |
| 2019-11-26 | ILTB **EP.149** — Tech and Consumer Growth Investing (Whisper) | 20 | — | — | 20/20 |

**Total new: 191 theses across 13 files.** The 4 ILTB episodes (Whisper `small`) reinforce existing
themes and introduce no net-new top-10 tickers — the pre-2023 ones predate Baker's current AI-infra
book (consumer/tech-growth vintage). (Ticker hygiene caveat: the extractor sometimes emits free-text
strings, e.g. "Vistra (VST)", "SpaceX (SPXC implied)" — so a few names read as net-new free-text
rather than clean tickers.)

---

## 3. Unity / world-model flag (Limitless, 2026-05-28) — the audit's target

The episode description explicitly lists Baker's portfolio (Astera Labs, Cerebras, NVIDIA, Micron,
**Unity Software**) and has a **"5:26 Unity and World Models"** chapter. Extracted theses matching the
Unity / world-model / game-engine / simulation / robotics-training flag:

- **T5 [moderate, ticker U]** — *"Unity Software is a world-model builder for robotics and AGI
  training, making it a sleeper AI infrastructure play."* ← the specific thesis absent from the prior
  319-thesis set; explains the Unity position (5.4% of book, tripled Q1 2026 with calls).
- **T6 [high_conviction, NVDA/ALAB]** — compute stack shifting pre-training → post-training/inference,
  a large new investment opportunity (context around world-model/synthetic-data training).

---

## 4. Top-10 13F ticker cross-reference

Target set: U, CIEN, MU, ALAB, LITE, COHR, VST, NVDA, CRWV, AMD, SNPS.

- **Net-new to the entire thesis corpus:** **U (Unity)** — Limitless only; **CRWV (CoreWeave)** —
  All-In E221 (also referenced free-text in CNBC).
- **Already present in prior corpus, reinforced by new files:** NVDA (ubiquitous), MU, AMD, ALAB,
  CIEN, COHR.
- **VST (Vistra)** appears net-new as free-text in TWiST E1990's power/energy basket
  (VST/CEG/NRG/TLN) — a datacenter-power theme worth a clean-ticker pass on re-score.
- **LITE, SNPS:** not newly mentioned in these 9 files.

---

## 5. Reiteration flags

~**181 of 191** new theses carry themes that overlap existing corpus themes — i.e. high thematic
continuity (AI infra, semis, memory/HBM, datacenter power, SpaceX/orbital compute, frontier labs).
On re-score these would mostly land in **existing** signal baskets (reinforcing conviction rather than
opening new themes). Genuinely new angles are few: **Unity-as-world-model (U)**, the **datacenter-power
basket (VST/CEG/NRG/TLN)**, and **orbital-compute economics** (fleshed out in CNBC/E274/BG2).

---

## 6. Skipped / deferred (with reasons)

- **Idea Farm / Meb Faber (~2025-11)** — **SKIPPED (re-syndication).** No distinct YouTube video
  exists; the "AI, Semiconductors, and the Robotic Frontier" title is Idea Farm re-posting ILTB
  **EP.385** (2024-08-27), which is being captured directly (see §Pending). Not a separate appearance.
- **Sohn Hearts & Minds Australia 2021 (~2021-12-03, Coinbase pitch)** — **still missing (LOW).** No
  accessible YouTube/transcript source found (the 2020 Sohn Aus video exists; the 2021 one does not
  surface). Logged for a future manual pass.
- **Audio-First #10 (Pappageorge, Substack)** — **deferred (LOW, unverified).** Substack-hosted audio;
  could not confirm it's a genuine Baker sit-down vs. a clip/commentary. Not fetched.

---

## 7. Podcast-only ILTB episodes (Whisper) — DONE

These 4 episodes have **no YouTube mirror** (the ILTB channel only posts video for 2025+ episodes), so
they were transcribed via `fetch_audio_whisper` (RSS enclosure → Whisper `small` on CPU; `medium`/MPS
tested slower). Wired into `RSS_TARGETS` (iTunes 1154105909); dates confirmed from the RSS feed. All 4
transcribed + extracted successfully (see §2 for thesis counts):

| Date | Episode | Priority | Theses |
|---|---|---|---:|
| 2024-08-27 | ILTB EP.385 — AI, Semiconductors, and the Robotic Frontier | MEDIUM | 20 |
| 2022-01-25 | ILTB EP.260 — The Cyclone Under the Surface | LOW | 17 |
| 2020-04-02 | ILTB EP.167 — Investing Through a Bear Market | LOW | 15 |
| 2019-11-26 | ILTB EP.149 — Tech and Consumer Growth Investing | LOW | 20 |

**Quality caveat (flag on review):** these use Whisper `small`, which slightly mis-hears proper nouns
(e.g. "Atreides"→"a treaties"). Acceptable for supplementary/historical items; if EP.385 (the
Unity-building-era MEDIUM episode) matters for extraction fidelity, a `medium`-model re-run is a cheap
follow-up (`fetch_audio_whisper --model medium --force` on that one RSS target).

---

## 8. Updated corpus stats

| | Baseline (pre-gap-fill) | **Now (final)** |
|---|---|---|
| Extraction files | 26 | **39** |
| Distinct appearances | 24 | **38** |
| Total theses | ~316 | **507** |
| Date range | 2020-05 → 2026-06 | **2019-11-26 → 2026-07-08** |

(Only the Sohn NY 2026 pair is 2 files for 1 event; all other files = 1 appearance each. Manifest
tiers: 28 youtube_auto, 4 whisper_small, 3 paywalled_lede, 2 writeup_public_portion, 1 pdf_extracted,
1 whisper_medium.)

---

## 9. Stale aggregates & downstream blast radius (regenerate on re-score)

These derived artifacts were built from the **old 27-file set** (with Heller + the 5 wrong dates) and
are now stale — they still contain Heller's 3 theses, carry the pre-correction dates, and **miss all 13
new files**:

- `analysis/thesis_timeline.json`, `thesis_timeline_v2.json`, `thesis_timeline_v2_flat.json`
- `analysis/all_summaries.json`, `analysis/thesis_audits/`, `analysis/thesis_reaudits/`
- `analysis/step4_signal_events_v6*.csv` and the earlier v2–v5 variants

**Date-change blast radius** (documented, not recomputed): the 5 corrected dates move their theses'
signal events — Aleph's ~8 events (2024-02-14 → 2025-10-22), the two All-In files and TBPN (wrong
2024/2025 dates → mid-2026), and iConnections (→ 2026-02-24). Every forward-return column
(`ret_/smh_/excess_ 1m/1q/1y/2y`) for those events changes. Removing Heller drops its 1 signal event.

**Explicitly NOT run** (deferred to the operator's re-score): `aggregate_theses.py`, `audit_theses.py`,
`theme_returns_v2.py`, `recompute_returns_v6*.py`.

---

## 10. Verification performed
- `mypy --strict` clean on `tools/transcripts/targets.py`.
- All 5 corrected files: no stale date/label/heller string remains in targets.py, manifest, transcript
  filenames, or extraction filenames; new dates present in all four layers.
- Each new extraction JSON parses; `metadata.date` matches intended date; thesis ids `T1..Tn`.
- Manifest reconciles with extraction files (39 each); tier counts consistent.
- Limitless: ≥1 Unity/world-model thesis captured (T5, ticker U) — confirmed net-new.
