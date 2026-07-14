# Gavin Baker Corpus Audit — Missing Appearances & Red Herrings

**Date:** 2026-07-08
**Scope:** Audit only. No transcription or extraction performed.
**Corpus location:** `celeb-pm/analysis/thesis_extractions/` (NOT `~/Projects/discord-analysis/`,
which is an unrelated Discord-message project — this audit was written next to the actual data).
**Method:** Four parallel web-research passes (personal site + Colossus/YouTube; podcast directories +
known hosts; conferences + X + news; a dedicated 2025-2026 recency sweep). Cross-corroborated where
possible (e.g. host "sixth conversation" remark confirms the ILTB set; in-episode "second time" remark
confirms the All-In sequence).

---

## Summary

- **~42 distinct Baker public appearances identified** across all channels (Nov 2019 → Jul 2026).
- **24 present in the corpus** (26 files; two events have 2 files each — see below).
- **~18 missing**, of which:
  - **10 HIGH priority** (2025-2026; these affect live signal scoring) — includes the Unity/world-model source.
  - **2 MEDIUM** (2023-2024).
  - **~6 LOW** (pre-2023, or uncertain/likely-clip).
- **1 red herring deleted:** `2026-02-15_heller_house_spacex_cfo_2026.json` (see bottom).
- **2 data-integrity flags** on existing corpus files (Aleph date; TBPN possible duplicate).

Priority key (per task): **HIGH** = 2025-2026 · **MEDIUM** = 2023-2024 · **LOW** = pre-2023.

---

## Master List — Full Table

Status: **HAVE** = in corpus · **MISSING** = not in corpus · **EXCLUDE** = not an original Baker appearance.
"x2 files" = corpus stores the event as two segment/writeup files.

