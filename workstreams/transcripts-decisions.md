# Transcripts Workstream — Decisions

> Companion to `workstreams/transcripts.md`. Loaded on demand, not at startup.
> Append new decisions with dates; keep the workstream doc's summary lean.

---

## 2026-07-01 — Theme-basket return analysis (theme_returns.py / theme_returns_v2.py)

**Context:** Two one-shot enrichment tasks. v1 (`theme_returns.py`) filled return columns on a
pre-built event CSV. v2 (`theme_returns_v2.py`) is a clean regeneration of the events themselves
from `thesis_timeline.json` + `theme_baskets_v2.json`, then the same return math. Both are
standalone of `src/celebpm` (operator constraint) and load `EODHD_API_KEY` from `.env` with dotenv
`override=True` (the `extract_theses.py` pattern).

### Return engine (shared by both scripts)
- **SPY is the master trading calendar.** N-trading-days-forward is measured on SPY's continuous
  US market index (2020→today); basket/SMH closes are looked up on those exact dates. A ticker
  absent on a date (pre-IPO / delisted) is excluded from that interval's equal-weight average.
- **Horizons** = 1m/1q/1y/2y ≙ 21/63/252/504 forward trading days. End index past the last SPY day
  → `INSUFFICIENT_DATA`. No priced ticker at either endpoint → `NO_DATA` (v2) / `PRE_IPO` (v1).
- **Direction:** LONG raw; SHORT negates the basket return (decline = positive signal); MIXED raw.
  `excess = direction-adjusted-basket − SMH`. SMH is computed for every event regardless of basket
  (including `NO_BASKET` events, where `ret_*`/`excess_*` = `NO_BASKET` but `smh_*` is numeric).
- **`theme_baskets*.json` is authoritative for baskets**, superseding any pre-filled `basket` column
  in the input CSV (which was stale — e.g. a row said `NO_BASKET` where the JSON resolves a basket).

### Date-segment resolution (operator-confirmed)
- **Chronological breakpoint, NOT literal "last match wins."** Walk segments in order; the first
  `before` whose bound exceeds the event date wins; fall through to the `after` segment if none.
  **Why:** the space themes have multiple overlapping `before` bounds — literal last-match would give
  a 2022 event the 2024–2026 basket (LUNR/ASTS, not yet public). Breakpoint semantics matches intent.

### v2 clustering + event state machine
- **Clustering uses `re.search` on the regex `keys`/`exclude`** against the lowercased summary — NOT
  substring `in`, and NOT the thesis `themes` tag list (too fragmented). A thesis may map to multiple
  themes (intentional). Unclustered theses are counted and reported, never fatal.
- **`mention_number` / `total_theme_mentions` are unique-date based** (1-based index of the event's
  date within the theme's distinct dates / count of distinct dates), not per-thesis.
- **First-date event:** `FIRST_MENTION_AND_HC` if *any* thesis on the theme's first unique date is
  `high_conviction`, else `FIRST_MENTION`.
- **Dedup key is `(date, theme, event_type)`** — multiple distinct theses on one date can legitimately
  trigger different event types (e.g. `FIRST_MENTION_WITH_TICKERS` + `FIRST_SMID_TICKER` same row);
  those are not duplicates.
- **THESIS_REVERSAL light guard (operator-confirmed):** flag a LONG-theme thesis whose summary holds a
  bearish keyword (losing/lost/risk/mistake/bubble/worst/flinched/break down), BUT skip a match when
  that keyword also appears in the theme's own `keys` patterns. **Why:** anti-bubble/bullish themes
  ("AI bubble not happening") contain "bubble" in nearly every summary — verbatim matching floods the
  output with self-referential false reversals. The guard suppresses those while keeping genuine
  off-keyword tonal turns (11 reversal events, not flooded).

### Data / repo hygiene
- **`analysis/eod_prices/` is gitignored** (9.3M, regenerable from EODHD), mirroring the existing
  `data/price_cache/` convention. Scripts are idempotent: cached tickers are not re-fetched unless
  `--force-refetch`; only the 12 v2-new tickers (ASML/CCJ/DISH/EA/MA/META/MSTR/ORCL/RBLX/TGT/TTWO/V)
  hit the API on the v2 run.
- **Ticker → EODHD symbol** = append `.US`; `adjusted_close` (split-adjusted) is the price field;
  bad/≤0 closes are dropped per-bar. No class-share edge cases in this universe.
