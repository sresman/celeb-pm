"""Regenerate Gavin Baker signal events from scratch and compute theme-basket returns.

Clean v5 regeneration. Reads two source-of-truth files:
  - ``analysis/thesis_timeline_v2_flat.json``  (319 theses)
  - ``analysis/theme_baskets_v3.json``         (52 themes, regex ``keys``/``exclude`` + baskets)

Pipeline:
  1. Cluster each thesis into themes via the regex ``keys``/``exclude`` patterns (multi-assign).
  2. Generate signal events per theme via a state machine (first mention, first HC, third within
     1yr, first-with-tickers, HC at high-profile venue, thesis reversal).
  3. Resolve each event's basket (date-aware) from ``theme_baskets_v3.json``.
  4. Pull/cache adjusted daily closes from EODHD for the 46-ticker universe.
  5. Compute equal-weight basket return + SMH benchmark + excess at 1m/1q/1y/2y.
  6. Write ``analysis/step4_signal_events_v5.csv`` + print summary stats.

Standalone of ``src/celebpm`` (imports nothing from it).

Usage:
    python -m tools.transcripts.theme_returns_v2 [--force-refetch]
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import dotenv
import requests

from . import targets

# --- Paths ------------------------------------------------------------------
ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
TIMELINE_JSON = ANALYSIS_DIR / "thesis_timeline_v2_flat.json"
BASKETS_JSON = ANALYSIS_DIR / "theme_baskets_v3.json"
OUTPUT_CSV = ANALYSIS_DIR / "step4_signal_events_v5.csv"
PRICE_CACHE_DIR = ANALYSIS_DIR / "eod_prices"

# --- EODHD -------------------------------------------------------------------
EODHD_URL_TEMPLATE = "https://eodhd.com/api/eod/{symbol}.US"
EODHD_FROM_DATE = "2020-01-01"
EODHD_ADJ_CLOSE_KEY = "adjusted_close"
EODHD_DATE_KEY = "date"
SLEEP_BETWEEN_FETCH = 0.5
HTTP_TIMEOUT = 30

# --- Benchmarks / calendar ---------------------------------------------------
SMH_SYMBOL = "SMH"
CALENDAR_SYMBOL = "SPY"

# --- Return horizons (forward trading days) ----------------------------------
INTERVALS: dict[str, int] = {"1m": 21, "1q": 63, "1y": 252, "2y": 504}

# --- Full ticker universe (46, incl. benchmarks) -----------------------------
UNIVERSE: list[str] = [
    "AAPL", "ALAB", "AMD", "AMZN", "ANET", "ASML", "ASTS", "AVGO", "CCJ", "CEG",
    "CIEN", "COHR", "CRM", "CRWV", "DISH", "EA", "EXAI", "GOOGL", "INTC", "LITE",
    "LUNR", "MA", "META", "MSFT", "MSTR", "MU", "NOW", "NVDA", "ORCL", "QCOM",
    "RBLX", "RDW", "RKLB", "RXRX", "SDGR", "SMH", "SNOW", "SPCE", "SPCX", "SPY",
    "TEAM", "TGT", "TSLA", "TTWO", "V", "VST",
    # Added 2026-07-09 for override + new-theme baskets (Part 2/3). Delisted/
    # ADR/private names (ATVI, VSAT, SATS, CRSO) resolve to NO_DATA gracefully.
    "AMAT", "KLAC", "LRCX", "T", "VZ", "TMUS", "HUBS", "ATVI", "NBIS", "VSAT",
    "SATS", "LUMN", "U", "EQIX", "DLR", "SONY", "NTDOY", "VRT", "ETN", "PWR",
    "NET", "FSLY", "AKAM", "LEU", "CRSO",
    # Added 2026-07-16 for v4-review baskets: retail omnichannel (WMT/HD/LOW/
    # COST/KR) + SK Hynix (Korean listing; may resolve NO_DATA gracefully).
    "WMT", "HD", "LOW", "COST", "KR", "000660.KS",
]

# --- Event-generation config -------------------------------------------------
HIGH_CONVICTION = "high_conviction"
HIGH_PROFILE_VENUES: list[str] = [
    "sohn", "iconn", "iconnections", "boston investment conference", "hedgefundalpha",
]
REVERSAL_KEYWORDS: list[str] = [
    "losing", "lost", "risk", "mistake", "bubble", "worst", "flinched", "break down",
]

# --- Status sentinels --------------------------------------------------------
NO_BASKET = "NO_BASKET"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
NO_DATA = "NO_DATA"


def load_api_key() -> str:
    dotenv.load_dotenv(targets.REPO_ROOT / ".env", override=True)
    key = os.environ.get("EODHD_API_KEY", "")
    if not key:
        raise SystemExit("EODHD_API_KEY missing — it must be set in .env.")
    return key


# ---------------------------------------------------------------------------
# Durable manual-override layer (analysis/manual_overrides.json)
#
# Applied AFTER clustering + basket resolution, immediately BEFORE returns.
# Two kinds:
#   cluster_overrides: move a thesis from one theme to another (re-clustering);
#                      applied to the assignments dict before event generation.
#   event_overrides:   set resolved_basket / basket_source / basket_direction and
#                      boolean flags on a resolved event row; applied after
#                      resolve_basket, before compute_returns. Match wins over
#                      clustering by design — this file survives rebuilds.
# Match keys: theme, date, mention_number, summary_contains (str | list, all must
# be substrings, case-insensitive).
# ---------------------------------------------------------------------------
OVERRIDES_JSON = ANALYSIS_DIR / "manual_overrides.json"
PAIR_TRADE = "PAIR_TRADE"
OVERRIDE_FLAGS = (
    "is_derisk_signal", "is_thesis_reversal", "is_thesis_close",
    "exclude_from_long_stats",
)


def load_overrides() -> dict[str, list[dict[str, Any]]]:
    if not OVERRIDES_JSON.exists():
        return {"cluster_overrides": [], "event_overrides": []}
    raw = json.loads(OVERRIDES_JSON.read_text())
    return {
        "cluster_overrides": list(raw.get("cluster_overrides", [])),
        "event_overrides": list(raw.get("event_overrides", [])),
    }


def _match(m: dict[str, Any], *, theme: str, date: str, summary: str,
           mention_number: int | None = None, thesis_id: str | None = None) -> bool:
    if "theme" in m and m["theme"] != theme:
        return False
    if "date" in m and m["date"] != date:
        return False
    if "thesis_id" in m and thesis_id is not None and m["thesis_id"] != thesis_id:
        return False
    if "mention_number" in m and mention_number is not None and m["mention_number"] != mention_number:
        return False
    sc = m.get("summary_contains")
    if sc is not None:
        subs = [sc] if isinstance(sc, str) else sc
        if not all(s.lower() in summary.lower() for s in subs):
            return False
    return True


def apply_cluster_overrides(
    assignments: dict[str, list[dict[str, Any]]], overrides: dict[str, Any]
) -> None:
    """Move theses between themes per cluster_overrides (mutates assignments).

    Destination is `to_theme` (or `new_theme`). A null/empty/"unclustered"
    destination REMOVES the matched thesis from `from_theme` without re-adding
    it anywhere — it then generates no event and does not count toward any
    theme's mention numbering (the thesis still exists in the timeline).
    Match keys include `thesis_id` (per-date ordinal) alongside date/theme.
    """
    _REMOVE = {None, "", "null", "unclustered", "none"}
    for ov in overrides.get("cluster_overrides", []):
        frm = ov["from_theme"]
        to = ov.get("to_theme", ov.get("new_theme"))
        m = ov["match"]
        moved: list[dict[str, Any]] = []
        keep: list[dict[str, Any]] = []
        for t in assignments.get(frm, []):
            (moved if _match(m, theme=frm, date=t["date"],
                             summary=str(t.get("summary", "")),
                             thesis_id=t.get("thesis_id")) else keep).append(t)
        assignments[frm] = keep
        if isinstance(to, str) and to.lower() not in _REMOVE:
            dest = assignments.setdefault(to, [])
            for t in moved:
                if t not in dest:
                    dest.append(t)
        # else: null/unclustered destination -> drop (removed from scoring)


def find_event_override(
    overrides: dict[str, Any], *, theme: str, date: str, summary: str,
    mention_number: int | None = None, require_summary: bool = False,
) -> dict[str, Any] | None:
    for ov in overrides.get("event_overrides", []):
        ov_typed: dict[str, Any] = ov
        m = ov_typed["match"]
        if require_summary and "summary_contains" not in m:
            continue
        if _match(m, theme=theme, date=date, summary=summary, mention_number=mention_number):
            return ov_typed
    return None


def apply_event_override(row: dict[str, Any], ov: dict[str, Any]) -> None:
    ap = ov["apply"]
    if "resolved_basket" in ap:
        row["resolved_basket"] = ", ".join(ap["resolved_basket"])
    if "basket_source" in ap:
        row["basket_source"] = ap["basket_source"]
    if "basket_direction" in ap:
        row["basket_direction"] = ap["basket_direction"]
    for flag in OVERRIDE_FLAGS:
        if flag in ap:
            row[flag] = "TRUE" if ap[flag] else "FALSE"
    row["override_note"] = ov.get("note", "")


# ---------------------------------------------------------------------------
# THESIS_REVERSAL guard (Part 4): a reversal must express a change from Baker's
# OWN prior stance, not merely bearish-sounding words about a topic.
# ---------------------------------------------------------------------------
STANCE_REVERSAL_PATTERNS: list[str] = [
    r"no longer (believe|think|hold|see|the)",
    r"used to (think|believe|be)",
    r"previously (thought|believed|argued|said|held)",
    r"walked back", r"backtrack", r"\bwas wrong\b", r"changed (his|my|her|its) (mind|view|thinking|stance)",
    r"reversed (his|my|the|its) (view|stance|position|call)",
    r"lost its .{0,45}(leadership|advantage|edge|lead|crown|frontier|moat|position)",
    r"has ceded", r"ceded (its|the) (lead|leadership|edge)",
    r"no longer the (cost leader|leader|lowest|best)",
    r"abandon(ed|ing) (his|the|its)", r"reversal of (his|the) (prior|earlier)",
]


def is_stance_reversal(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in STANCE_REVERSAL_PATTERNS)


# ---------------------------------------------------------------------------
# Step 4: price fetch + cache (only new tickers hit the API)
# ---------------------------------------------------------------------------
def fetch_prices(api_key: str, force_refetch: bool) -> dict[str, dict[str, float]]:
    PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    prices: dict[str, dict[str, float]] = {}

    for ticker in UNIVERSE:
        cache_path = PRICE_CACHE_DIR / f"{ticker}.json"
        if cache_path.exists() and not force_refetch:
            rows = json.loads(cache_path.read_text())
        else:
            params = {
                "from": EODHD_FROM_DATE, "to": today, "period": "d",
                "fmt": "json", "api_token": api_key,
            }
            try:
                resp = requests.get(
                    EODHD_URL_TEMPLATE.format(symbol=ticker), params=params, timeout=HTTP_TIMEOUT
                )
                resp.raise_for_status()
                rows = resp.json()
                print(f"  [fetched] {ticker}")
            except requests.RequestException as exc:
                # Invalid/delisted/private ticker (e.g. 404) -> graceful NO_DATA.
                rows = []
                print(f"  [no data] {ticker}: fetch failed ({exc.__class__.__name__})")
            cache_path.write_text(json.dumps(rows))
            time.sleep(SLEEP_BETWEEN_FETCH)

        series = _series_from_rows(rows)
        prices[ticker] = series
        if not series:
            print(f"  [no data] {ticker}: EODHD returned no usable rows")
        else:
            print(f"  {ticker}: {len(series)} bars [{min(series)} .. {max(series)}]")
    return prices


def _series_from_rows(rows: Any) -> dict[str, float]:
    series: dict[str, float] = {}
    if not isinstance(rows, list):
        return series
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        date_str = raw.get(EODHD_DATE_KEY)
        close = raw.get(EODHD_ADJ_CLOSE_KEY)
        if not isinstance(date_str, str):
            continue
        if not isinstance(close, (int, float)) or close <= 0:
            continue
        series[date_str] = float(close)
    return series


# ---------------------------------------------------------------------------
# Step 1: cluster theses into themes (regex keys/exclude)
# ---------------------------------------------------------------------------
def cluster_theses(
    theses: list[dict[str, Any]], baskets: dict[str, Any]
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Return (theme -> [theses], unclustered_count). A thesis may map to many themes."""
    compiled: dict[str, tuple[list[re.Pattern[str]], list[re.Pattern[str]]]] = {}
    for theme, cfg in baskets.items():
        keys = [re.compile(p) for p in cfg.get("keys", [])]
        excl = [re.compile(p) for p in cfg.get("exclude", [])]
        compiled[theme] = (keys, excl)

    assignments: dict[str, list[dict[str, Any]]] = {theme: [] for theme in baskets}
    unclustered = 0
    for thesis in theses:
        summary_lc = str(thesis.get("summary", "")).lower()
        matched_any = False
        for theme, (keys, excl) in compiled.items():
            if not any(p.search(summary_lc) for p in keys):
                continue
            if any(p.search(summary_lc) for p in excl):
                continue
            assignments[theme].append(thesis)
            matched_any = True
        if not matched_any:
            unclustered += 1
    return assignments, unclustered


