# Expanded frozen cohort implementation plan

Execution: inline, following the approved continuation. All code, caches, tests and artifacts remain on D:. Python stdlib only.

Goal: increase event diversity and initial window coverage without selecting on labels, model support or forecast scores.

- [x] Add deterministic window/band/history sampling at 50/30/20 target shares, strict source cap, double time gate, URL/normalized-body deduplication and explicit market-commentary exclusions.
- [x] Exclude every event already represented in saved forecasts. Require at least 12 selected documents, 4 in the initial window, 8 within initial window plus band, and 3 sources; do not relax gates to hit a target count.
- [x] Target at most 20 new events with at most 20 documents each. Freeze actual retained count, model configuration, split, inputs and hashes before model requests. Report any target shortfall.
- [x] Extend semantic runner to consume the exact frozen cohort, preserving original selection defaults for replay. Three modes share the same validated subset and simulation budget.
- [x] Run bounded model extraction using user-authorized runtime credential, record failures and tokens; no failed rows converted to zero support.
- [x] Collect official outcomes after forecasts. Use pre-model event split in quality evaluation. Do not claim this retrospective historical-LLM study is a prospective uncontaminated test.
- [x] Run regression and artifact checks, update Chinese report/index and implementation ledger.

Files: expansion.py, preparation.py (optional filters), semantic_pipeline.py (frozen input path), run_expansion.py, run_deepseek.py, quality_pipeline.py, artifact verifier and focused tests. Preserve historical source blobs before edits.

Actual outcome: 20 new events / 400 sampled / 391 validated / 9 failed / 60 runs; official scoreable 0/20. Execution completed with extraction failures retained; prediction quality remains unestablished. See expansion-validation.md.
