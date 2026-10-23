# Dynamic Retrieval Implementation Plan

> For agentic workers: use subagent-driven-development or executing-plans task by task. No remote publishing. User approved development on 2026-10-22.

**Goal:** 在用户指定目录交付可复现的专利离线实现与真实数据运行结果。
**Architecture:** 数据适配与索引、确定性算法与状态机、CLI与报告三层。源码仅标准库依赖。
**Tech Stack:** Python 3.11+, SQLite, unittest, HTML/SVG/JavaScript.
**Spec:** docs/design.md

## Global Constraints
- Raw data is read-only. Offline baseline requires no service; the user subsequently authorized DeepSeek API extraction with a supplied credential, held only in the running process.
- All development, cache, artifacts and temporary test data must reside under D:\27专利\事件预测动态检索窗口. The former C: staging has been migrated.
- Do not label price proxies as verified outcomes; no future document versions.
- Before each production unit, run its behavior tests and record missing-feature failure, then implement and rerun.

## Task 1: Data adapter and index
- [x] Implement data/store.py with SQLite indexed ingestion, audit.json, market tasks at cutoff, latest eligible document versions; read fixtures first and assert no future versions and mixed schemas processed.
- [x] Interfaces: build_index(data_root: Path, db_path: Path)->dict; Store(db_path).tasks(cutoff: str)->list[dict]; Store.documents(event_id: str, cutoff: str)->list[dict]; Store.labels(market_id: str)->list[dict]. Store context manager; outputs JSON-safe dictionaries, UTC ISO strings.
- [x] Document record: id, canonical_url, source_id, provider, title, text, published_at, observed_at, content_hash, event_id, source_file, scrape_status.
- [x] Task record: market_id, event_id, question, description, outcomes, observed_at; never final price or label.
- [x] unittest fixtures include source files in wrong directory, repeated URL different text, future version, missing timestamp, malformed JSON and labels excluded from tasks.
- [x] Run full real ingestion and inspect audit; independent review.

## Task 2: Algorithm, extraction and engine
- [x] models.py; evidence.py; core.py (pure math); engine.py (transactional rounds). First behavioral tests: weights [1,.5,.25], relation 3/5=.6; zero budget effective silence unchanged; no-sample phi=0; min-source gate prevents premature stop; late recovery alters same-round probabilities; no duplicates; total spend<=budget.
- [x] Extraction accepts task-specific regex rules and reviewed annotations. Annotated evidence sets exact five elements and supports. Conservative generic rules remain explicitly heuristic.
- [x] run(task: dict, documents: list[dict], config: Config, annotations: dict|None=None)->dict returns result, rounds, evidence, config, diagnostics.
- [x] Three modes fixed/basic/enhanced. Reproducible source search with cursor and costs. Unit tests for expansion/recovery, contraction, cooldown, source reactivation, budget exhaustion and no evidence.
- [x] Review against spec and fix regressions.

## Task 3: CLI, evaluation and report
- [x] CLI index/tasks/run/compare/demo; defaults discover project root and data path from config. Run reads tasks/documents only; evaluation explicitly accesses labels after forecast.
- [x] HTML includes probability/budget/window/loss curves and round details, escaped evidence titles, no external CDN.
- [x] CLI integration tests use temporary archive, verify exit code, artifacts and JSON serialization. Report tests check script-safe JSON and escaping via malicious fixture.
- [x] Real pilot 5 eligible tasks; compare all three modes with identical frozen annotations. All labels identified as proxies. Save run manifest and hashes.

## Task 4: Delivery
- [x] README Chinese commands, patent traceability map, limitations and tested runtime; final reviewer.
- [x] Copy source/tests/docs/configs and necessary outputs to target with approved filesystem action. Re-run unittest and demo from target; verify hashes and real report.