# ---------------------------------------------------------------------------
# Step 2: generate signal events per theme
# ---------------------------------------------------------------------------
def _is_hc(thesis: dict[str, Any]) -> bool:
    return thesis.get("confidence") == HIGH_CONVICTION


def _venue_match(source: str) -> bool:
    src = source.lower()
    return any(v in src for v in HIGH_PROFILE_VENUES)


def _days_between(d1: str, d2: str) -> int:
    a = dt.date.fromisoformat(d1)
    b = dt.date.fromisoformat(d2)
    return (b - a).days


def generate_events(
    theme: str, theses: list[dict[str, Any]], direction: str, key_patterns: list[str]
) -> list[dict[str, Any]]:
    """Generate (pre-dedup) signal-event records for one theme's assigned theses."""
    if not theses:
        return []
    theses = sorted(theses, key=lambda t: (t["date"], t["thesis_id"]))
    unique_dates = sorted({t["date"] for t in theses})
    total_mentions = len(unique_dates)
    date_index = {d: i + 1 for i, d in enumerate(unique_dates)}
    by_date: dict[str, list[dict[str, Any]]] = {}
    for t in theses:
        by_date.setdefault(t["date"], []).append(t)

    events: list[dict[str, Any]] = []

    def emit(event_type: str, thesis: dict[str, Any]) -> None:
        date = thesis["date"]
        events.append({
            "date": date,
            "theme": theme,
            "event_type": event_type,
            "confidence": thesis.get("confidence", ""),
            "mention_number": date_index[date],
            "total_theme_mentions": total_mentions,
            "source": thesis.get("source", ""),
            "summary": thesis.get("summary", ""),
            "summary_extended": thesis.get("summary_extended", ""),
            "tickers_direct": ", ".join(thesis.get("tickers_direct", []) or []),
        })

    first_date = unique_dates[0]
    first_date_theses = by_date[first_date]

    # FIRST_MENTION_AND_HC / FIRST_MENTION (first unique date)
    hc_on_first = next((t for t in first_date_theses if _is_hc(t)), None)
    if hc_on_first is not None:
        emit("FIRST_MENTION_AND_HC", hc_on_first)
    else:
        emit("FIRST_MENTION", first_date_theses[0])

    # FIRST_HC_NOT_FIRST_MENTION (earliest HC date that is not the first date)
    for d in unique_dates:
        hc = next((t for t in by_date[d] if _is_hc(t)), None)
        if hc is not None:
            if d != first_date:
                emit("FIRST_HC_NOT_FIRST_MENTION", hc)
            break

    # THIRD_MENTION_WITHIN_1YR
    if total_mentions >= 3 and _days_between(unique_dates[0], unique_dates[2]) <= 365:
        emit("THIRD_MENTION_WITHIN_1YR", by_date[unique_dates[2]][0])

    # FIRST_MENTION_WITH_TICKERS (earliest thesis with direct tickers)
    with_tickers = next((t for t in theses if t.get("tickers_direct")), None)
    if with_tickers is not None:
        emit("FIRST_MENTION_WITH_TICKERS", with_tickers)

    # HC_HIGH_PROFILE_VENUE (every HC thesis at a high-profile venue)
    for t in theses:
        if _is_hc(t) and _venue_match(str(t.get("source", ""))):
            emit("HC_HIGH_PROFILE_VENUE", t)

    # THESIS_REVERSAL (LONG themes only; Part-4 tightened guard: requires an
    # explicit change from Baker's own prior stance, not just bearish words).
    if direction == "LONG":
        for t in theses:
            if is_stance_reversal(str(t.get("summary", ""))):
                emit("THESIS_REVERSAL", t)

    return events


