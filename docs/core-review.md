# Core independent review

Reviewed 2026-10-22 against `docs/design.md` and implementation plan Task 2. Scope: `core.py`, `models.py`, `evidence.py`, `engine.py` and their three test modules. No implementation files changed by this review. Line references below describe the reviewed snapshot, before fixes.

## Verdict

**Specification compliance: changes required.** The main equations and cutoff checks match the agreed design, but cross-phase duplicate reading charges violate budget semantics. Timestamp ordering must use instants, and source exposure must include recovery searches in the same round.

**Code quality: changes required before delivery.** The standard-library separation is appropriate and the scoped 19 tests pass. Existing duplicate coverage only checks unique exported evidence, so it misses repeated paid reads. Configuration validation also accepts a string as an enabled boolean feature.

These verdicts concern this snapshot, not subsequent fixes or the unreviewed CLI/data implementation.

## Findings

### P1 — One document is read and charged repeatedly across retrieval phases

Location: `src/dynamic_retrieval/engine.py:91-105` (`attempted[(kind, source)]`), callers at 119-127 and 180.

The cursor is scoped to query kind. A document discovered by a transition probe is read again in recovery, again by the ordinary window, and again by slow/watch search. `known` and `admitted_ids` prevent duplicate exported rows and silence resets, but each repetition still pays `read_cost`, consumes the budget and increases effective search coverage. This changes both comparisons and exhaustion behavior. Parent adjudication: separate retrieval actions and their request costs are deliberate; repeated cached body-reading charges are the defect.

Reproduction: use `tests/test_engine.py` helpers with one annotated `document('old', '2026-06-12')` and `EngineTests().config()`. Reviewed output:

```text
round 1: retrieved_ids=['old', 'old'], spent=2.85, action=expand
round 2: retrieved_ids=['old'],        spent=1.4,  action=contract
round 3: retrieved_ids=['old'],        spent=1.4,  action=contract
```

Suggested acceptance check: one global paid-read/extraction identity per selected URL/version. Moving a known probe into the window must still mark it recovered and update current-round probabilities without another reading charge. Distinguish that promotion from discovering a new document. Query requests may still have their stated empty-request cost.

### P2 — Raw timestamp string ordering selects the wrong URL version and fact rank

Locations: `src/dynamic_retrieval/engine.py:35-44`; `src/dynamic_retrieval/core.py:31`.

Both functions compare ISO timestamp strings, although the public engine accepts any timezone-aware ISO representation. Two strings with different offsets do not sort by their actual instants. The version selector can discard the latest eligible text, and the weight assignment can favor a later fact instead of the earliest one. UTC-normalized adapter output avoids this in that path, but the engine's documented standalone interface and annotation/demo inputs are affected.

Reproduction: two otherwise eligible records sharing a URL, with IDs `early` and `late` and `observed_at` values respectively:

```text
early: 2026-06-19T10:00:00+14:00 = 2026-06-18T20:00:00Z
late:  2026-06-19T01:00:00+00:00 = 2026-06-19T01:00:00Z
```

`run(..., Config(mode='fixed', rounds=1), ...)` exports `early`, but must export `late`. Giving the same timestamps as `published_at` to two same-fact rows produces `{'late': 1.0, 'early': 0.5}` from `independent_weights(rows, .5)`; the expected ranks are reversed. Normalize to UTC or compare parsed instants, retaining deterministic source/ID ties.

### P2 — Recovery requests are missing from same-round source exposure

Locations in original snapshot: `src/dynamic_retrieval/engine.py:138-146` and `180-183`.

The source exposure clock and coverage-adjusted silence are updated before recovery. The later call to `update_sources()` recalculates intervals/phi only. A source first queried during recovery therefore spends budget while retaining zero observed days, and a source without a fresh result gets no effective-silence increment for that recovery query. Future source rates use an undercounted exposure denominator. This violates same-round source-state recalculation.

Minimal reproduction: sources `0` through `6` each have one annotated `Alice` document published June 14; sources `0` and `1` additionally have one June 18 document. Cutoff June 20; target `{'subject':'alice'}`; all support `[1,-1]`. Set `rounds=1,total_budget=100,round_budget=15.5,initial_window_days=5,min_window_days=2,earliest_days=30,band_days=10,grid_days=10,band_fraction=.1,recovery_fraction=.7,low_loss=0,high_loss=.1,stable_distance=0`. Round 1 expands. Source `5` spends 1.2, has new_count=1 but observed_days=0. Source `6` spends .2, has observed_days=0 and silence=0, although coverage(.2,2) is approximately .09516. The latter query is empty, so it must not reset silence; it should advance covered silence. Finalize each source once after all searches, or adjust additional coverage without double-counting elapsed time.

### P2 — String boolean silently enables optional behavior

Location: `src/dynamic_retrieval/models.py:50-77`; consumed at `engine.py:192`.

`Config.from_dict({'enable_uncertainty_expansion': 'false'})` succeeds and stores a truthy string, thereby enabling uncertainty expansion and source inclusion. A JSON configuration typo can silently change the selected embodiment. Require `type(value) is bool` for this field. Numeric fields also currently accept booleans and reject some wrong types with incidental `TypeError`; consistent public-boundary type validation would make failures clearer, but that is secondary to the silent boolean switch.

