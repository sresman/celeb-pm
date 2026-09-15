# Curation Gate — 2 new Baker appearances (2026-08-15 sweep)

**Pipeline paused before returns** (`theme_returns_v2` / `build_repeat_mention_events` NOT run).
Awaiting operator basket decisions, as usual.

## What ran
| Episode | Source | Transcript | Theses |
|---|---|---|---|
| **All-In 2026-08-14** (`kVzYGVJ8zUk`) | YouTube auto-caps | `youtube/2026-08-14_allin_anthropic_ipo_nvidia_500b_2026aug_kVzYGVJ8zUk.txt` | 15 |
| **a16z 2026-07-14** ("Is AI a Bubble?") | Whisper (small) on RSS MP3 — audio-only | `whisper/2026-07-14_a16z_ai_bubble_datacenters_2026jul.txt` | 15 |

Extraction → aggregate → audit → reaudit_tickers complete. `thesis_timeline_v2(_flat).json` = **619 entries** (was 589). No extraction/audit errors.

**Attribution note:** All-In = Baker is a *guest* among 4 hosts ("Gavin Baker joins the show" @0:00) — attribute only Baker's contributions (per targets.py comment). a16z = solo Baker guest → full attribution.

**Incidental fix (logged):** `fetch_audio_whisper` hit the known `write_step_manifest` truncation bug — it overwrote `whisper/_manifest.json`, dropping the 2 CNBC whisper rows from `_master_manifest.json`. Restored them into `whisper/_manifest_cnbc.json` (which the whisper fetcher never touches → won't recur). `_master_manifest.json` back to 49 entries, zero missing transcripts.

---

## GATE: new tickers not in any `theme_baskets_v3.json` basket

Recommendations below — accept/modify, then I'll edit `theme_baskets_v3.json` / `manual_overrides.json` and run returns.

| Ticker | ×mentions | Context | Recommendation |
|---|---|---|---|
| **ANTH** (Anthropic) | 5 | All-In episode is Anthropic-$2T-IPO-centric (revenue ramp, S1 as the key AI-infra demand signal) | **PRIVATE / untradeable — no EODHD price.** Track as thesis-only (like SpaceX pre-IPO). Optionally a new theme "Anthropic IPO / frontier-lab demand signal" with **no basket** (signal-only), or a proxy basket if you want returns. Your call. |
| **SpaceX** | 3 | Orbital compute / Starlink AI | Map to the existing **"Orbital / space-based compute"** theme (public proxies RKLB/LUNR/ASTS/RDW), or use post-IPO **SPCX**. Recommend reuse existing space basket. |
| **CRWV** (CoreWeave) | 2 | Neocloud | New **"Neoclouds"** basket = CRWV, NBIS (LONG). |
| **TSM** | 1 | Foundry capacity | Add to existing **"TSMC capacity discipline"** basket (currently proxied by NVDA/AVGO/MU). |
| **MRVL** (Marvell) | 1 | Custom silicon / optical DSP | Add to **"Custom ASIC"** or **"Switched scaleup networks"** basket. |
| **CSCO** (Cisco) | 1 | AI networking (Ethernet) | Add to an **AI-networking** basket (with ANET), or map to existing networking theme. |
| **WDAY** (Workday) | 1 | Silver Lake ~$43B take-private; SaaS consolidation | **"software/SaaS disruption"** basket — likely a consolidation/at-risk name (confirm direction). |
| **GEV** (GE Vernova) | 1 | Datacenter power | New **"Datacenter power equipment"** basket = GEV, CAT, CMI, SIEGY (+VRT/ETN?) (LONG). |
| **CAT** (Caterpillar) | 1 | On-site power gen | → same power-equipment basket. |
| **CMI** (Cummins) | 1 | Backup/prime power | → same power-equipment basket. |
| **SIEGY** (Siemens ADR) | 1 | Grid/datacenter electrification | → same power-equipment basket. |

Already-basketed tickers (no action): NVDA, GOOGL, AMZN, MSFT, AVGO, META, AMD, TSLA, MU.

## GATE: theme labels to check for basket coverage
Mostly covered by the existing 60 baskets. Newer/edge labels to confirm map to a key (or add one):
- **"AI frontier models"** (×9) / **"AI monetization"** (×6) — Anthropic-centric; tie to the ANTH decision above.
- **"AI financing / capital markets"** (×2) — Nvidia's $500B financing, credit-gap framing; may be signal-only (no clean basket).
- **"power/energy"** (×2) — covered if you accept the new power-equipment basket.
- Others (semiconductor supply chain, AI datacenter infrastructure, custom silicon, space/orbital, software/SaaS disruption, open-source AI) map to existing baskets.

## After sign-off (what I'll run)
```
# edit theme_baskets_v3.json / manual_overrides.json per decisions above
theme_returns_v2 --force-refetch            # EODHD cache → extend to current (Aug events)
build_repeat_mention_events --force-refetch  # → step4_signal_events_v10_with_returns_extended.{csv,xlsx}
```
EODHD cache currently ~2026-08-14; `--force-refetch` needed so the Aug-14 event gets real forward prices (will be ~0 forward since it's today's filing/appearance).