# ---------------------------------------------------------------------------
# Step 3: basket resolution
# ---------------------------------------------------------------------------
def resolve_basket(
    theme: str, event_date: str, baskets: dict[str, Any]
) -> tuple[list[str], str, str, bool]:
    """(tickers, source, direction, asterisk). Date segments = chronological breakpoint:
    first `before` whose bound > event_date wins, else the `after` segment."""
    entry = baskets[theme]
    direction = entry.get("direction", "LONG")
    asterisk = bool(entry.get("asterisk", False))

    if "tickers" in entry:
        tickers = list(entry["tickers"])
        source = entry.get("source", "")
        return tickers, source, direction, asterisk

    chosen = None
    after_segment = None
    for seg in entry["date_segments"]:
        if "before" in seg:
            if event_date < seg["before"]:
                chosen = seg
                break
        elif "after" in seg:
            after_segment = seg
            if event_date >= seg["after"]:
                chosen = seg
                break
    if chosen is None:
        chosen = after_segment
    if chosen is None:
        raise SystemExit(f"No applicable date_segment for {theme!r} at {event_date}")
    return list(chosen.get("tickers", [])), chosen.get("source", ""), direction, asterisk


# ---------------------------------------------------------------------------
# Step 5: return computation
# ---------------------------------------------------------------------------
def _ticker_return(series: dict[str, float], start: str, end: str) -> float | None:
    s = series.get(start)
    e = series.get(end)
    if s is None or e is None:
        return None
    return (e / s - 1.0) * 100.0


