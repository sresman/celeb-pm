# basket_reresolution_v2 — implementation notes

## 2026-07-14 — Re-run basket resolution with a cleaner prompt (v2)

Task: for each of the 241 `signal_events` rows, send summary fields to
`claude-opus-4-6` with the operator-supplied prompt, and write
`analysis/basket_reresolution_v2.csv`. Do not apply anything. Sort changed rows first.

Script: `scratchpad/reresolve_v2.py` (one `messages.create` per row, 8-way thread pool,
adaptive thinking + `effort: medium`, `max_tokens=4000`, retry-with-backoff on
API errors and one retry on JSON-parse failure).

### Decisions / deviations

- **DEV-1 — `tickers_implied` omitted (does not exist).** The task said to send
  `summary, summary_extended, tickers_direct, tickers_implied, confidence`. The
  `signal_events` sheet has **no `tickers_implied` column** (only `tickers_direct`).
  `tickers_implied` lives in the `thesis_timeline*.json` files, which the task
  explicitly forbids using ("do not use any other data source"). Resolution: sent
  only the four columns that exist. Flagged to operator.

- **DEV-2 — prompt sent verbatim, with a labeled STATEMENT block inserted.** The
  operator prompt refers to "the following statement" but is otherwise a fixed
  block. I injected the row's summary/extended/tickers/confidence as a labeled
  `STATEMENT` section immediately after the first sentence, then the two questions
  and the JSON output spec verbatim. `tickers_direct` is labeled as "may be
  incidental" to match the prompt's own caution that a mention ≠ a view.

- **SD-1 — column mapping.** `old_basket`←`resolved_basket`, `old_source`←
  `basket_source`, `old_direction`←`basket_direction`. NaN `resolved_basket` → "".
  Blank `basket_source` → treated as `NO_BASKET`.

- **SD-2 — model output → new_* columns.** `trade:true` → `new_basket`=basket
  string, `new_source`=source, `new_direction`=direction. `trade:false` →
  `new_basket=""`, `new_source="NO_BASKET"`, `new_direction=""`.

- **SD-3 — `changed` definition.** `old_is_trade = (old_source != NO_BASKET)`.
  - trade-status differs → YES.
  - both no-trade → NO (direction/basket ignored; old rows carry a junk `LONG`).
  - both trades → YES iff basket **set** (order-insensitive, `/` and `,` both split),
    OR `source`, OR `direction` differ. Source is included deliberately so a
    resolution-provenance change surfaces for review (conservative / over-flags
    rather than under-flags). Note old sources `RETAIL_PROXY`/`CONSTRUCTED`/
    `PAIR_TRADE` can never equal a model `source` (BAKER_NAMED/OBVIOUS_UNIVERSE),
    so those rows will tend to read `changed=YES`.

- **SD-4 — `override_exists` matches `event_overrides` only.** Matched on the
  README's keys: `theme` (exact), `date` (exact string), `mention_number` (int),
  `summary_contains` (str|list, all substrings, case-insensitive, matched against
  `summary`). `cluster_overrides` (theme re-assignment) are NOT counted — they
  don't supersede a basket, which is what this audit compares. First-match / any-match
  semantics: YES if any event_override matches.

- **SD-5 — model params.** `claude-opus-4-6` exactly as the operator specified
  (valid current model ID). Adaptive thinking + `effort: medium` chosen because the
  trade/no-trade + universe-resolution judgment benefits from reasoning; the whole
  point of the re-run is cleaner judgment. Non-streaming at `max_tokens=4000` (well
  under SDK timeout; JSON output is tiny even with thinking).

- **Sort:** `changed=YES` rows first, then `changed=NO`; original sheet order
  preserved within each group (stable).

- **Not applied:** nothing writes back to the sheet, overrides, or any pipeline
  artifact. Output is `analysis/basket_reresolution_v2.csv` only.

## 2026-07-16 — Apply v4 review into manual_overrides.json + re-run pipeline

Input: `analysis/basket_reresolution_v4.csv` (136 rows, `final_action`). Applied 102
actionable rows (all except KEEP CURRENT=32 / KEEP NO_BASKET=2). Builder:
`scratchpad/apply_v4.py`. Full before/after in `analysis/basket_v4_application_diff.md`.

