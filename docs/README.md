# Docs Index -- celeb-pm

Canonical location for specs, frameworks, and reference material. Specs are loaded on-demand by task prompts, not ambiently.

---

## Specs (`docs/specs/`)

- `docs/specs/13f_analysis_pipeline_spec.md` -- canonical 13F parser & position-reconstruction pipeline spec (schemas §1.x, classification, thresholds). Implemented incrementally across the multi-prompt build (Prompt 1: discovery; Prompt 2: parse/positions).
- `docs/specs/view2_conviction_tracker_spec.md` -- View 2 (Conviction Tracker): one row per ACTIVE_ADD event with forward returns, add-type classification (adding-to-winners vs averaging-down), and follow-through stats. **Phase-2 View 2 IMPLEMENTED** — wired into `run_pipeline` and the standalone `python -m celebpm.build_views` runner. (Views 3/4 still pending.)

---

## Reference (`docs/reference/`)

_Add reference material here as needed._