def compute_returns(
    event_date: str, basket: list[str], direction: str,
    prices: dict[str, dict[str, float]], calendar: list[str],
) -> dict[str, Any]:
    smh_series = prices.get(SMH_SYMBOL, {})
    start_idx = bisect.bisect_left(calendar, event_date)
    out: dict[str, Any] = {}

    if start_idx >= len(calendar):
        for label in INTERVALS:
            out[f"ret_{label}"] = INSUFFICIENT_DATA
            out[f"smh_{label}"] = INSUFFICIENT_DATA
            out[f"excess_{label}"] = INSUFFICIENT_DATA
        return out

    start_date = calendar[start_idx]
    for label, n_days in INTERVALS.items():
        end_idx = start_idx + n_days
        if end_idx >= len(calendar):
            out[f"ret_{label}"] = INSUFFICIENT_DATA
            out[f"smh_{label}"] = INSUFFICIENT_DATA
            out[f"excess_{label}"] = INSUFFICIENT_DATA
            continue
        end_date = calendar[end_idx]

        smh_ret = _ticker_return(smh_series, start_date, end_date)
        out[f"smh_{label}"] = round(smh_ret, 2) if smh_ret is not None else INSUFFICIENT_DATA

        if not basket:
            out[f"ret_{label}"] = NO_BASKET
            out[f"excess_{label}"] = NO_BASKET
            continue

        per_ticker = [
            r for t in basket
            if (r := _ticker_return(prices.get(t, {}), start_date, end_date)) is not None
        ]
        if not per_ticker:
            out[f"ret_{label}"] = NO_DATA
            out[f"excess_{label}"] = NO_DATA
            continue

        raw = sum(per_ticker) / len(per_ticker)
        signed = -raw if direction == "SHORT" else raw
        out[f"ret_{label}"] = round(signed, 2)
        out[f"excess_{label}"] = (
            round(signed - smh_ret, 2) if smh_ret is not None else INSUFFICIENT_DATA
        )
    return out


