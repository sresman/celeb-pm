# Regex Word-Boundary Fix — Scoping / Blast-Radius Audit (2026-08-10)

**Status: DRY-RUN ONLY. No keys changed, no deliverable regenerated.**
Scopes the systemic substring-matching issue flagged during the 2-new-appearances task.

## TL;DR
- **Do NOT blanket-anchor every key with `\b…\b`.** It removes 133 corpus matches, but
  only ~39 are true false positives — the other ~94 are legitimate stem/plural matches
  the keys were designed to catch. Blanket anchoring would drop **27 signal events
  (20 material, 7 meets-criteria)** — almost entirely regressions.
- **The real bug is 4 short collision-keys:** `cien`, `lite`, `tpu`, `dram`.
- **Recommended targeted fix blast radius: 2 events lost, 0 theses unclustered.**

## The two failure modes anchoring must distinguish
1. **Substring-inside-a-word false positives** (what we want to kill):
   - `cien` matches "effi**cien**t / effi**cien**cy" — 19 spurious matches, all in the
     Optical theme. (Intended target: ticker CIEN / Ciena.)
   - `lite` matches "satel**lite**s" — 2 spurious (Optical).
   - `tpu` matches "ou**tpu**t" — 2 spurious (Google TPU). Also legitimately matches "tpus".
   - `dram` matches "**dram**atically" — 16 spurious (DRAM/HBM). "dramatically" starts at a
     word boundary, so leading-`\b` alone does NOT fix it — needs `\bdram\b`.
2. **Intentional stem / prefix keys** (must be preserved):
   - `disaggregat` → "disaggregation/disaggregated", `distill` → "distillation",
     `stablecoin` → "stablecoins", `scaling law` → "scaling laws",
     `humanoid robot` → "humanoid robots", `neocloud` → "neoclouds", `export control`
     → "export controls", `token factor` → "token factory", etc.
   - Naive `\b…\b` breaks ALL of these (trailing inflection blocked).

## Blanket `\b…\b` anchoring (the WRONG fix) — measured blast radius
- 56 keys change; 133 corpus matches removed.
- Re-cluster of 589 theses: **45 theses change assignment; 30 become fully unclustered**
  (unclustered 255 → 303).
- Mention-grain events: **238 → 211 (−27, 0 gained).**
- Of the 27 lost events, **20 are material** (real basket and/or meets-criteria);
  **7 are meets-criteria** — e.g. 2025-10-22 China/export→ASML,LRCX,AMAT,KLAC;
  2026-06-15 & 2026-06-27 Datacenter→EQIX,DLR; 2025-05-28 Reasoning→MU;
  2023-04-21 Optical→CIEN,COHR,LITE; plus Scaling-laws macro events.
- Verdict: destructive. The stem keys (China/export "export controls", Datacenter
  "installed physical asset", Reasoning "reasoning models", etc.) are legit and would be
  silently killed.

## Targeted fix (the RIGHT fix) — measured blast radius
Change ONLY the 4 collision keys; leading-`\b` preserves plurals where safe:
| Key | → | Rationale |
|-----|---|-----------|
| `tpu` | `\btpu` | kills "ou**tpu**t"; keeps "tpu"/"tpus" |
| `cien` | `\bcien` | kills "effi**cien**t"; keeps "ciena" |
| `lite` | `\blite` | kills "satel**lite**s"; keeps "lite" |
| `dram` | `\bdram\b` | kills "**dram**atically" (word-boundary start needs both bounds); "drams" is not a used form |

Measured on the full 589-thesis corpus (with existing overrides applied):
- **Mention-grain events: 238 → 236 (−2, 0 gained). 0 theses newly unclustered; 6 theses lose only a spurious tag.**
- The 2 lost events are BOTH spurious "Optical networking / interconnect" events that
  existed *only* via the `cien`/`lite` false positives:
  - **2023-04-21** Optical → CIEN,COHR,LITE, **meets-criteria=TRUE** (currently contributes
    1q +12.5% / 1y +13.5% to the signal slice). Really a Starlink/"satellites" thesis, not optical.
  - **2026-07-20** Optical → CIEN,COHR,LITE, meets=FALSE (via `cien`←"efficiency").
- ⚠️ Note: removing the 2023-04-21 event **does change the historical signal stats**
  (one meets-criteria winner drops out). This is a correction, not a regression — but it
  moves the numbers, so it warrants explicit sign-off and a v8→v9 changelog.

## Recommendation
1. Apply the **targeted** 4-key fix above (not blanket anchoring).
2. Also fix these the durable way instead of / in addition to per-thesis overrides:
   the 4 cluster_overrides added in the 2-new task (tpu/dram/cien for ARIA+ILTB) become
   redundant once the keys are fixed — but leave them (harmless, idempotent) or clean them
   up in the same PR.
3. Regenerate returns → **v9** deliverable + v8→v9 changelog documenting the 2 removed
   Optical events and any mention renumbering.
4. Leave all stem/prefix keys untouched.

## Method
Dry-run script re-used the pipeline's own `cluster_theses` + `apply_cluster_overrides`
against anchored copies of `theme_baskets_v3.json` (baskets on disk never modified).
Anchoring only ever removes matches, so no new events can appear — lost-event set is complete.
