# Experiment preparation independent review

Reviewed 2026-10-22. Scope: `preparation.py`, `reviewpack.py`, `prepare_experiment.py`, preparation/review-pack tests, preparation verification branch, and Task 5/6 plan. Read-only source review; only this report was added. No production raw archive was accessed.

## Finding requiring correction

### P2 — Reject preparation output inside the read-only archive

Location: `prepare_experiment.py:25-26` (output validation), followed by `save_cohort` at line 33; `reviewpack.py:26-35` permits any new or empty destination.

The CLI checks whether the destination already contains work but never checks whether its resolved path is inside `--data`. Passing `--output <archive>/review-output` succeeds and writes task JSON, document copies, annotations and HTML into the raw archive. This violates the plan's explicit read-only source-tree constraint and pollutes future recursive archive ingestion. The index builder already enforces this boundary for its own output; the new preparation entry point needs the equivalent protection.

Reproduced independently using only `PreparationTests` temporary fixture and the real subprocess CLI:

```text
prepare_experiment.py --db <temp>/index.sqlite --data <temp>/archive
  --cutoff 2026-01-10T00:00:00Z --count 1
  --output <temp>/archive/review-output
returncode: 0
wrote_inside_raw_tree: True
files_created: 11
Prepared 1/1 distinct-event tasks; all semantic review pending
```

Resolve both paths before writing and reject equality or a descendant of the source root, including resolved junction/symlink destinations. Add a CLI regression asserting exit 2, no output creation and unchanged source files. Preserve the existing refusal to overwrite nonempty review work.

## Independently executed checks