- **DEV-V4-1 — date conversion.** v4 CSV dates are `M/D/YY`; the pipeline matches events
  on ISO `YYYY-MM-DD`. Converted with `strptime("%m/%d/%y")` (all years 19–26 → 2019–2026).
  A mismatched format would silently no-op the override — verified all 102 (theme, ISO,
  mention) exist in the current 241-row sheet before writing.
- **DEV-V4-2 — new entries PREPENDED.** `find_event_override` is first-match. New
  theme+date+mention entries are inserted ahead of the 15 existing ones so a v4 decision
  wins over any theme-level catch-all for its specific event, while catch-alls still govern
  every non-v4 mention. No existing entry deleted/modified (15→117 event, 1→1 cluster).
- **DEV-V4-3 — UNIVERSE extended by 6.** `WMT, HD, LOW, COST, KR, 000660.KS` added to
  `theme_returns_v2.UNIVERSE` (retail CHANGE baskets + SK Hynix). Required — a final_basket
  ticker absent from UNIVERSE prices to NO_DATA and the event drops out of scoring. Consistent
  with the 2026-07-09 "+25 tickers" precedent. `000660.KS` 404s on EODHD → graceful NO_DATA;
  DRAM baskets still score via MU.
- **DEV-V4-4 — PAIR_TRADE (EV SPAC).** v4 row `final_basket="PAIR_TRADE"` is a placeholder;
  tickers came from `final_note` ("short LCID/RIVN long TSLA") → `resolved_basket=["TSLA",
  "LCID(short)","RIVN(short)"]`, `basket_source=basket_direction="PAIR_TRADE"` (mirrors the
  existing Custom-ASIC PAIR_TRADE convention). Returns skipped for PAIR_TRADE, so ticker
  exactness is documentary only.
- **DEV-V4-5 — continuation entries.** 22 KEEP-continuation rows locked to their current
  `old_basket/old_source/old_direction`, tagged `"reason":"trade_continuation"`. Functionally
  a defensive pin (basket resolution is deterministic and doesn't consult the model
  re-resolution), but explicitly requested and harmless.
- **Conflicts:** no exact theme+date collisions with the 15 existing overrides. One catch-all
  functional overlap (Reasoning "flywheel") checked — the two v4 Reasoning rows don't contain
  "flywheel", so no actual collision.
- **Verification:** scored trade events 194→138 (−56, target ~57). All four STEVE spot-checks,
  continuation baskets, existing overrides (China/SpaceX-short/Custom-ASIC), and Unity(U) pass.
  **Partial:** "NO_BASKET themes → zero scored" holds for AI-bubble + scaling-laws; residual
  scored events elsewhere trace to explicit CHANGE proxies, KEEP CURRENT rows, or the existing
  SpaceX override. **Genuine gap:** 2 mentions never in v4 (AI-capex m3 2025-01-28, Broad-AI m6
  2025-10-22) kept theme defaults and still score — outside the 136-row review scope.

### Follow-up (same day) — two macro themes fully zeroed + pipeline fix

- **Operator ruling:** `AI capex ROI positive` and `Broad AI bullish / early innings` are
  never-a-trade macro commentary "regardless of which mention number." Consolidated their 14
  per-mention v4 entries into **2 theme-level NO_BASKET catch-alls** (mirrors the existing
  `Microsoft AI position` catch-all). event_overrides 117 → 105 (net +90 vs the original 15).
- **DEV-V4-6 — m4 NVDA reverted.** The theme-level ruling supersedes the v4 CHANGE that set
  `AI capex ROI positive` m4 (2025-03-29) → NVDA; m4 is now NO_BASKET. Flagged in the diff as
  the one intra-v4 supersession (latest review wins).
- **BUGFIX — theme_returns_v2 OUTPUT_FIELDS.** Added `override_note` + the 4 override flags to
  `OUTPUT_FIELDS`; `apply_event_override` sets these, but they were absent from the DictWriter
  fieldnames → `ValueError` on any overridden row. Pre-existing latent crash (masked by `| tail`
  in prior runs); the deliverable xlsx (build_repeat_mention_events) was never affected. Both
  scripts now exit 0, `mypy --strict` clean.
- **Final:** scored trade events 194 → **135** (−59). Both themes 0 scored (all 8+8 mentions
  NO_BASKET). Full before/after: `analysis/basket_v4_application_diff.md`.

