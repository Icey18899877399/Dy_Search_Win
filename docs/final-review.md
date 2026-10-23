# Final whole-project review

Reviewed 2026-10-22, read-only implementation review against `docs/design.md`, `docs/patent-map.md`, README and the closed core/data-CLI findings. Scope includes all `src/dynamic_retrieval` modules and all five test modules. No source or test edits; only this report was added. Did not access the real archive/index or run ingestion against real data.

## Current verdict

**PASS for the reviewed implementation scope. All three final-review P2 findings are CLOSED.** After the fixes, the complete bundled-Python suite passes **50/50 tests** (2.935 seconds). Independent replays of the original review-gate and nonbinary reproductions also pass. Publication failure was independently checked at both audit and database replacement, with and without a previous index: all four cases preserve the previous database/audit pair or their prior absence and leave no temporary publication files.

No remaining actionable finding was identified in this re-review. This is a code and temporary-fixture verdict, not independent verification of the real archive's coverage or completed pilot artifacts. The parent/data agent is recording the real-index equivalence check and final real-run results separately in the data/validation reports.

## Original snapshot verdict (superseded)

**Changes required: three reproducible P2 findings remain below.** The current bundled-Python `test.py` passes **44/44 tests** (1.313 seconds). The earlier findings marked closed remain closed in this snapshot. This verdict does not claim full-dataset coverage or real pilot completion.

The declared scope is appropriate: offline binary tasks, conservative lexical support abstention, explicit event rules/annotations, simulated costs/clocks, and proxy-only evaluation. Deferred online APIs, calibration, general semantic extraction, multiclass composition and optional contraction-gain variants are not findings.

## Findings

### P2 — Annotation entries bypass the explicit review gate

**CLOSED.** `extract` now requires `annotation.get('reviewed') is True`. Synthetic demo and test annotations explicitly set `true`. Regression covers missing, null, false, string `false`, string `true`, integer 1 and integer 0, all abstaining when no configured rule supplies support. Boolean true still enables checked annotation support. The original reproduction now returns lexical support `[0,0]` for every unreviewed marker.

Location: `src/dynamic_retrieval/evidence.py:60`.

Only the literal Boolean `false` disables an annotation. A missing `reviewed` key, `null`, or the string `"false"` is accepted and exported as `reviewed_annotation`, with its directional support used in probabilities. This conflicts with README's instruction to confirm `reviewed: true` and the intended reviewed-only support path.

Reproduction: task `Will Alice win?`, outcomes `[Yes,No]`, target `{subject: Alice}`, cutoff `2026-01-03T00:00:00Z`; one document with text/title `Alice won`, published January 1, observed January 2, unique ID `x`. Run fixed mode for one round with annotation `{'x': {'elements': {'subject':'Alice'}, 'support':[1,-1], 'quote':'Alice won'}}`. Repeat adding `reviewed: null` or `reviewed: "false"`.

All three output `reviewed_annotation` and probabilities `[0.9820137900379085,0.017986209962091555]`. Adding literal `reviewed: false` instead gives `lexical_v1` and `[0.5,0.5]`.

Accept only `annotation.get('reviewed') is True` for the reviewed path, or reject malformed review markers explicitly. Mark synthetic fixtures explicitly reviewed and cover missing/null/string markers in regression tests.

### P2 — Known nonbinary outcomes are rewritten as binary when description is missing

**CLOSED.** Explicit outcome lists are classified independently of description completeness, including JSON-encoded lists. Partial nonbinary records are excluded; partial `[No,Yes]` is preserved with `partial_explicit_binary` provenance. The original three-outcome reproduction now returns no task. Pilot now requires `full_metadata`, preserving its stated full-definition selection rule. Existing full-metadata precedence and cutoff tests pass.

Locations: `src/dynamic_retrieval/data/store.py:185-197`.

The adapter only checks nonbinary outcomes when a description is also present. If a partial record explicitly supplies `outcomes=['Alice','Bob','Carol']` but lacks `description`, it is converted to inferred `[Yes,No]`. The previous nonbinary regression covers a full record and does not cover this path. `tasks` exposes the invented binary task, which `run/compare` accept; pilot happens to exclude all inferred partial metadata.