| Date | Source / Show / Venue | Host / Interviewer | URL | Est. dur | Status | Priority | Notes |
|---|---|---|---|---|---|---|---|
| 2019-11-26 | Invest Like the Best EP.149 — "Tech & Consumer Growth Investing" | Patrick O'Shaughnessy | https://colossus.com/episode/baker-tech-and-consumer-growth-investing/ | ~1h | **MISSING** | LOW | Baker's 1st ILTB. |
| 2020-04-02 | Invest Like the Best EP.167 — "Investing Through a Bear Market" | Patrick O'Shaughnessy | https://podcasts.apple.com/us/podcast/gavin-baker-investing-through-a-bear-market/id1154105909?i=1000470286606 | ~1h | **MISSING** | LOW | COVID bear market. |
| 2020-05-07 | Columbia SIMA discussion | Columbia SIMA students | https://www.youtube.com/watch?v=kFY30zE9td0 | ~1h | HAVE | — | `2020-05-07_columbia_sima_investing_2020may` |
| 2020-07-27 | Koyfin "Investing Wizards" Ep.6 | Rob Koyfman | https://www.youtube.com/watch?v=cLPjhJcl5Vk | ~45-60m | HAVE | — | `2020-07-27_koyfin_investing_wizards_ep6`. ("AI Tailwind for Semis" clip `NlZhF_pULfo` = excerpt of same.) |
| 2020-09-25 | themarket.ch — "Semiconductors are magic" | The Market (CH) | (paywalled) | print | HAVE | — | `2020-09-25_themarket_semiconductors_magic` (paywalled_lede) |
| ~2020-11 (video 2020-12-15) | Sohn Hearts & Minds Australia 2020 — omnichannel pitch | Sohn HM stage | https://www.youtube.com/watch?v=dqYbDqz500c | ~15m | HAVE | — | `2020-11-15_sohn_australia_2020_omnichannel` |
| 2021-09-13 | themarket.ch — "Inflation matters" | The Market (CH) | (paywalled) | print | HAVE | — | `2021-09-13_themarket_inflation_matters` (paywalled_lede) |
| ~2021 Fall | Graham & Doddsville, Issue 43 (print interview) | Columbia CBS students | https://business.columbia.edu/.../Graham%20&%20Doddsville_Issue%2043_vF.pdf | print | HAVE | — | `2021-11-01_graham_doddsville_issue43` (pdf_extracted) |
| 2021-11-30 | VS Partners / FT Seattle — global tech | VS Partners | — | — | HAVE | — | `2021-11-30_vspartners_global_tech` |
| ~2021-12-03 | Sohn Hearts & Minds Australia 2021 — Coinbase (COIN) pitch | Sohn HM stage | https://www.sohnheartsandminds.com.au/media/gavin-baker-stock-tip-coinbase-coin | ~10m | **MISSING** | LOW | Distinct from 2020 Sohn Aus. |
| 2022-01-25 | Invest Like the Best EP.260 — "The Cyclone Under the Surface" | Patrick O'Shaughnessy | https://joincolossus.com/episode/baker-the-cyclone-under-the-surface/ | ~1h15m | **MISSING** | LOW | Inflation/semis/private-vs-public. |
| 2022-03-25 | On The Tape / RiskReversal — "fear the market killer" | Guy Adami / Dan Nathan | — | — | HAVE | — | `2022-03-25_onthetape_fear_market_killer` |
| 2022-04-08 | themarket.ch — "There is no playbook" | The Market (CH) | (paywalled) | print | HAVE | — | `2022-04-08_themarket_there_is_no_playbook` (paywalled_lede) |
| 2023-06-19 | This Week in Startups E1764 — AI platform shift | Jason Calacanis | https://thisweekinstartups.com/episodes/OCTTCk1O9jq | ~65m | HAVE | — | `2023-06-19_twist_ai_platform_shift`. (YouTube `H_q0w2qSyGY` = clip of same.) |
| ~2024-02-28 | iConnections Global Alts Miami 2024 — panel w/ Gracias, Gurley | Ron Biscardi (mod.) | https://iconnections.io/insights/video/gracias-baker-gurley/ | ~40m | HAVE | — | `2024-01-15_iconn_globalalts_2024_gracias_gurley`. ⚠️ **Date discrepancy** — corpus 2024-01-15 vs source ~2024-02-28. (YouTube `MWE5LsO62wA` = same panel.) |
| **⚠️ 2024-02-14 / 2025-10-22** | Invested by Aleph — semiconductors & "global warming is solved" | Michael Eisenberg | https://www.aleph.vc/content/gavin-baker · https://www.youtube.com/watch?v=ugihLT9cFTE | ~85m | HAVE | — | `2024-02-14_aleph_semis_globalwarming`. ⚠️ **MAJOR date flag** — corpus dates it 2024-02-14; every web source dates the episode 2025-10-22. Same host/topic/~duration → almost certainly ONE interview mis-dated by ~20 months. **Verify** — this materially affects signal timing. |
| 2024-06-15 | All-In Podcast (x2 files: DRAM bottleneck + secondary markets) | Chamath/Jason/Sacks/Friedberg | — | ~101m + 40m | HAVE | — | `2024-06-15_allin_dram_bottleneck` + `2024-06-15_allin_secondary_markets` |
| 2024-07-01 | Thematic Investors Ep.7 | Kieran Cavanna | https://thematicinvestors.blubrry.net/2024/07/01/... | ~60m | HAVE | — | `2024-07-01_thematic_investors_scifi_history` |
| 2024-08-09 | This Week in Startups E1990 — Liquidity Summit fireside (w/ Gracias) | Jason Calacanis | https://thisweekinstartups.com/episodes/z0SaGsY7LRF | ~30-40m | **MISSING** | MEDIUM | 2nd TWiST; distinct from 2023-06-19. |
| 2024-08-27 | Invest Like the Best EP.385 — "AI, Semiconductors, and the Robotic Frontier" | Patrick O'Shaughnessy | https://colossus.com/episode/baker-ai-semiconductors-and-the-robotic-frontier/ | ~1h20m | **MISSING** | MEDIUM | See Idea Farm note below (title collision). |
| 2024-12-07 | All-In Podcast (~E205) — SEC/Bitcoin/xAI supercomputer | Chamath/Jason/Friedberg | https://podcasts.apple.com/.../id1502871393?i=1000679544989 | ~1h30m | HAVE | — | `2024-12-07_allin_sec_bitcoin_xai`. Baker's 1st All-In. |
| 2025-01-04 | All-In Podcast E209 — 2025 predictions | Chamath/Jason/Sacks/Friedberg | https://allin.onpodcastai.com/episodes/enbPZeoW7AT | ~1h56m | HAVE | — | `2025-01-04_allin_2025_predictions` |
| ~2025-01-27 | iConnections Global Alts Miami 2025 — panel "The Future of AI" (w/ Gracias) | Ron Biscardi (mod.) | https://iconnections.io/insights/video/the-future-of-artificial-intelligence-global-alts-miami-2025/ · https://www.youtube.com/watch?v=UJ3pNPFwAeM | ~40-50m | **MISSING** | HIGH | Announced on X: x.com/GavinSBaker/status/1887525455588118676 |
| 2025-03-29 | All-In Podcast E221 — AI Cold War, Signalgate, CoreWeave IPO | Chamath/Jason/Sacks/Friedberg | https://allin.onpodcastai.com/episodes/ktD1c8kiSlu | ~88m | **MISSING** | HIGH | Baker breaks down CoreWeave IPO. |
| 2025-05-28 | Sohn Montreal 2025 (inaugural) — SK Hynix (HBM) pitch | Sohn stage | https://hedgefundalpha.com/conferences/2025-sohn-montreal-atreides-gavin-baker/ | ~10-15m | HAVE | — | `2025-05-28_sohn_montreal_2025_skhynix_writeup` (writeup_public_portion) |
| ~2025-10-22 | Invested by Aleph (see 2024-02-14 row) | Michael Eisenberg | https://www.youtube.com/watch?v=ugihLT9cFTE | ~85m | HAVE* | — | *Same event as the Aleph row above — listed once; date flagged there. |
| 2025-10-30 | a16z Runtime Conf — "Is there an AI bubble?" | David George (a16z) | https://www.youtube.com/watch?v=5ze3ZNvOdRY | ~32m | HAVE | — | `2025-10-30_a16z_ai_bubble_david_george`. (An "a16z Feb 2026 / Positional Strategy" item is a **re-clip** of this — not a separate appearance.) |
| **⚠️ 2025-11-15** | TBPN — token factories / sovereign AI | "Technology Brothers" (Coogan/Hays) | — | ~33m | HAVE | — | `2025-11-15_tbpn_token_factories_sovereign_ai`. ⚠️ **Possible duplicate** of the 2026-06-15 TBPN below (same ~33m, overlapping "token"+"sovereign AI" theme). Verify which date is real. |
| ~2025-11-01 | The Meb Faber Show / The Idea Farm — "AI, Semiconductors, and the Robotic Frontier" | Meb Faber | https://theideafarm.com/podcast/gavin-baker-ai-semiconductors-and-the-robotic-frontier/ | ~1h | **MISSING?** | HIGH | ⚠️ **UNCERTAIN** — title is identical to ILTB EP.385 (2024). Could be a genuine new Meb Faber interview OR Idea Farm re-syndicating EP.385. **Verify before treating as new.** |
| 2025-12-09 | Invest Like the Best EP.451 — "Nvidia v. Google, Scaling Laws, Economics of AI" | Patrick O'Shaughnessy | https://colossus.com/episode/nvidia-v-google-the-economics-of-ai/ | ~1h26m | HAVE | — | `2025-12-09_iltb_gpus_tpus_ai_economics_yt` |
| 2026-03-02 | Capital Allocators EP.489 — "Truth-Seeking & Crossover Investing at Atreides" | Ted Seides | https://www.capitalallocators.com/podcast/truth-seeking-and-crossover-investing-at-atreides/ | ~1h9m | HAVE | — | `2026-03-02_capital_allocators_crossover`. (Some directories list ~May publish; corpus 2026-03-02.) |
| 2026-05-12 | Sohn NY 2026 — "Inside the Mind of a Tech Investor" (fireside w/ Jas Khaira) | Jas Khaira (Blackstone) | https://www.youtube.com/watch?v=2Ryr95iiYNk | ~25-35m | HAVE | — | `2026-05-12_sohn_ny_2026_khaira_writeup` + `..._tech_investor` (x2 files, writeup_public_portion). A full **video** now exists (link) if a richer transcript is wanted. |
| 2026-05-20 | Invest Like the Best EP.473 — "Watts and Wafers" | Patrick O'Shaughnessy | https://www.youtube.com/watch?v=Mmj_G9RlW-I | ~1h17m | HAVE | — | `2026-05-20_iltb_watts_wafers_yt`. Host called it their "6th conversation" → ILTB set (149/167/260/385/451/473) is complete. |
| 2026-05-22 | All-In Podcast E274 — "SpaceX's $2T Case, Nvidia Selloff" | Chamath/Jason/Friedberg (Baker subs) | https://www.youtube.com/watch?v=HGbA6ze0_3M | ~1h42m | **MISSING** | HIGH | SpaceX S-1 teardown. |
| **2026-05-28** | **Limitless: An AI Podcast (Bankless)** — "How Gavin Baker Invests in AI, and Where the Bubble is Going Next" | Josh Kale & Ejaaz Ahamadeen | https://open.spotify.com/episode/57TeNu68VQOseZMrz4uV7V · Apple id1813210890?i=1000770002821 | ~29m | **MISSING** | **HIGH** | ⭐ **THE UNITY / WORLD-MODEL SOURCE.** Has a "Unity and World Models" chapter (~5:26) where Baker calls Unity "a world model builder." Video+audio (also on YouTube). This is the source the audit was chasing — see "Known gaps" below. |
| 2026-06-07 | All-In Liquidity Summit — Secondaries panel | Chamath/Jason (+ Gerstner, Rodriques) | https://www.youtube.com/watch?v=V0lFjTWx36I | ~40m | **MISSING** | HIGH | Panel (multi-speaker); secondary vs IPO markets. |
| 2026-06-11 | BG2 Pod — SpaceX IPO / Fable 5 / AI capex | Brad Gerstner & Bill Gurley | https://www.youtube.com/watch?v=Tx9jT2c6e3U | ~1h21m | HAVE | — | `2026-06-11_bg2_spacex_ipo` |
| 2026-06-12 | CNBC "Squawk on the Street" — SpaceX public-debut day | CNBC anchors | https://www.cnbc.com/video/2026/06/12/early-spacex-investor-gavin-baker-on-companyas-new-public-market-pressures.html | ~5-8m | **MISSING** | HIGH | Short live TV hit. |
| ~2026-06-15 | TBPN — SpaceX IPO / "token path" thesis / sovereign AI | Coogan & Hays | https://www.tbpndigest.com/story/2026-06-15/gavin-baker-on-the-spacex-ipo-... | ~30-60m | **MISSING?** | HIGH | ⚠️ May duplicate the corpus 2025-11-15 TBPN — reconcile the two. |
| 2026-06-26 | All-In Podcast E278 — Socialists sweep NYC, AI memory crunch, Micron | Chamath/Jason/Sacks/Friedberg (+ Kalanick) | https://allinchamathjason.libsyn.com/socialists-sweep-nyc-... | ~1h40m | **MISSING** | HIGH | IPO segment ~1:27: Anthropic $3T, SpaceX float, Cerebras. |
| ~2026-07 | Generating Alpha Podcast Ep.56 | Amir Fischer | https://podcasts.apple.com/us/podcast/generating-alpha-podcast/id1818899431 | ~1h15m | **MISSING** | HIGH | Published very recently (~Jul 2026); exact date unpinned. Career arc + AI infra. |

