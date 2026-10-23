# Phase 12: frozen V5 development fact/admission diagnostic

Scope: 18 previously inspected development events. No model requests; no quality or held-out claim. V5 admission is unchanged.

## Counts

| Metric | Value |
|---|---:|
| selected_documents | 358 |
| extraction_failures | 2 |
| documents | 356 |
| validated_documents | 356 |
| tasks | 18 |
| directional_documents | 44 |
| directional_passes | 1 |
| directional_read | 43 |
| directional_admitted | 1 |
| directional_final | 1 |
| opt_in_v6_directional_passes | 2 |
| opt_in_v6_new_directional_passes | 1 |
| eligible_for_grouping | 0 |
| grouped_documents | 0 |
| group_count | 356 |
| weight_changes | 59 |

## Opt-in V6 evidence-backed change

V6 adds one newly passing directional document among these 44; admission and final evidence require engine replay. This is a development comparison, with the original support unchanged.

- 2354063 / `cc2515d881e47b41045a8936fd51ada9dc9a088045d7b5a05e47d35b80f1cff0`: proposal_submission; date witnesses ['May 13, 2026']; establishes_outcome=false.

> The Likud party of Prime Minister Benjamin Netanyahu submitted a proposal to dissolve the Israeli parliament on Wednesday, May 13, 2026, following threats of a coalition collapse.

## Decision

Historical V5 unchanged. Opt-in V6 adds only Israeli parliamentary dissolution and Kevin Warsh confirmation procedure contracts. Exact dated completed proposal submission is weak procedural context, never dissolution proof. Header-only dates and future/expected stages remain rejected. No broader normalization or missing-date relaxation is applied.

The conservative opt-in grouping requires all five nonempty elements in a bound quote, an exact complete event date, identical support and known source. Only whitespace/case, exact day formats and closed country aliases normalize. Missing fields, contradictory support, qualifiers and uncertain time remain distinct. Same-source duplicates stay in the audit and add zero weight; different source representatives use gamma by chronological rank.

Grouping runs on all validated documents within each task. Changed weights below compare lexical legacy identity with conservative identity at the frozen gamma; they are not prediction-score changes.

## V5 unsupported task contracts

| Market | Question | Directional docs |
|---|---|---:|
| 1439560 | Russia x Ukraine ceasefire by April 30, 2026? | 2 |
| 1706415 | Military action against Iran ends on April 25, 2026? | 0 |
| 1171663 | Russia x Ukraine ceasefire by June 30, 2026? | 0 |
| 1423716 | Will Elon Musk post 1000-1039 tweets in April 2026? | 0 |
| 1500754 | Will Kevin Warsh be confirmed as Fed Chair? | 10 |
| 1517836 | Trump announces end of military operations against Iran by June 30th? | 3 |
| 567687 | Russia x Ukraine ceasefire by end of 2026? | 0 |
| 2354003 | US announces new Iran agreement/ceasefire extension by June 30? | 1 |
| 2354044 | US x Iran diplomatic meeting by June 3, 2026? | 4 |
| 2354063 | Israeli parliament dissolved by July 31? | 11 |
| 1654956 | Will the Fed decrease interest rates by 50+ bps after the July 2026 meeting? | 0 |

## Blockers (a row can have several)

| Blocker | Documents |
|---|---:|
| event_time_unknown | 36 |
| unsupported_task | 31 |
| subject_unresolved_or_mismatch | 31 |
| action_unresolved_or_mismatch | 23 |
| object_unresolved_or_mismatch | 23 |
| object_mismatch | 10 |
| action_relation_unresolved | 10 |
| forecast_or_market_basis | 2 |
| actor_not_grounded | 1 |

## Directional evidence: all 44 rows

### 1439560 / 32675d705e97a2b24674471a11f41e754bf1c97d35205d302f08033078cd5f7c