Reproduction using `tests/test_data.py` helpers: create `batch('2026-01-02T00:00:00Z', None, False)`, add `events[0].markets[0].outcomes=['Alice','Bob','Carol']`, write it to a temporary archive, build a temporary index, then query tasks at January 3. The returned market has `outcomes=['Yes','No']`, `metadata_quality='partial_inferred_binary'`; `nonbinary_markets_excluded` is zero. No full metadata snapshot is involved.

Validate explicit outcome lists independently of description completeness. Known nonbinary lists should not become inferred binary tasks; valid explicit reverse ordering `[No,Yes]` should also survive a missing description. Keep time eligibility and existing full-metadata precedence intact.

### P2 — Audit publication failure leaves a changed database after a failed rebuild

**CLOSED for the reported exception/failure path.** The audit is staged and published first; the database replacement follows, restoring the prior audit on database publication failure. If rollback itself fails, the previous-audit recovery file is retained and its path is reported. The CLI's duplicate post-build audit write was removed. Both new regression tests pass; independent checks also cover first-time builds with no prior database/audit. No two-file crash-atomicity claim is made by this review.

Locations: `src/dynamic_retrieval/data/store.py:325-326`.

The database and audit are replaced sequentially. If the audit replacement fails after the database replacement (for example a Windows sharing violation), the function raises but the old database has already been lost and the old external audit describes a different index. This contradicts the function/README promise that a failed rebuild preserves the previous index. Existing failure regression injects failure during ingest, before either publication operation.

Reproduction: build a temporary index whose one body is `old`; save database/audit bytes; change source body to `new`. Patch only `store.os.replace` so it delegates normally except when destination is `audit.json`, where it raises `PermissionError('simulated audit sharing violation')`. Rebuild raises that error, but `old_db_preserved=False`, `old_audit_preserved=True`, and `Store.documents(...)` now returns `new`. Temporary building files are cleaned, so the old index is not recoverable from those files.

Use a recoverable publication protocol, or explicitly define the embedded audit/database as the authoritative commit and return a clear committed-with-sidecar-failure status. A generic failure must not silently violate the preservation promise. Test failure at the second publication step, including consistency of the external audit.

## Verified interactions and boundaries

- The new content-addressed body table compresses UTF-8 text once per SHA-256, preserves document-version metadata separately, and decompresses only selected rows. Existing repeated-Unicode-body regression passes with one unique body and a compact SQLite file.
- `Store.documents` filters both publication and observation clocks before ranking visible successful versions. The body observation clock requires batch `scraped_at`; a later body cannot inherit an earlier metadata collection timestamp. Compression does not bypass these gates.
- `audit.json` and case variants are rejected as the requested database basename before writes. Index files inside the resolved source tree are rejected; existing unrelated databases are protected. Index metadata retains an embedded audit.
- Cached extraction prevents repeat body fees across probe/recovery/window/watch while retaining per-query fees. Recovery exposure is recomputed from round-opening state and included in same-round source statistics.
- The source interval model uses sorted unique publication instants; mixed timezone ordering, fixed cutoff, absolute delta confirmation, contraction skip, cooldown and total/round budget regressions pass.
- Labels remain a separately accessed table. CLI prediction completes before evaluation obtains labels; comparison records proxy labels and fingerprints, conflicts abstain, and verified Brier is null. No price-derived support path was found.
- Report fields previously identified as unsafe are escaped; JSON script embedding escapes closing-script-sensitive characters. No new actionable report-injection finding was identified.
- Unconfigured real lexical support remains neutral. This validates the declared scheduling demonstration scope, not real forecasting accuracy or source exhaustion in an online service.

## Verification command

```powershell
Set-Location 'C:\Users\18899\Documents\ChatGPT\zl\patent_project'
& 'C:\Users\18899\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' test.py
```

All targeted reproductions used the same interpreter, `PYTHONPATH=src;tests`, and auto-cleaned temporary directories. No production archive, target index, or real-run outputs were touched.

## Additional re-review checks

- The CLI explicitly reconfigures stdout/stderr to UTF-8, and its new subprocess regression succeeds under `PYTHONIOENCODING=gbk` with Unicode characters outside GBK in the output path. The process exits zero and its output decodes as UTF-8.
- Compression, body observation clock, reserved audit filename, cache/read costs, same-round recovery exposure, cooldown, contraction and proxy-label isolation remain covered by the passing 50-test suite.
- Only this review report was edited during re-review. Implementation changes were made by the responsible agents.