## Task 5: Real prediction experiment preparation (continued 2026-10-22)
- [x] Add a label-blind candidate selector: cutoff-visible full metadata, strict active/closed fields, end date after cutoff, freshness, source hash checks; one market per event and enough visible full texts.
- [x] Export frozen task list, full version texts, source provenance, target-element drafts and reviewed:false support annotations; provide a local review entry page.
- [x] Test rejection of expired/closed/future/stale/changed-source tasks, distinct events, no labels/prices, draft status and safe output paths. Independently review and validate real five-event package.
- [x] Deliver updated commands, status table and report links; preserve original 15 pipeline runs as historical acceptance outputs.

## Task 6: Automatic end-to-end execution (user revised: no human review)
- [x] Generate deterministic event-specific directional rules, record version/category/limitations, and abstain on unsupported tasks or ambiguous sentences. Human review is optional, not an execution gate.
- [x] Run the three modes with identical frozen task rules, source corpus, cutoff and budgets; save full-pool rule coverage and per-run evidence, probabilities and costs.
- [x] Run five distinct-event real tasks through automatic selection, extraction, scheduling, proxy comparison and offline HTML reporting. Explicitly disclose zero directional matches and distinguish synthetic directional tests.
- [x] Final independent review, target publication and target-directory regression verification: 71 tests, 31 stored runs, 5 prepared inputs, and target CLI 5-task/15-run smoke replay passed.

## Task 7: Prediction quality and calibration (not yet complete)
- [x] Add DeepSeek automatic semantic extraction, strict machine annotation validation, runtime-only credential, request cache, model/prompt/version and factual support traces. Human review remains optional.
- [x] Validate a bounded real pilot: five distinct events, up to ten documents each, identical frozen annotations across three modes; report actual API tokens separately from simulated source budgets.
- [x] Add coverage diagnostics and event-disjoint retrospective development partitions; freeze configuration and prediction fingerprints before label access.
- [x] Add official API resolution snapshots and strict payout-based validation; Brier/log-loss/reliability/ECE use explicit denominators and exclude unresolved/unverified outcomes. Real pilot: 1/5 scoreable.
- [x] Expand to 20 new events / 400 sampled documents with source caps and time strata; freeze 8 validation / 12 test events before model calls. Run 60 forecasts on 391 validated documents, retaining 9 extraction failures.
- [ ] Establish meaningful prediction/calibration quality and a prospective protocol: expanded batch has 0/20 verified official outcomes and all predictions remain uniform; the historical LLM may contain future knowledge.
- [ ] Add ablations and calibrated source costs if supported by the experiment. Do not present proxy or synthetic results as official evaluation.

Task 5 is a bounded continuation of the offline scope authorized by the user's “下一步…请继续”. The user then explicitly requested no human review and an automatic full pipeline, so Task 6 follows that direction. The user selected DeepSeek by supplying its API credential. Task 7 semantic integration proceeds under that authorization; execution success does not establish prediction quality. Official payout evaluation is implemented; sufficient verified outcome coverage and forecast quality remain open.

Storage correction: user reiterated all project data belongs on D:. C: development and temporary directories moved with SHA-256 verification (677 files); tests use D: .runtime/tmp.

## Task 8: Bottleneck repair and expanded evaluation
- [x] Version typed matching, grid budget accumulation and frozen-metadata routing; preserve legacy policies.
- [x] Terminal-winner protocol with negative-risk identity mapping and explicit time checks; payout protocol preserved.
- [x] 20-event/240-run and 30-event/360-run shared-input development ablations.
- [x] 30 additional events / 600 sampled / 589 validated / 11 failed / 90 model-pipeline forecasts.
- [x] Independent review, audit amendment with full backup, 129 tests and 811 saved-run verification.
- [x] Bounded typed_v4 identity/relation/time comparison and conflict gates; 30-event/589-document frozen replay, 360 final runs, no model calls. See docs/matching-v4-validation.md.
- [x] Frontend per-element match status, event relation, explicit blockers and time interpretation; 164 Python + 13 JS tests and 1172 saved-run checks.
- [ ] General semantic participant/compound-event coverage and demonstrated quality gain. Historical 24/50 scoreable, Brier 0.25; v4 predictions are unscored development results, no superiority claim.