### Undated / low-confidence YouTube items (from gavinbaker.net's own list — mostly clips or unclear)

| Item | URL | Assessment |
|---|---|---|
| "Rise of the Gigafirm: next trillion-dollar tech company?" | https://www.youtube.com/watch?v=esWMssGq-G0 | Panel; likely maps to a known conference — **verify**, LOW. |
| Panel w/ Gracias, Baker & Gurley | https://www.youtube.com/watch?v=MWE5LsO62wA | Almost certainly the **iConnections 2024** panel (HAVE) — not new. |
| "AI platform shift… extinction risk… Nvidia" | https://www.youtube.com/watch?v=H_q0w2qSyGY | Clip of **TWiST 2023-06-19** (HAVE) — not new. |
| Audio-First #10 — Metaverse / Apple M&A (Pappageorge) | https://pappageorge.substack.com/p/audio-first-10-... | Possible genuine ~2020-21 appearance — **verify**, LOW. |

---

## Known Gaps (operator's pre-identified list) — Resolution

| Operator's gap | Resolution |
|---|---|
| **Idea Farm Nov 2025** | Found as "The Meb Faber Show / Idea Farm — AI, Semiconductors, and the Robotic Frontier" (~2025-11-01). ⚠️ **UNCERTAIN** — the title is identical to ILTB EP.385 (2024); may be a re-syndication rather than a new interview. Verify before extracting. |
| **All-In Jun 2026** | Found: **E278 (2026-06-26)**. Also surfaced two more previously-unknown 2026 All-Ins: **E274 (2026-05-22)** and the **Liquidity Summit secondaries panel (2026-06-07)**. All MISSING, all HIGH. |
| **Squawk on the Street Jun 2026** | Found: **CNBC 2026-06-12** (SpaceX public-debut day, ~5-8m TV hit). MISSING, HIGH. |
| **Breakaway Jun 2026** | ❌ **RED HERRING.** "Breakaway – Investing & Finance" is an independent solo-host podcast (Sean Hathaway, Apple id1525004534). Its ~2026-06-13 "SpaceX, SpaceX & SpaceX" episode *reviews the IPO using Baker/Gerstner clips* — Baker does not appear as a guest. **Do not add.** (The "Gerstner+Baker+Fox+Tang" lineup some aggregators attach to it is bleed-over from the BG2 episode.) |
| **Unity / world-model source (unknown)** | ✅ **RESOLVED → Limitless: An AI Podcast (Bankless), 2026-05-28**, "How Gavin Baker Invests in AI, and Where the Bubble is Going Next." Dedicated "Unity and World Models" chapter (~5:26): Baker frames Unity as "a world model builder." This is the missing source explaining the Unity thesis absent from the 319 extracted theses. **The 247WallStreet Feb 18 2026 article does NOT contain the world-model framing** — that article is about Baker's NVIDIA leveraged calls; it only notes he "added calls" on Unity. The world-model language traces to the Limitless episode (mirrored by TechFlow May 29, Binance Square, Futunn) and a later 247WallStreet Unity piece (~Jul 3 2026). ⚠️ All 247WallStreet URLs hard-block automated fetch (Cloudflare 403) — the exact embedded YouTube iframe could not be byte-verified; **a human should open the 247WallStreet Unity article in a browser to confirm the embedded video is the Limitless episode.** Best-supported conclusion: it is. |