# ---------------------------------------------------------------------------
# Orchestration + output
# ---------------------------------------------------------------------------
OUTPUT_FIELDS = [
    "date", "theme", "event_type", "confidence", "mention_number", "total_theme_mentions",
    "source", "summary", "summary_extended", "tickers_direct",
    "resolved_basket", "basket_source", "basket_direction", "basket_asterisk",
    "override_note", "is_derisk_signal", "is_thesis_reversal", "is_thesis_close",
    "exclude_from_long_stats",
    *(f"ret_{l}" for l in INTERVALS),
    *(f"smh_{l}" for l in INTERVALS),
    *(f"excess_{l}" for l in INTERVALS),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-refetch", action="store_true",
                        help="Re-pull every ticker from EODHD even if cached.")
    args = parser.parse_args()

    api_key = load_api_key()
    baskets = json.loads(BASKETS_JSON.read_text())
    theses = json.loads(TIMELINE_JSON.read_text())
    print(f"Loaded {len(theses)} theses, {len(baskets)} themes.")

    # Step 1: cluster
    assignments, unclustered = cluster_theses(theses, baskets)
    clustered = len(theses) - unclustered

    # Step 1b: durable cluster overrides (re-theme specific theses)
    overrides = load_overrides()
    apply_cluster_overrides(assignments, overrides)

    # Step 2: generate events
    raw_events: list[dict[str, Any]] = []
    for theme, theme_theses in assignments.items():
        direction = baskets[theme].get("direction", "LONG")
        key_patterns = baskets[theme].get("keys", [])
        raw_events.extend(generate_events(theme, theme_theses, direction, key_patterns))

    # Dedup on (date, theme, event_type) — keep first occurrence.
    seen: set[tuple[str, str, str]] = set()
    events: list[dict[str, Any]] = []
    for ev in raw_events:
        triple = (ev["date"], ev["theme"], ev["event_type"])
        if triple in seen:
            continue
        seen.add(triple)
        events.append(ev)

    # Step 4: prices
    print(f"\nFetching prices for {len(UNIVERSE)} tickers (cache: {PRICE_CACHE_DIR}) ...")
    prices = fetch_prices(api_key, args.force_refetch)
    calendar = sorted(prices.get(CALENDAR_SYMBOL, {}).keys())
    if not calendar:
        raise SystemExit(f"No {CALENDAR_SYMBOL} calendar data — cannot anchor returns.")
    print(f"Calendar ({CALENDAR_SYMBOL}): {len(calendar)} days [{calendar[0]} .. {calendar[-1]}]")

    # Steps 3 + 5: resolve baskets, apply event overrides, compute returns
    for ev in events:
        tickers, source, direction, asterisk = resolve_basket(ev["theme"], ev["date"], baskets)
        ev["resolved_basket"] = ", ".join(tickers)
        ev["basket_source"] = source if source else NO_BASKET
        ev["basket_direction"] = direction
        ev["basket_asterisk"] = str(asterisk)
        ov = find_event_override(
            overrides, theme=ev["theme"], date=ev["date"],
            summary=str(ev.get("summary", "")), mention_number=ev.get("mention_number"),
        )
        if ov is not None:
            apply_event_override(ev, ov)
        basket = [x.strip() for x in ev["resolved_basket"].split(",") if x.strip()]
        if ev["basket_source"] == PAIR_TRADE or ev["basket_direction"] == PAIR_TRADE:
            for label in INTERVALS:
                ev[f"ret_{label}"] = PAIR_TRADE
                ev[f"smh_{label}"] = PAIR_TRADE
                ev[f"excess_{label}"] = PAIR_TRADE
        else:
            ev.update(compute_returns(ev["date"], basket, ev["basket_direction"], prices, calendar))

    # Step 6: sort + write
    events.sort(key=lambda e: (e["date"], e["theme"]))
    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(events)
    print(f"\nWrote {len(events)} signal events → {OUTPUT_CSV}")

    _print_summary(events, clustered, unclustered)