## Task 9: Local visual workbench (frozen-input initial release)
- [x] Catalog verified historical artifacts and provide task search/pagination.
- [x] Window/band/round replay, sources, probabilities, simulated budgets and independent diagnostic evidence.
- [x] Frozen input rerun, config validation, actual round observer, cancellation and partial trace export.
- [x] Same-group comparison with task/input/annotation/config/computation-version checks; saved evaluation protocol and denominator display.
- [x] Browser end-to-end real 24-round rerun equals original result and rounds; 148 Python + 13 JS tests; 812 artifact checks.
- [x] New-event selection, UTC cutoff, server-owned preview/freeze, model extraction and shared-input three-strategy runs; actual document progress, partial results, cancel/restart and parent-lifetime controls.
- [ ] Extensions: browser-triggered new-run scoring, per-grid actual expenditure and detailed step timings.
- [x] Independent v4 evaluation: 10 new-to-project events / 200 documents; 194 valid and 6 failed extractions; 30 predictions frozen before official labels; 4/10 scoreable (validation 2, test 2). All modes Brier 0.25, equal to uniform. Workflow verified; quality improvement not established. See docs/fresh-workflow-validation.md.

See docs/frontend-validation.md and docs/frontend-user-guide.md. All files on D:. This frontend does not establish forecast quality or complete remaining semantic repair.

## Task 10: Admission diagnosis before scale-up
- [x] Frozen 15-document audit: 12 actual read rejections + 3 unread; exact replay of 30 runs and source hashes unchanged; zero new model requests. See docs/admission-v4-diagnosis.md.
- [x] Single-variable coverage probe: initial window 14 to 30 days reaches all 7 directional Bab el-Mandeb documents; admission remains zero. Production settings unchanged.
- [x] Bounded typed_v5 task/role/condition parsing, source-context/conflict guards and explicit relation/time checks; 120 development runs. General semantic coverage remains open.
- [ ] Broader task coverage, semantic fact deduplication and calibrated window coverage.
- [x] Freeze typed_v5 before 18 new events / 358 documents; 356 valid, 2 failed, 54 predictions; all frozen before official labels. 17 scoreable, aggregate enhanced Brier 0.236954; all 11 scored test events remain uniform. See docs/matching-v5-validation.md.


## Task 11: Patent offline demonstration acceptance (2026-10-23)

- [x] Restore local workbench and render V5 relations, blockers, task conditions and time checks; real-browser diagnostics do not submit model requests.
- [x] Aggregate four frozen V5 cohorts from individual predictions and verified source hashes; keep original predictions and labels unchanged.
- [x] Finish 8 supplemental mechanism tests, S107 budget-fragmentation repair, frozen dependency replay protection; 205 Python / 20 frontend tests and 1376 artifact checks passed.
- [x] Publish final patent mapping, delivery report and refreshed manifest. See docs/offline-demo-acceptance.md.

## Task 12: Calibration and measured resource evaluation (2026-10-23, partial)

- [x] Pure source-cost/coverage and gamma estimation, units/provenance/insufficient-data checks; explicit per-source engine overrides; rectangular urgency-budget interpolation utility.
- [ ] Fit parameters from real query coverage/cost and incubation observations; automatic urgency-driven runtime policy. Defaults remain uncalibrated.
- [x] Development-only V6 admission and conservative fact-grouping ablations: 216 runs over 18 inspected events / 356 valid documents; preserve frozen annotations and V5 behavior. No new quality claim.
- [x] On-demand model provider, failure abstention, cache-separated request/token/retry/duration ledger; eager pipeline ledger integration. 54 cache-only runs match shared-annotation results; 795 cache hits, zero new network calls.
- [ ] Real cold/warm network cost comparison and invoice validation; incomplete in-flight attempt accounting after forced termination remains a limitation.
- [ ] New event-disjoint, preferably prospective quality/cost evaluation; do not relabel inspected V5 data as untouched test data.
- [x] 273 Python / 20 frontend tests, 1376 historical run checks, independent Phase 12 artifact checks and reviewed boundary regressions. See [phase12-delivery.md](phase12-delivery.md).