---

## Negative / Unconfirmed Findings (things that do NOT exist, as far as could be verified)

- **Jefferies fireside with Dan Loeb** — NOT confirmed. Only a loose secondary claim that "Loeb and Baker talked at the Jefferies Conference"; no date, URL, agenda entry, or video found. Jefferies runs a "TechTrek" series but no Baker×Loeb session surfaced. Likely private/unrecorded — treat as unverified.
- **Milken Institute Global Conference** — no Baker appearance in 2024/2025/2026 speaker listings.
- **X / Twitter Spaces (@GavinSBaker)** — none found (hosted or joined). He uses X to *announce/link* appearances (Sohn, iConnections), not to host Spaces. X pages 402-blocked, so an unindexed Space can't be fully ruled out.
- **Sohn Hong Kong / Sohn NY pre-2026** — none. His Sohn footprint is Australia (2020, 2021), Montreal (2025), NY (2026).
- **The Meb Faber Show / Idea Farm original interview** — likely a re-post of ILTB EP.385 (see uncertainty flag above).
- **On The Tape / RiskReversal beyond 2022-03-25** — later "Baker" hits are quotes of his X posts, not appearances.

---

## Data-Integrity Flags on Existing Corpus Files (not gaps — corrections)

1. **⚠️ Aleph date (HIGH impact).** `2024-02-14_aleph_semis_globalwarming` is dated 2024-02-14 in the corpus, but every web source dates the "Invested by Aleph" Baker episode to **2025-10-22**. Same host, topic, and ~85m duration → almost certainly one interview mis-dated by ~20 months. Because this project anchors signals on appearance date, a wrong date here misplaces the signal by nearly two years. **Verify and correct.**
2. **⚠️ TBPN possible duplicate.** `2025-11-15_tbpn_token_factories_sovereign_ai` and the master-list `~2026-06-15` TBPN share ~33m runtime and overlapping "token" + "sovereign-AI-won't-reach-the-frontier" themes. They may be the same episode with one wrong date (the June-2026 one carries SpaceX-IPO context; the corpus one doesn't). **Reconcile — possibly only one is real, or they are two genuine appearances.**
3. **iConnections 2024 date.** Corpus 2024-01-15 vs source ~2024-02-28 for the Gracias/Baker/Gurley panel. Minor; verify.

---

## Deleted Red Herring

**`2026-02-15_heller_house_spacex_cfo_2026.json` — REMOVED (`git rm`) on 2026-07-08.**

Not a Baker appearance. Source is "Heller House / Mission Control," a reporter/host segment profiling
**SpaceX CFO Bret Johnson** during SpaceX IPO week — Baker is not the speaker. Its 3 extracted "theses"
were mis-attributed to Baker and would contaminate the thesis timeline. Corpus drops **27 → 26 files**
(24 distinct events). Full note: `analysis/_removed_files_log.md`.

⚠️ **Downstream cleanup still owed:** the heller_house theses may persist in derived artifacts built from
the old 27-file set — `analysis/thesis_timeline*.json`, `all_summaries.json`, `thesis_audits/`,
`thesis_reaudits/`, and `transcripts/_master_manifest.json`. These need a targeted purge or regeneration
in a later pass (flagged in `_removed_files_log.md`; not actioned here since this is the audit step only).

---

## Recommended Next Actions (not executed — audit only)

1. **Fetch + extract the HIGH-priority 2025-2026 misses**, in signal-value order:
   Limitless/Bankless 2026-05-28 (Unity) → All-In E274/E278/Liquidity-Summit → iConnections 2025 →
   All-In E221 (CoreWeave) → CNBC 2026-06-12 → Generating Alpha Ep.56 → TBPN 2026-06-15 (after dedupe).
2. **Verify the two date-integrity flags** (Aleph, TBPN) — these are corrections to existing signal timing.
3. **Disambiguate the Idea Farm/Meb Faber Nov-2025 item** before spending extraction budget on it.
4. **Human-confirm the 247WallStreet→Limitless link** by opening the article in a browser.
5. **Backfill MEDIUM/LOW** (ILTB EP.385/260/167/149, TWiST E1990, Sohn Australia 2021) only if full historical coverage is wanted.
