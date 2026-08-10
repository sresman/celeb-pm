## Handoff -- transcripts -- 2026-08-10

**Session duration**: ~1 session (multi-step)
**Workstream**: transcripts (Baker corpus → signal events)

### What was built
- `tools/transcripts/targets.py` — added 2 solo-Baker YouTube appearances to `YOUTUBE_VIDEOS`:
  `NGsi2PC4y68` (ILTB "Why the markets are pricing AI wrong", 2026-08-04) and `MmNWwIYFBeI`
  (Aria Networks "MFU", 2026-04-16).
- `transcripts/youtube/*.txt` (+2) + `_manifest.json` + `transcripts/_master_manifest.json` (47 entries).
- `analysis/thesis_extractions/*` (+2), `thesis_audits/*` (+27), timelines regenerated (589 theses).
- `analysis/manual_overrides.json` — +4 `cluster_overrides` (null) removing substring-FP clusters.
- `analysis/theme_baskets_v3.json` — **targeted regex fix**: `dram`→`\bdram\b`, `cien`→`\bcien`,
  `lite`→`\blite`, `tpu`→`\btpu` (4 keys only).
- `tools/transcripts/build_repeat_mention_events.py` — OUTPUT bumped v7→v8→v9.
- Deliverables: `step4_signal_events_v8_*` then `..._v9_with_returns_extended.{csv,xlsx}` (v7/v8 kept).
- Docs: `two_new_appearances_implementation_notes.md`, `two_new_appearances_curation_gate.md`,
  `v7_to_v8_changelog.md`, `regex_word_boundary_audit.md`, `v8_to_v9_changelog.md`.
- Commits pushed to `main`: `e57de51` (v8), `98442d3` (v9 regex fix).

### Decisions made
See `workstreams/transcripts-decisions.md` 2026-08-10 (SD-2NEW-1…3, SD-REGEX-1…3). Key WHYs:
- Both appearances are solo Baker → full attribution (no Heller-House-style CFO split).
- Left T4/T7/T9 unclustered as noise: T4 is a macro credit-gap framework not a ticker trade; NVDA
  views already well-captured; overrides add maintenance surface without signal.
- **Rejected blanket `\b`-anchoring** — dry-run proved it destroys ~94 legit stem-key matches and
  drops 27 events / 7 meets-criteria. Fixed only the 4 genuine substring collisions.
- v9 removing the spurious 2023-04-21 Optical winner is a *correction* but moves historical stats
  (signal ret_1y 240.5%→257.8%), so it got explicit sign-off + a changelog.

### Current state
Complete and pushed. Corpus 47 transcripts / 589 theses. v9 deliverable = 236 events (v8 was 238;
−2 spurious Optical events, 0 return changes on shared rows, 3 mention renumbers). Pipeline ran clean
(0 extraction/audit errors). No spec was in play (prompt-driven). EODHD cache at 2026-08-07.

### Known issues
- **PIPELINE_MAP "minimal re-run" recipe is unsafe**: `fetch_youtube <ids>` overwrites the youtube
  per-step manifest → `build_manifest` truncated `_master_manifest.json` 45→16. Recovered by
  re-running `fetch_youtube` with no args. Fix `write_step_manifest` to merge-by-id (tools/transcripts/common.py).
- 3 cluster_overrides (tpu/dram/cien, 2026-08-04 & 2026-04-16) now redundant with the key fix — harmless.
- `coherent` key semantically over-matches ("coherent cluster") — patched per-thesis, not at key level.

### Next step
Optional cleanup only (nothing blocking): in `analysis/manual_overrides.json`, drop the 3 now-redundant
`cluster_overrides` (ARIA T1 `tpu`, ARIA T5 `dram`, ILTB T14 `cien`) and re-run
`theme_returns_v2` + `build_repeat_mention_events` to confirm 0 delta; keep the ILTB T3
`compute.*scale` override (not a substring collision). OR harden `write_step_manifest` (merge-by-id).

### Parallel work available
- 13F cross-reference (join `thesis_timeline_v2_flat.json` ↔ `13f_signal_triggers_clean.csv`).
- `write_step_manifest` merge-by-id hardening (independent of analysis).

### Context to load
`analysis/PIPELINE_MAP.md`, `analysis/regex_word_boundary_audit.md`, `analysis/v8_to_v9_changelog.md`,
`workstreams/transcripts-decisions.md` (2026-08-10 section).
