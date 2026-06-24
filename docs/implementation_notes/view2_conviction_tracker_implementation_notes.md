# View 2 (Conviction Tracker) — Implementation Notes & Spec Deviations

Companion to `docs/specs/view2_conviction_tracker_spec.md`. These deviations were logged during
the multi-prompt build of View 2 (Conviction Tracker). None are silent; each is a resolved
ambiguity or a small addition beyond the literal spec. This is the durable repo copy — it
supersedes the ephemeral build-workdir `spec-deviations.md`.

---

## SD-V2-1 — `still_held` is per-CHAIN (security-level), not per-cycle

**Spec:** "still_held | derived | Is the position in the most recent filing?"

**What was implemented:** `still_held = True` iff the (cusip, security_type) chain's last entry is
at the dataset's `latest_period` AND is non-EXIT. It is a property of the SECURITY across the whole
dataset, independent of which add-cycle the row belongs to.

**Consequence:** An ADD in an OLD cycle that later exited but was re-entered and is held now reports
`still_held=True`.

**Rationale:** The literal spec reads "the position … in the most recent filing"; the dataset
cannot distinguish shares by cycle.

**FLAGGED — operator confirmation required.** 2 of 3 QA reviewers preferred per-cycle (True only if
THIS add's cycle reaches `latest_period` without an EXIT). A test locks the per-chain behavior, so
flipping to per-cycle later is a one-function change. → Operator: confirm per-chain, or request
per-cycle.

---

## SD-V2-2 — `is_underlying_price` column omitted

The View-2 column table lists `is_option` but NOT `is_underlying_price` (unlike View 1). The
View-2 row therefore carries `is_option` only. Faithful to the View-2 spec; noted because it
diverges from View 1's row shape.

---

## SD-V2-3 — Sort tiebreak beyond the spec's two keys

Spec: weight_delta_pct DESC, then quarter DESC. Implemented: (weight_delta_pct DESC, quarter DESC,
cusip ASC, security_type ASC) for deterministic output on ties. Same discipline as View 1.

---

## SD-V2-4 — `quarters_held_before_add` counts OBSERVED quarters, not calendar quarters

Counts on-book cycle entries with period < add.period (NEW + matched/HELD; EXIT excluded). Missing
filings are not counted (chain-adjacency model). Example NEW(Q1)/HOLD(Q2)/ADD(Q3) → 2.

---

## SD-V2-5 — "next quarter" = next CHAIN entry

`followed_by_exit` / `followed_by_another_add` inspect `chain[idx+1]` (the next OBSERVED quarter),
not the strictly-consecutive calendar quarter. Consistent with the `prior_period` adjacency model
used pipeline-wide.

---

## SD-V2-6 — held-before-dataset entry record = first entry of the CURRENT cycle

Operator wording said "FIRST change record in the chain"; implemented as cycle-aware "first entry of
current cycle" (equal to the operator wording in the common no-prior-EXIT case). Matches "same
per-cycle logic as View 1".

---

## SD-V2-7 — `add_type` boundary: prior return == 0.0 → AVERAGING_DOWN

Per spec ("> 0" winner; "<= 0" averaging down). A prior-quarter return of exactly 0.0 classifies as
AVERAGING_DOWN. Intentional.

---

## SD-V2-8 — `return_rec` test factory gains a `price_on_filing` param (default 100.0)

Backward-compatible test-helper extension so `cumulative_return_since_entry_pct` is testable. Does
not change any View-1 test outcome.