def _avg(vals: list[float]) -> str:
    return f"{sum(vals) / len(vals):>8.2f}" if vals else f"{'--':>8}"


def _print_summary(events: list[dict[str, Any]], clustered: int, unclustered: int) -> None:
    labels = list(INTERVALS)
    ret_cols = [f"ret_{l}" for l in labels]

    print(f"\n=== Totals ===\nSignal events: {len(events)}")
    print(f"Theses clustered: {clustered} | unclustered: {unclustered}")

    print("\n=== Events by type ===")
    by_type: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        by_type.setdefault(ev["event_type"], []).append(ev)
    for et in sorted(by_type, key=lambda k: -len(by_type[k])):
        print(f"  {et:<28} {len(by_type[et])}")

    def table(title: str, groups: dict[str, list[dict[str, Any]]], win: bool = False) -> None:
        print(f"\n=== {title} ===")
        header = f"{'group':<28} {'n':>3}  " + "  ".join(f"{l:>8}" for l in labels)
        print(header)
        print("-" * len(header))
        for g in sorted(groups):
            rows = groups[g]
            cells = []
            for col in ret_cols:
                nums = [r[col] for r in rows if isinstance(r[col], (int, float))]
                if win:
                    cells.append(
                        f"{100 * sum(1 for v in nums if v > 0) / len(nums):>7.1f}%"
                        if nums else f"{'--':>8}"
                    )
                else:
                    cells.append(_avg(nums))
            print(f"{g:<28} {len(rows):>3}  " + "  ".join(cells))

    table("Avg basket return by event_type", by_type)

    by_source: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        by_source.setdefault(ev["basket_source"], []).append(ev)
    table("Avg basket return by basket_source", by_source)

    table("Win rate (% positive) by event_type", by_type, win=True)


if __name__ == "__main__":
    main()