Runtime: `C:\Users\18899\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.

- `python -B test.py`: exit 0; **63 tests passed** (including 9 preparation and 4 review-pack tests).
- `python -B scripts/verify_artifacts.py`: exit 0; **16 saved runs** verified (15 pilot runs plus demo), **5 pilot tasks**, **0 preparation tasks** present at review time.
- Existing manifest checks verified both saved file hashes and their recorded code hashes against current files. Thus the original engine/CLI code covered by these manifests still matches the historical runs; the verifier does not require old manifests to enumerate newly added modules.
- Temporary CLI containment reproduction above: exit 0 confirmed the finding. Fixture removed by normal temporary-directory cleanup.

## Other observations

Selection consumes a whitelist of task fields, checks metadata source SHA256 and exact observation/task snapshot alignment, uses a deterministic seeded ordering, and permits one selected market per event. The selected document query enforces both publication and observation cutoffs. Draft annotations remain `reviewed:false` with `[0,0]` support. HTML escapes task and document values; inherited market-directory sanitization keeps task output names within the package.

The package consistently calls metadata eligibility and semantic deadline review pending. It does not promote proxy labels, heuristic extraction, or successful export into verified prospectiveness or human approval. Source provenance distinguishes freshly verified metadata hashes from indexed article-source hashes; article archives are not independently revalidated by this new selector. The date scanner is explicitly conservative and incomplete.

No further actionable correctness/security issue was identified in this bounded review. This is not a semantic review of actual candidate questions or evidence, an official outcome verification, or confirmation that a real five-event preparation package is complete. Task 6 remains pending.

## Review disposition

The initial snapshot had one reproducible P2 issue. See the follow-up below for its resolution and expanded automatic-pipeline scope.

## Follow-up: automatic full-pipeline review

The user subsequently requested automatic execution without manual review. Reviewed the new `automatic.py`, `pipeline.py`, `run_pipeline.py`, automatic/pipeline tests and the containment correction. No original engine, CLI, evidence or evaluation file was edited by this reviewer.

### Resolved — read-only source boundary

`reviewpack.validate_output` now resolves the output/source paths and rejects the source root or its descendants. Both preparation and pipeline entry points call it; direct `save_cohort` obtains the source root from preparation provenance. Independent rerun of the exact temporary CLI reproduction now gives **exit 2**, with **no output directory created**. This closes the initial finding.

### P2 — probability table reverses valid No/Yes outcomes

`pipeline.py` renders each run's probability vector unchanged but labels the table column `Yes / No`. The adapter and engine intentionally preserve the archive outcome order, including `['No', 'Yes']`. A valid reversed-order market therefore displays an inverted interpretation.

Independent temporary-fixture reproduction used a supported nomination question, `['No','Yes']`, and the article sentence `Alice Smith announced her candidacy for the Republican presidential nomination.` The fixed result was `[0.017986209962091555, 0.9820137900379085]`; the HTML rendered `0.018 / 0.982` under `Yes / No`. The actual Yes probability was 0.982. Reorder by outcome names for the fixed header, or print an explicit per-row outcome/probability mapping; add a reversed-order nonuniform regression.

### P2 — artifact verifier lacks automatic root manifest dispatch

At the reviewed snapshot `scripts/verify_artifacts.py` recognizes only preparation manifests before treating all remaining manifests as ordinary runs. A new `automatic_pipeline` manifest contains `summary.json`, nested runs and no root `result.json`. Placing the requested automatic output under the normal `artifacts` directory therefore makes the verifier attempt to read a nonexistent root `result.json`. Add an explicit pipeline branch, verifying completion counts, unique events and identical mode input fingerprints while leaving nested run checks active. The developer was informed before final packaging.

### Independent results and limits

- `python -B test.py`: **70 tests passed**, exit 0.
- Read only the already generated `../tmp/automatic-check` package: **5 distinct events, 15 runs**, `completed_automatic_rules_experiment`, `human_reviewed:false`, `official_outcomes_verified:false`.
- All root-manifest file hashes matched. Every task had three modes with the same input hash and empty annotation dictionaries.
- Visible document counts were 337, 385, 246, 235 and 360. **Every task had zero automatic directional documents** at this snapshot. Four comparisons were `proxy_only`, one `no_labels`; all `verified_brier` values were null.
- Selection and directional-rule construction do not consume labels. For each task, all three predictions finish before `Store.labels` is called for its post-prediction comparison. No reviewed annotations are fabricated. Unsupported question families explicitly use zero-support rules.
- Rules and reports explicitly describe candidacy/nomination signals as unvalidated directional features, not verified outcomes. Historical-cycle matching remains an explicitly documented limitation. This review does not assert that the heuristics are accurate, calibrated, or causally valid.

Full pipeline execution was demonstrated in the saved package, but meaningful directional behavior on those real documents was not demonstrated because the rules hit none. This is distinct from the synthetic directional-rule unit tests. Final delivery should state this distinction and keep official outcome/semantic validation incomplete.

### Second follow-up — report and manifest dispatch corrections

Independent `python -B test.py` now reports **71 passing tests**, exit 0. The reversed-outcome regression and the end-to-end fixture with nonzero supporting evidence in all three modes pass. The HTML now explicitly looks up Yes and No indices before rendering, closing the probability-labeling finding.

The verifier now has an `automatic_pipeline` branch checking task/run counts, unique event IDs, identical three-mode input/annotation fingerprints, empty reviewed-annotation input, consistent automatic policy and null verified Brier. One integration detail was reported for correction: its run lookup initially used the unsanitized market ID while the pipeline uses `market_directory`; the verifier must use the same mapping for otherwise-valid IDs such as reserved Windows names or path-like IDs. This does not affect the five numeric real IDs.

### Final frozen-artifact verification

The verifier now uses the same `market_directory` mapping as the pipeline. After source freeze and generation of `artifacts/automatic-20260515`, independent `python -B scripts/verify_artifacts.py` returned **exit 0**, verifying **31 runs**, **5 historical pilot tasks** and **5 prepared tasks**. This includes the preserved 16 historical runs and the 15 new automatic runs, with matching artifact/code hashes, both cutoff clocks, budget accounting, comparison input equality and proxy isolation.

Independent inspection of the final summary confirmed **5 distinct events**, **1,563 visible documents**, **15 completed runs**, **zero directional document hits**, and final probabilities **[0.5, 0.5] in all 15 runs**. Human review and official-outcome verification are false; every verified Brier field is null. The earlier **71-test pass** includes a separate synthetic end-to-end case proving that a matched directional signal reaches all three modes without fabricated reviewed annotations.

**Final disposition: no unresolved actionable finding in the reviewed scope.** The source-tree containment, reversed-outcome reporting and automatic-manifest dispatch/directory mapping issues are closed. The automatic offline pipeline and its artifact integrity passed this review. The real cohort did not demonstrate directional prediction changes or predictive quality improvement; semantic validity, calibration and official-outcome evaluation remain unverified, as stated in the outputs.