## Independently verified behavior

- Scoped command: bundled Python with `PYTHONPATH=src;tests`, `python -m unittest test_core test_engine test_evidence -v`: **19/19 pass**.
- Equations checked directly against the design: typed target intersection, `[1,.5,.25]` duplicate ranks for normalized UTC fixtures, weighted support then stable softmax, exponential coverage, smoothed survival ratio and maximum-gap guard, transition decay, normalized loss, minimum-source/absolute-delta stop gate. No pure-equation discrepancy found for valid normalized inputs.
- Basic mode independently ranks window/band while enhanced shares the full fact pool. The initial written design did not state this exception, but the parent confirmed it deliberately represents patent embodiment 1 and will clarify the design. It is not an implementation finding after that adjudication.
- Future publication and future observation/version inputs are excluded before retrieval. Virtual round time never changes cutoff eligibility. Mixed-offset version ordering is wrong, but did not admit a post-cutoff version.
- Recovery updates probabilities and volume in the same round in the existing recovery fixture. Recovery cost remains within the total/round caps in the tested cases. Review did not find a budget overspend path; repeat reads instead waste valid budget.
- An additional 500 seeded random fixtures (seed 42; all three modes; 0-10 sources; total budgets .01-100 and round budgets .01-25) passed no-crash, total/round budget, nonnegative remaining, and normalized-probability assertions. These smoke probes ran while the parent began applying review fixes; they are additional engineering coverage, not proof that the open findings were fixed.
- The recovery fixture expands at round 1 and again at round 5 with confirmation_rounds=3; it does not expand during the intervening cooldown. Contraction rounds skip convergence and clear confirmation history.
- Source revival probe: with low source-exhaustion thresholds and multiple unread relevant records, a source becomes inactive, later gains a new record under watch, and resets silence/confirmations with `active=True` and phi=0. Repeated records do not reset `last_new_round`. The cross-phase read issue still distorts coverage before revival.
- Empty pool in all three modes: no crash, uniform `[.5,.5]`, zero spending and zero supporting evidence. Default enhanced stops after shrinking to minimum and reports `evidence_converged`; basic/fixed reach round limit. The zero-source enhanced stop is the explicitly tested vacuous minimum in `test_core.py:52`, not treated as an unintended crash or nonuniform prediction.
- Default unconfigured lexical extraction abstains with `[0,0]`; configured regex/annotation paths are explicit. No price or evaluation label is used in support calculation. Extraction exports method/version and a quote.
- Full discovery was also attempted while the parent was developing Task 3: all 25 discovered runnable tests passed; only `test_cli` import failed because `dynamic_retrieval.report` did not yet exist. This is recorded as concurrent incomplete work, not a core regression.

## Missing regression coverage

Add focused tests for global paid-read uniqueness and promotion without charging, timezone-normalized version/rank ordering, recovery-only source exposure and silence, and strict boolean config validation. Existing tests named `prevents_duplicates` only compare final row IDs and therefore do not verify the retrieval invariant.

## Re-review after fixes — 2026-10-22

**Latest scoped verdict: PASS for specification compliance and code quality; all four review findings are closed.** This supersedes the original snapshot verdict above. The original findings and reproductions remain as the audit history. The basic-versus-enhanced fact-clustering distinction is the deliberately adjudicated patent embodiment distinction.

Reviewed the updated `core.py`, `models.py`, `engine.py`, `evidence.py` and the three scoped test modules. Ran only `python -m unittest test_core test_engine test_evidence -v` with bundled Python and `PYTHONPATH=src;tests`: **25/25 pass** (8 core, 11 engine, 6 evidence). Did not run data/CLI discovery or another broad randomized pass during the concurrent storage work.

Independent targeted reproductions also pass:

- Cross-stage reads: the original single-old-document case still issues distinct retrieval actions and promotes the probe during recovery, updates same-round probability above .9, and performs exactly one paid body read. Round costs changed from `[2.85,1.4,1.4,.4,.85]` to `[1.85,.4,.4,.4,.85]`, retaining request and recovery movement costs.
- UTC ordering: the original mixed-offset URL fixture selects `late`; independent duplicate weighting assigns `early:1, late:.5`. Engine normalizes accepted publication/observation timestamps and ranks versions using parsed instants; core ranks publication instants.
- Recovery-only exposure: replayed the seven-source case and additionally placed source `6`'s only document outside the recovery range. Its empty recovery request spends .2, records exactly 1 observed day and covered silence `0.09516258196404043 = coverage(.2,2)`. The round-opening snapshot prevents double advancement when finalization runs twice.
- Strict config boundary: string `enable_uncertainty_expansion='false'`, boolean numeric `query_cost=True` / `epsilon=True`, and string numeric `total_budget='2'` all raise `ValueError`.
- Outcome order: configured positive support for outcomes `['No','Yes']` produces `[-1,1]`; annotation vectors remain explicitly aligned to the supplied outcome order.

No remaining actionable finding in this re-review scope. No implementation edits were made by the reviewer.
