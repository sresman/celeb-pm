# Signal Events Changelog — v8 → v9 (2026-08-10)

Deliverable: `analysis/step4_signal_events_v9_with_returns_extended.{csv,xlsx}` (v8 preserved for diff).
Driver: **targeted regex word-boundary fix** to 4 substring-collision keys in `theme_baskets_v3.json`.
Scoping: see `analysis/regex_word_boundary_audit.md` (blanket `\b`-anchoring was rejected as destructive;
only 4 keys are genuinely substring-unsafe).

## The fix (4 keys only — stem/prefix keys left untouched)
| Key | → | Kills (false positive) | Keeps |
|-----|---|------------------------|-------|
| `dram` | `\bdram\b` | "**dram**atically" | "dram", "dram cycle" |
| `cien` | `\bcien` | "effi**cien**t/effi**cien**cy" | "ciena" |
| `lite` | `\blite` | "satel**lite**s" | "lite" |
| `tpu` | `\btpu` | "ou**tpu**t" | "tpu", "tpus" |

`tpu.*v8` / `tpu.*cost` verified to have **no** residual "output"-style false positives, so left as-is.

## Headline
- **Rows: 238 → 236 (−2, 0 gained).**
- **0 return/basket changes on any of the 236 shared events.**
- 3 Optical mentions **renumbered** (mention_number only): 2024-01-30 (2→1),
  2024-07-01 (3→2), 2026-05-20 (4→3) — the removed 2023-04-21 Optical mention was chronologically first.
- Signal slice **improves**: n 45 → **44**, ret_1y **240.5% → 257.8%**, winrate 100%.
  (Removing a below-average spurious winner raises the mean.) Control n 134 → 133.
- No price refetch needed — corpus dates unchanged; EODHD cache still at 2026-08-07.

## Removed events (2) — both spurious, caused by the fixed keys
| Date | Theme | Basket | meets | Why removed |
|------|-------|--------|:--:|-------------|
| 2023-04-21 | Optical networking / interconnect | CIEN,COHR,LITE | ✓ | `lite`←"satel**lite**s" — this is an All-In Starlink/satellites thesis, not optical networking. Was contributing +12.5% 1q / +13.5% 1y to the **signal** slice. |
| 2026-07-20 | Optical networking / interconnect | CIEN,COHR,LITE | – | `cien`←"effi**cien**cy" — CNBC drawdown thesis, no optical content. Was in the control slice. |

Both events existed ONLY via the substring false positives; after the fix the underlying
theses retain their correct theme assignments (no thesis became unclustered).

## Note on redundancy with prior overrides
The 4 `cluster_overrides` added in the 2-new-appearances task (ARIA T1 `tpu`, ARIA T5 `dram`,
ILTB T14 `cien`, ILTB T3 `compute.*scale`) are now partly redundant with this key fix (tpu/dram/cien
no longer mis-match those theses at the key level). They are harmless and idempotent, so left in
place; `compute.*scale`→"hyperscaler" is NOT a substring-collision (real words) and still relies on
its override. A future cleanup could drop the 3 now-redundant overrides.