## 2026-07-16 (later) — Clustering fix: 42 misclustered-thesis removals + 8 NO_BASKET flags

Full before/after: `analysis/clustering_fix_diff.md`. Builder: `scratchpad/apply_clusterfix.py`.

- **BLOCKER surfaced first (operator resolved):** the task's `Tn` labels didn't match the timeline's
  `thesis_id` (~13/29 wrong), and the 29 listed removals under-covered shared dates so they missed the
  target counts. Operator chose "extend removals to hit targets." Resolved every removal by CONTENT
  against clustered members; extended by 13 clear misclusters on DRAM/Optical/Power.
- **DEV-CF-1 — cluster_override removal support.** `to_theme`/`new_theme` null|""|"unclustered" →
  drop from `from_theme` (no re-add); `_match` gained `thesis_id`. Removal is `from_theme`-scoped
  (multi-clustered theses survive in their correct theme). `theme_returns_v2.py` edit; imported by
  build_repeat_mention_events. `mypy --strict` clean.
- **DEV-CF-2 — GLM 5.2.** Existing TPU→China override destination changed to null; plus China→null
  removal → GLM out of both themes.
- **DEV-CF-3 — event overrides matched by (theme,date), not mention_number.** Robust to the renumbering
  the removals cause; prepended so they win over catch-alls and prior per-mention overrides. Reverts
  xAI 2025-10-22 →GOOGL and supersedes the Reasoning "flywheel"/Inference/Neoclouds catch-alls for the
  flagged dates.
- **Verification:** Optical 3 ✅, Power 5 ✅, China 6 ✅, NVDA-moat 7 ✅, first-mention dates ✅, all 8
  NO_BASKET applied ✅, invariants (China/Unity/SpaceX-short) ✅. Scored 135→100 (target ~97).
  **DRAM = 9, not 7** — all 9 are genuine HBM/DRAM mentions; target 7 predates the gap-fill corpus
  growth. Did NOT cut genuine mentions to force 7; flagged for operator (which 2, if any, to drop).

## 2026-07-17 — Three corrections (Edge AI→DRAM, China NO_BASKET, TPU→NVDA moat)

Builder: `scratchpad/apply_three.py`.

- **Fix 1 (Edge AI 2024-08-27 T7 → DRAM):** had to DELETE the last-task cluster_override that
  removed (DRAM,2024-08-27,T7) as a misclustered edge thesis — same thesis this task moves INTO DRAM;
  otherwise the move would be undone. Added Edge-AI→DRAM move; removed the AAPL event override; it now
  inherits DRAM default MU. DRAM 9→10, Edge AI 7→6.
- **DEV-3F-1 — Edge AI overrides de-fragilized.** Removing 2024-08-27 renumbers Edge AI, which would
  have silently broken the mention_number-keyed NO_BASKET overrides for 2026-05-28/2026-07-08 (→ they'd
  fall back to the Edge-AI AAPL/QCOM default and become scored). Stripped `mention_number` from all Edge
  AI event overrides → match by (theme,date), robust. Verified 2026-05-28/07-08/2024-01-30 still NO_BASKET.
- **Fix 2 (China 2025-01-28 → NO_BASKET):** prepended (theme,date) event override. China scored 4→3.
- **Fix 3 (Google TPU 2025-10-30 T12 → NVDA moat):** moved the roundtripping thesis; inherits NVDA.
  NVDA moat 7→8. **Google TPU stayed at 4 (not the expected 3)** — 2025-10-30 also carries T3 ("NVDA's
  biggest threat is Google's TPU") and T4 ("custom ASIC fail; TPU external sales catalyst"), both
  genuine TPU-competitive theses that keep the date scored as GOOGL. Only the roundtripping thesis moved
  (correct); did not relabel the genuine TPU theses. Consequently **total scored stayed 100 (not 99)**:
  China −1 offset by the new NVDA-moat 2025-10-30 mention (+1); the GOOGL TPU mention legitimately remains.
- **Verified:** DRAM 2024-08-27=MU, China 2025-01-28=NO_BASKET, NVDA-moat 2025-10-30=NVDA, TPU
  2025-10-30=GOOGL, invariants (China basket, Unity) intact. `mypy --strict` clean; both scripts exit 0.