Russia x Ukraine ceasefire by April 30, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260417\runs\1439560\extraction-trace.json`; source ID `publisher:the kyiv independent`.
- Pass/read/admitted/final: False/True/False/False; support `[-1, 1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['unsupported_task', 'subject_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> The following day, the Kremlin rejected the initiative.

Frozen elements: `{"subject": "Russia and Ukraine", "action": "rejected a proposed temporary Easter ceasefire", "object": "Ukraine's Easter ceasefire proposal", "time": "March 31 (following Zelensky's March 30 statement)", "location": "Moscow/Kyiv"}`.

### 1439560 / af075763dcc0015fb59329cba038ad1377b9eb491730f289d22b49fa3c960f59

Russia x Ukraine ceasefire by April 30, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260417\runs\1439560\extraction-trace.json`; source ID `publisher:reuters`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['unsupported_task', 'subject_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: action_not_in_bound_quote, object_missing_or_unknown, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> As both Ukraine and Russia celebrate Orthodox Easter this weekend, the countries have agreed on a short, 32-hour ceasefire to mark the holiday.

Frozen elements: `{"subject": "Ukraine and Russia", "action": "agreed on a short, 32-hour ceasefire to mark Orthodox Easter", "time": "April 11, 2026 (ceasefire from 4 p.m. Saturday to midnight Sunday)", "location": "Ukraine/Russia"}`.

### 669662 / bbbd6db6387f0948aa306df6e0678cd162c2c70e26e91c0e8a178bc6e56f0f6a

Will there be no change in Fed interest rates after the April 2026 meeting?

- Frozen source: `artifacts\semantic-v5-independent-20260417\runs\669662\extraction-trace.json`; source ID `publisher:foreignpolicyjournal.com`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['actor_not_grounded'].
- Admission blockers: actor_not_grounded.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_missing_or_unknown.

> His remarks were widely interpreted as a strong signal of a hold at the April meeting.

Frozen elements: `{"subject": "Federal Reserve", "action": "maintain_rate", "object": "federal funds rate", "time": "April 2026"}`.

### 669662 / dc54e20dfd1741536ee2556eeec785efd57b96fcc013acfc22e73cb7540dcbbc

Will there be no change in Fed interest rates after the April 2026 meeting?

- Frozen source: `artifacts\semantic-v5-independent-20260417\runs\669662\extraction-trace.json`; source ID `publisher:investopedia`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['forecast_or_market_basis', 'event_time_unknown'].
- Admission blockers: forecast_or_market_basis, event_time_unknown.
- Grouping blockers: action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> Federal Reserve officials are widely expected to hold the central bank's key interest rate steady at their next meeting April 28 to 29.

Frozen elements: `{"subject": "Federal Reserve", "action": "hold key interest rate steady", "object": "federal funds rate", "time": "April 28-29, 2026 meeting", "location": "United States"}`.

### 669662 / d60cdd1d4cb0d707f6de38ed37e2e0deda8b044a7aa747180499535c90c7a285

Will there be no change in Fed interest rates after the April 2026 meeting?

- Frozen source: `artifacts\semantic-v5-independent-20260417\runs\669662\extraction-trace.json`; source ID `publisher:tradingkey`.
- Pass/read/admitted/final: True/True/True/True; support `[1, 0]` unchanged.
- Opt-in V6 passes: True; stage: None; blockers: [].
- Admission blockers: none.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> Bessent specifically affirmed the Fed's decision to hold steady under the current circumstances.

Frozen elements: `{"subject": "Federal Reserve", "action": "hold steady on interest rates", "object": "federal funds rate", "time": "April 2026", "location": "Washington"}`.

### 1500754 / a4d6d53bcfacb89637978ea45b65a8e3c558ff83f6155d68743d1b89be8a4ebd

Will Kevin Warsh be confirmed as Fed Chair?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1500754\extraction-trace.json`; source ID `publisher:cnbc`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'speculative_conditional_or_negated_statement', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> Warsh's confirmation cleared a key hurdle last week when U.S. Attorney Jeanine Pirro of Washington, D.C., referred an investigation into the renovation at Fed headquarters over to the central bank's inspector general, seemingly ending a criminal probe. A Senate Banking Committee vote is scheduled Wednesday.

Frozen elements: `{"subject": "Kevin Warsh", "action": "nominee for Fed Chair; Senate Banking Committee vote scheduled", "object": "Federal Reserve Chair confirmation process", "time": "2026, Senate Banking Committee vote scheduled Wednesday", "location": "United States Senate"}`.

### 1500754 / f5cd0bddd81fcb0973e5f32ec8593101aaf0d3aa1f892b8c4bd4ef03d15180c9

Will Kevin Warsh be confirmed as Fed Chair?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1500754\extraction-trace.json`; source ID `publisher:reuters`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'speculative_conditional_or_negated_statement', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: action_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote.

> The Senate Banking Committee is expected on Wednesday to advance Kevin Warsh's nomination as Federal Reserve Chair to the full Senate, with a vote now set for 10 a.m. EDT (1400 GMT).

Frozen elements: `{"subject": "Kevin Warsh", "action": "Senate Banking Committee expected to advance nomination", "object": "nomination as Federal Reserve Chair to the full Senate", "time": "Wednesday, April 29, 2026 (vote set for 10 a.m. EDT)", "location": "Senate Banking Committee"}`.

### 1500754 / 451beb2880462525f9fe5e07c845468ec4f7d68479e16657f8a5c1412d641090

Will Kevin Warsh be confirmed as Fed Chair?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1500754\extraction-trace.json`; source ID `publisher:the new yorker`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'speculative_conditional_or_negated_statement', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: quote_has_qualification_or_negation, subject_not_in_bound_quote, action_not_in_bound_quote, object_missing_or_unknown, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> On Sunday, the Republican senator Thom Tillis, of North Carolina, who had blocked Warsh’s nomination in protest at the Administration abusing its power to go after Powell and the Fed, said that he would allow it to proceed, opening the way for Warsh to be confirmed before Powell’s term ends in May.

Frozen elements: `{"subject": "Kevin Warsh", "action": "nomination to proceed toward Senate confirmation as Fed Chair", "time": "before Powell's term ends in May", "location": "U.S. Senate"}`.

### 1500754 / 31daaf9b6ba8264503f3ca7fd2da5d50fd11e1d92dbec24085b25fb161645ab2

Will Kevin Warsh be confirmed as Fed Chair?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1500754\extraction-trace.json`; source ID `publisher:usa today`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> The decision probably clears the way for Warsh's confirmation: Tillis confirmed in a social media post April 26 that he looks forward to supporting him.

Frozen elements: `{"subject": "Kevin Warsh", "action": "nominated for and seeking Senate confirmation as", "object": "Chair of the Federal Reserve", "time": "April 2026", "location": "United States Senate"}`.

### 1500754 / c7d678c0b5e798cbb1c221589872785cb0cb285edd54d320f480c8b57bc69eaa

Will Kevin Warsh be confirmed as Fed Chair?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1500754\extraction-trace.json`; source ID `publisher:barron's`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_missing_or_unknown.

> Warsh Path to Fed Chair Clear as Sen. Tillis Says He Won’t Block Committee Vote

Frozen elements: `{"subject": "Kevin Warsh", "action": "path to Fed Chair cleared", "object": "Senate committee vote", "time": "current (as of excerpt)"}`.

### 1500754 / 8bd43807f376e9d5c701504494be925d49e424264fb3cdbe51ac40ad9f50af3f

Will Kevin Warsh be confirmed as Fed Chair?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1500754\extraction-trace.json`; source ID `publisher:upi.com`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'speculative_conditional_or_negated_statement', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> U.S. Sen. Thom Tillis, R-N.C., said on Sunday that he will end his blockade of Kevin Warsh's confirmation as Federal Reserve chair after the Department of Justice ended its investigation into current chair Jerome Powell.

Frozen elements: `{"subject": "Thom Tillis", "action": "said he will end his blockade and vote to confirm", "object": "Kevin Warsh as Federal Reserve chair", "time": "April 26 (Sunday)", "location": "United States Senate"}`.

### 1500754 / 9bc3a786058a361ef7fe93df66ccb4eef17fb1b4d398be22ecc33839b5db14f8

Will Kevin Warsh be confirmed as Fed Chair?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1500754\extraction-trace.json`; source ID `publisher:ap news`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> The announcement by Sen. Thom Tillis of North Carolina removes a big hurdle to Trump’s effort to install Kevin Warsh, a former high-ranking Fed official, in the job in place of Jerome Powell

Frozen elements: `{"subject": "Kevin Warsh", "action": "Senate committee scheduled to vote on nomination; Tillis dropping opposition to confirmation", "object": "confirmation as Fed Chair", "time": "Sunday announcement; committee vote Wednesday; Powell term ends May 15", "location": "Washington"}`.

### 1500754 / 39402834d9f25df8158aa673b612b6bf02ef7dde1ff36307e8bb67f376fff545

Will Kevin Warsh be confirmed as Fed Chair?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1500754\extraction-trace.json`; source ID `publisher:new york post`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'speculative_conditional_or_negated_statement', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch.
- Grouping blockers: quote_has_qualification_or_negation, action_not_in_bound_quote, object_not_in_bound_quote, time_not_in_bound_quote, location_not_in_bound_quote.

> Republican Senator Thom Tillis on Sunday said he would allow Senate confirmation of Federal Reserve chair nominee Kevin Warsh to go forward

Frozen elements: `{"subject": "Kevin Warsh", "action": "advance confirmation", "object": "Fed chair nominee", "time": "April 26, 2026", "location": "United States Senate"}`.

### 1500754 / e3f9d32b577d2b19de5a5aa875d05c4c69c065c4cb7e783616164c6544abbe12

Will Kevin Warsh be confirmed as Fed Chair?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1500754\extraction-trace.json`; source ID `publisher:nbc news`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> Sen. Thom Tillis drops blockade of Trump's Fed chair nominee, clearing path for Warsh's confirmation

Frozen elements: `{"subject": "Kevin Warsh", "action": "Sen. Thom Tillis drops blockade of nomination, clearing path for confirmation", "object": "Fed chair nominee", "time": "Sunday before 2026-04-30", "location": "U.S. Senate"}`.

### 1500754 / 328e57ff8a7d4a96c1fe90d14a03371ad4ff4135e9f3d4fd985e6df1b02a056c

Will Kevin Warsh be confirmed as Fed Chair?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1500754\extraction-trace.json`; source ID `publisher:fortune`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'speculative_conditional_or_negated_statement', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> The committee on Saturday said it planned to vote Wednesday on Warsh’s nomination.

Frozen elements: `{"subject": "Kevin Warsh", "action": "nomination advanced toward Senate confirmation", "object": "Chair of the Federal Reserve", "time": "Sunday announcement; committee vote planned Wednesday", "location": "U.S. Senate Banking Committee"}`.

### 1517836 / 3e40b6da32e00a79c1e070af05a1bdb0f3ff1844f17f723e51868cb6d23aef30

Trump announces end of military operations against Iran by June 30th?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1517836\extraction-trace.json`; source ID `publisher:ukranews.com`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['unsupported_task', 'subject_unresolved_or_mismatch', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: time_not_exact_day, time_not_in_bound_quote, location_missing_or_unknown.

> US President Donald Trump has announced that the military operation against Iran is officially over.

Frozen elements: `{"subject": "Donald Trump", "action": "announced that the military operation against Iran is officially over", "object": "military operation against Iran", "time": "before 2026-04-30"}`.

### 1517836 / ad63d536b130774c0f01e2cd12730792a24c39f7cfa5244c31ae331dda4e1a35

Trump announces end of military operations against Iran by June 30th?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1517836\extraction-trace.json`; source ID `publisher:bankingnews`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['unsupported_task', 'subject_unresolved_or_mismatch', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> US President Trump has announced the end of the military operation against Iran, according to Fox News reports.

Frozen elements: `{"subject": "President Trump", "action": "announced the end of the military operation against Iran", "object": "military operations against Iran", "time": "reported around April 2026, ahead of talks on April 15-16, 2026", "location": "Islamabad, Pakistan (planned talks)"}`.

### 1517836 / a373529b0fb6a54eb40c566ec1c8207e1e2c1fec5e25fda2667c81e5a6d38f82

Trump announces end of military operations against Iran by June 30th?

- Frozen source: `artifacts\semantic-v5-independent-20260430\runs\1517836\extraction-trace.json`; source ID `publisher:rbc-ukraine`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['unsupported_task', 'subject_unresolved_or_mismatch', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_missing_or_unknown.

> US President Donald Trump has declared the completion of the military operation against the Iranian regime, according to the Instagram account of Fox News journalist Maria Bartiromo.

Frozen elements: `{"subject": "US President Donald Trump", "action": "declared the completion of the military operation against the Iranian regime", "object": "military operation against Iran", "time": "reported interview, before April 16, 2026"}`.

### 2354003 / adce67e49f6f545202d8b4daf232d9553469b75d88843644d4e23771bf8978b1

US announces new Iran agreement/ceasefire extension by June 30?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354003\extraction-trace.json`; source ID `publisher:tradingkey`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['unsupported_task', 'subject_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_missing_or_unknown, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> U.S. President Trump announced a preliminary agreement with Iran, including a 60-day ceasefire extension and reopening the Strait of Hormuz, pending final review.

Frozen elements: `{"subject": "U.S. President Trump and U.S.-Iran negotiators", "action": "announced a preliminary agreement (Memorandum of Understanding) including a 60-day ceasefire extension and reopening of the Strait of Hormuz, pending Trump's final review; Trump said he will make a final ruling", "time": "Friday (reported in article, before 2026-05-31 cutoff)", "location": "United States / Iran"}`.

### 2354023 / 10b2baf0a0dc384f61b7cef176ce74fc97ee7401a323b551ec8a4764bd8fb153

Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by June 7, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354023\extraction-trace.json`; source ID `publisher:the jerusalem post`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['object_mismatch', 'action_relation_unresolved', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: object_mismatch, action_relation_unresolved, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: quote_has_qualification_or_negation, subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> Trump added that he will lift the US naval blockade on the Strait of Hormuz, adding that the strait "must be immediately open, no tolls, for unrestricted shipping traffic, in both directions."

Frozen elements: `{"subject": "Donald Trump", "action": "announced he will lift the US naval blockade on the Strait of Hormuz", "object": "US naval blockade of the Strait of Hormuz", "time": "Friday (reported)", "location": "White House Situation Room"}`.

### 2354023 / 45f732afcde526cca16fee097798677399a9a5d11ac4e8c32e2dbc740cb1bdd5

Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by June 7, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354023\extraction-trace.json`; source ID `publisher:türkiye today`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['object_mismatch', 'action_relation_unresolved', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: object_mismatch, action_relation_unresolved, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: quote_has_qualification_or_negation, subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> Hours earlier, Trump had signaled a significant shift, announcing on Truth Social that the U.S. naval blockade of Iranian shipping would be lifted, framing it as the first tangible step toward an agreement to end the conflict.

Frozen elements: `{"subject": "Donald Trump", "action": "announced on Truth Social that the U.S. naval blockade of Iranian shipping would be lifted", "object": "U.S. naval blockade of Iranian shipping in the Strait of Hormuz", "time": "Saturday, before the cutoff (reported alongside a Saturday alert)", "location": "Strait of Hormuz / Truth Social"}`.

### 2354023 / ba807ef3796a9727ae1d7287ccd04ddfd78669b73c8fa87a05909e532b88856a

Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by June 7, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354023\extraction-trace.json`; source ID `publisher:i̇lke haber ajansı`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['object_mismatch', 'action_relation_unresolved', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: object_mismatch, action_relation_unresolved, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote.

> US President Donald Trump announced on Friday that Washington intends to lift its naval blockade of the Strait of Hormuz

Frozen elements: `{"subject": "Donald Trump", "action": "announced intention to lift naval blockade of the Strait of Hormuz and remove mines", "object": "US naval blockade of the Strait of Hormuz", "time": "Friday (reported)", "location": "Strait of Hormuz"}`.

### 2354023 / 39d188141fa313505c32288d24e51df5b5ae6cbb0bdc1cc423331f7521e1ecbd

Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by June 7, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354023\extraction-trace.json`; source ID `publisher:times now`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['object_mismatch', 'action_relation_unresolved', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: object_mismatch, action_relation_unresolved, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: quote_has_qualification_or_negation, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> US President Donald Trump announced Friday that the United States would lift the naval blockade imposed on Iranian ports last month, a major development that could open the door to a broader agreement between Washington and Tehran.

Frozen elements: `{"subject": "Donald Trump", "action": "announced the United States would lift the naval blockade imposed on Iranian ports", "object": "US naval blockade of Iranian ports / Strait of Hormuz", "time": "Friday (announcement reported in excerpt)", "location": "Strait of Hormuz"}`.

### 2354023 / 051f5cd50ad105055773abdc8ef0081ceb58bf6226c4d82b0334d8a5544329b1

Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by June 7, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354023\extraction-trace.json`; source ID `publisher:the war zone`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['object_mismatch', 'action_relation_unresolved', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: object_mismatch, action_relation_unresolved, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> President Donald Trump on Friday announced he was lifting the U.S. blockade on Iranian ports enacted last month.

Frozen elements: `{"subject": "Donald Trump", "action": "announced he was lifting the U.S. blockade on Iranian ports", "object": "U.S. naval blockade on Iranian ports / Strait of Hormuz", "time": "Friday (before May 31, 2026)", "location": "Strait of Hormuz"}`.

### 2354023 / b54ef0a4fa90148d80a8cec4740f89dd694117a0ce04da59b4ca6d5e3374eb35

Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by June 7, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354023\extraction-trace.json`; source ID `publisher:the telegraph`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['object_mismatch', 'action_relation_unresolved', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: object_mismatch, action_relation_unresolved, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> Donald Trump has announced that he will lift the US blockade of Iranian shipping in the Strait of Hormuz.

Frozen elements: `{"subject": "Donald Trump", "action": "announced he will lift the US blockade of Iranian shipping", "object": "the US naval blockade of the Strait of Hormuz", "time": "Friday (reported)", "location": "White House Situation Room / Truth Social"}`.

### 2354023 / c58d13430abe05bb3d4524ff4eb9de3fbe8a635a413e782f44190326ef436ed0

Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by June 7, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354023\extraction-trace.json`; source ID `publisher:شفق نيوز`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['object_mismatch', 'action_relation_unresolved', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: object_mismatch, action_relation_unresolved, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: quote_has_qualification_or_negation, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote.

> US President Donald Trump announced on Friday that Washington would lift the naval blockade in the Strait of Hormuz, noting that the strategic waterway must be reopened immediately without any transit fees.

Frozen elements: `{"subject": "Donald Trump", "action": "announced that Washington would lift the naval blockade in the Strait of Hormuz", "object": "US naval blockade of the Strait of Hormuz", "time": "Friday (reported before cutoff)", "location": "Washington"}`.

### 2354023 / 866cfa7faae975196864644492704c863b7cf90dffb7d6c8236a5ec4bacce1c3

Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by June 7, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354023\extraction-trace.json`; source ID `publisher:outlook india`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['object_mismatch', 'action_relation_unresolved', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: object_mismatch, action_relation_unresolved, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> President Donald Trump has declared that the U.S. naval blockade on the Strait of Hormuz will be lifted, potentially defusing a major flashpoint in the ongoing conflict with Iran.

Frozen elements: `{"subject": "Donald Trump", "action": "declared", "object": "the U.S. naval blockade on the Strait of Hormuz will be lifted", "time": "before 2026-05-31", "location": "Truth Social platform"}`.

### 2354023 / 732494db5b2b9435e4a33477bc1e98fc2412453d08334f79a517fc5899614236

Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by June 7, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354023\extraction-trace.json`; source ID `publisher:ctv news`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['object_mismatch', 'action_relation_unresolved', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: object_mismatch, action_relation_unresolved, action_unresolved_or_mismatch, object_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: quote_has_qualification_or_negation, subject_not_in_bound_quote, object_not_in_bound_quote, time_missing_or_unknown, location_not_in_bound_quote.

> Posted to Truth Social, Trump announced that the U.S. blockade ‘will now be lifted’ but did not confirm any date or if this is a part of a larger deal.

Frozen elements: `{"subject": "Donald Trump", "action": "announced", "object": "that the U.S. blockade of the Strait of Hormuz 'will now be lifted'", "location": "Strait of Hormuz"}`.

### 2354023 / 471aefe80d2f9129da7ed4437b45e9a6176b41107cdc03b530fe51152f128a6a

Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by June 7, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354023\extraction-trace.json`; source ID `publisher:arabcanadanews.ca`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['object_mismatch', 'action_relation_unresolved', 'action_unresolved_or_mismatch', 'object_unresolved_or_mismatch'].
- Admission blockers: object_mismatch, action_relation_unresolved, action_unresolved_or_mismatch, object_unresolved_or_mismatch.
- Grouping blockers: action_not_in_bound_quote, object_not_in_bound_quote, time_not_in_bound_quote, location_not_in_bound_quote.

> US President Donald Trump announced that the US restrictions on navigation in the Strait of Hormuz "will be lifted now,"

Frozen elements: `{"subject": "Donald Trump", "action": "announced that US restrictions on navigation in the Strait of Hormuz will be lifted now", "object": "US restrictions/blockade on navigation in the Strait of Hormuz", "time": "May 29, 2026", "location": "Washington"}`.

### 2354044 / 017532db0e920e094e7b126037c961c2a566978195778fc262a52f7c9d64d65b

US x Iran diplomatic meeting by June 3, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354044\extraction-trace.json`; source ID `publisher:ynetnews`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['unsupported_task', 'subject_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> The United States and Iran are close to agreeing on a memorandum of understanding aimed at ending the war, according to regional officials and a diplomat cited by AP

Frozen elements: `{"subject": "United States and Iran", "action": "reviewing a Pakistan-prepared draft memorandum of understanding and negotiating through mediators", "object": "memorandum of understanding to end the war", "time": "Saturday, with decision expected within 48 hours", "location": "Tehran and regional mediation"}`.

### 2354044 / 1e859efae8cd3e9bf322dcd3b38ab67ed8d9f3401cf5d8ab9e9c4b26037ba87c

US x Iran diplomatic meeting by June 3, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354044\extraction-trace.json`; source ID `publisher:cnn`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['unsupported_task', 'subject_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: quote_has_qualification_or_negation, subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote.

> US and Iranian officials suggested that they may be closer to reaching a framework agreement to end the war after mediators from Qatar and Pakistan held talks in Tehran on Saturday.

Frozen elements: `{"subject": "United States and Iran negotiations", "action": "held talks through mediators and exchanged a memorandum of understanding proposal", "object": "framework agreement to end hostilities and reopen Strait of Hormuz", "time": "Saturday and preceding days before the report", "location": "Tehran"}`.

### 2354044 / 4648e5c9bf793c4f9ab8ded583cec075b679e9611e1d5a9cc23e5406f074ab70

US x Iran diplomatic meeting by June 3, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354044\extraction-trace.json`; source ID `publisher:radio free europe/radio liberty`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['unsupported_task', 'subject_unresolved_or_mismatch'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> what is important was that the two sides kept speaking indirectly through Pakistani mediators, but also, perhaps more recently, through the Qataris as well.

Frozen elements: `{"subject": "United States and Iran", "action": "indirect negotiations", "object": "diplomatic talks via Pakistani and Qatari mediators", "time": "as of May 2026", "location": "Islamabad; Miami"}`.

### 2354044 / 77965031a4cac6f88ef86be8274a8eea8470eee0aec8053be00e1db0589e0907

US x Iran diplomatic meeting by June 3, 2026?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354044\extraction-trace.json`; source ID `publisher:cbs news`.
- Pass/read/admitted/final: False/False/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['unsupported_task', 'subject_unresolved_or_mismatch', 'event_time_unknown'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote.

> Mr. over the weekend to send senior envoys to Pakistan for a second round of direct talks with Iranian officials, insisting his administration has "all the cards"

Frozen elements: `{"subject": "United States and Iran", "action": "planned second round of direct talks", "object": "senior envoys to Pakistan", "time": "over the weekend (before May 2026 cutoff)", "location": "Pakistan"}`.

### 2354063 / 5c34d7ef598d79fbca0f5cad2c8935ca72211fd4d3872c998a86081387d2a719

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:the media line`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: preliminary_approval; blockers: ['event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> the Knesset dissolution bill passed in the preliminary vote, and the train left the station

Frozen elements: `{"subject": "Israeli Knesset", "action": "coalition advanced a dissolution bill in a preliminary vote", "object": "Knesset dissolution legislation", "time": "Wednesday", "location": "Knesset, Israel"}`.

### 2354063 / 3250b8d600752b8aff3b473b1978d02d2f244d7bba0aaac7289c38ec824061c8

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:pakistan today`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: preliminary_approval; blockers: ['event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_missing_or_unknown, time_not_in_bound_quote.

> Israel’s parliament has given initial approval to a bill to dissolve the Knesset, moving the country closer to a snap election.

Frozen elements: `{"subject": "Israeli Knesset", "action": "gave initial approval to a bill to dissolve the Knesset", "time": "May 20, 2026", "location": "Israel"}`.

### 2354063 / eccc1e69dc9ae316fe1c1fe873cd731003215210af5b3d65af17d462aa405ba6

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:www.israelhayom.com`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'speculative_conditional_or_negated_statement', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, forecast_or_market_basis, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: action_not_in_bound_quote, object_missing_or_unknown, time_not_exact_day, location_not_in_bound_quote.

> The Knesset is expected to vote Wednesday in a preliminary reading on dissolving itself, formally launching the process of moving up the upcoming Israeli legislative elections.

Frozen elements: `{"subject": "Knesset", "action": "expected to vote in a preliminary reading on dissolving itself", "time": "Wednesday", "location": "Israel"}`.

### 2354063 / b49d589c6bc29644c11b8e3ff10a610c74b8538aab43ecc473ad44aa3e91c0cd

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:dailyhunt`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, location_missing_or_unknown.

> The coalition led by Israeli Prime Minister Benjamin Netanyahu on Wednesday submitted a bill to dissolve parliament, taking the first formal step toward triggering fresh national elections later this year.

Frozen elements: `{"subject": "Netanyahu-led coalition", "action": "submitted a bill to dissolve parliament", "object": "parliament (Knesset)", "time": "Wednesday"}`.

### 2354063 / 18d9038a830a3681cd77f4e8bd4d0638da2514abb497b4b0bfa3a66f70984c09

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:the straits times`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'speculative_conditional_or_negated_statement', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch.
- Grouping blockers: quote_has_qualification_or_negation, subject_not_in_bound_quote, action_not_in_bound_quote, object_not_in_bound_quote, time_not_in_bound_quote.

> Israel’s ruling coalition has submitted a proposal to dissolve the country’s Parliament, paving the way for early elections, the party of Prime Minister Benjamin Netanyahu said on May 13.

Frozen elements: `{"subject": "Israel's ruling coalition", "action": "submitted a proposal to dissolve Parliament", "object": "the 25th Knesset", "time": "May 13, 2026", "location": "Israel"}`.

### 2354063 / 359a9fe1755a1016523e0d684ae230b219f98aef808ae3ea0e0bf6f6d81e68a8

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:latin times`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, object_not_in_bound_quote, time_not_exact_day, time_not_in_bound_quote.

> Israeli Prime Minister Benjamin Netanyahu moved one step closer to a possible early election after coalition leaders submitted a bill to dissolve the Knesset, Israel's parliament, amid growing fractures inside his right-wing government.

Frozen elements: `{"subject": "Israeli Knesset", "action": "coalition leaders submitted a bill to dissolve", "object": "Knesset dissolution bill", "time": "reported as potentially triggering a parliamentary vote as early as next week", "location": "Israel"}`.

### 2354063 / 8ca1834a74a7c1088ac28a7e5398f8f26c247700ea2387e36013f407375f48a5

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:the national`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: proposal_submission; blockers: ['event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_missing_or_unknown, time_not_exact_day, time_not_in_bound_quote, location_not_in_bound_quote.

> Israeli Prime Minister Benjamin Netanyahu's coalition has submitted a bill to dissolve the Knesset and trigger elections amid an ultra-Orthodox conscription crisis.

Frozen elements: `{"subject": "Israeli Knesset", "action": "coalition submits bill to dissolve parliament and trigger elections", "time": "current reporting period", "location": "Israel"}`.

### 2354063 / cc2515d881e47b41045a8936fd51ada9dc9a088045d7b5a05e47d35b80f1cff0

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:asatunews.co.id`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: True; stage: proposal_submission; blockers: [].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: object_not_in_bound_quote, time_not_exact_day, location_not_in_bound_quote.

> The Likud party of Prime Minister Benjamin Netanyahu submitted a proposal to dissolve the Israeli parliament on Wednesday, May 13, 2026, following threats of a coalition collapse.

Frozen elements: `{"subject": "Likud party of Prime Minister Benjamin Netanyahu", "action": "submitted a proposal to dissolve the Israeli parliament", "object": "the 25th Knesset", "time": "Wednesday, May 13, 2026", "location": "Israel"}`.

### 2354063 / 1d9bb1a42868270621902454a37511830518483737d118689134dd922badba3f

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:the times of india`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, action_not_in_bound_quote, object_missing_or_unknown, time_not_exact_day, time_not_in_bound_quote.

> Israel's ruling coalition on Wednesday submitted a proposal to dissolve parliament to pave the way for early elections

Frozen elements: `{"subject": "Israeli Knesset (parliament)", "action": "ruling coalition submitted a proposal to dissolve parliament to pave the way for early elections", "time": "Wednesday (reported); bill could be voted on May 20; elections possibly from third week of August", "location": "Israel"}`.

### 2354063 / 29fed178ad53c85c2986536cb1d4152b396bc8197b87d403004a5cc602394b37

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:le monde.fr`.
- Pass/read/admitted/final: False/True/False/False; support `[1, 0]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: time_not_exact_day, location_missing_or_unknown.

> Israel ruling coalition proposes dissolving parliament for early elections

Frozen elements: `{"subject": "Israel ruling coalition", "action": "proposes dissolving parliament", "object": "parliament", "time": "early elections"}`.

### 2354063 / e856cf3a0d897971b43eadbbde8ac1fa7ad42effb7dd4b28f25c21b66c175ddf

Israeli parliament dissolved by July 31?

- Frozen source: `artifacts\semantic-v5-independent-20260531\runs\2354063\extraction-trace.json`; source ID `publisher:the guardian`.
- Pass/read/admitted/final: False/True/False/False; support `[1, -1]` unchanged.
- Opt-in V6 passes: False; stage: None; blockers: ['completed_target_procedure_not_grounded', 'event_time_unknown', 'event_date_not_grounded_in_event_statement'].
- Admission blockers: unsupported_task, subject_unresolved_or_mismatch, event_time_unknown.
- Grouping blockers: subject_not_in_bound_quote, object_missing_or_unknown, time_not_exact_day, time_not_in_bound_quote.

> Israel’s ruling coalition has submitted a proposal to dissolve parliament to pave the way for early elections

Frozen elements: `{"subject": "Israel's ruling coalition", "action": "submitted a proposal to dissolve parliament to pave the way for early elections", "time": "Wednesday (reported)", "location": "Israel"}`.

## Limitations

- Lexical five-element grounding is stricter than model extraction and does not establish truth.
- Distinct source IDs do not establish independent reporting or remove cross-source syndication.
- Same-source duplicate zero weighting only applies within a fully grounded matching group; incomplete facts remain separate.
- This diagnostic does not establish predictive quality, real monetary savings or held-out generalization.
- Historical summary contains labels; this script accesses only the directional index and computes no label-based quantity.
- Operator initial broad summary read exposed embedded labels before projection; no label values informed the policies or this report.

Exact source SHA-256 hashes, raw evidence, grounding witnesses, matching traces and per-task group counts are in `phase12-fact-diagnostic.json`.
