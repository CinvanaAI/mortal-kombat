# How to read one historical battle

[Open the flow diagram](historical-flow.html) · [Explore the two recorded comparisons](index.html) · [Editable diagram source](historical-flow.json)

The diagram follows one comparison in the preserved Transcript Model Evaluator source. It connects the recorded task, ten examples, candidate responses, full rubric and whole-battle judgment. The exact source revision running during each historical battle remains unverified. The public source links below pin the preserved snapshot at commit `d0358512315b4ca4c16471e16061f64bf35541cb`.

| Diagram step | Inspect the recorded material | Mechanism in the preserved source |
| --- | --- | --- |
| Task + pair | [Task and model identities](index.html#task), [ten original examples](index.html#examples) | `_run_one_battle` loops through artifacts and assembles the task with each source text. [Read the artifact loop](https://github.com/CinvanaAI/transcript-model-evaluator/blob/d0358512315b4ca4c16471e16061f64bf35541cb/active_prompt/battle/service.py#L615). |
| Resolve A / B | [Both candidates' responses](index.html#examples) | `_resolve_candidate_outputs_for_artifact` checks the two persisted outputs, calls providers for missing candidates, and retains result or error envelopes. This happens inside a battle's artifact loop. [Read output resolution](https://github.com/CinvanaAI/transcript-model-evaluator/blob/d0358512315b4ca4c16471e16061f64bf35541cb/active_prompt/battle/service.py#L932). |
| Ten pairs + rubric | [Complete rubric](index.html#rubric), [all ten example pairs](index.html#examples) | `judge_input_payload` includes the task, model identities, all ten source/output pairs, candidate errors, category descriptions and weights. [Read bundle assembly](https://github.com/CinvanaAI/transcript-model-evaluator/blob/d0358512315b4ca4c16471e16061f64bf35541cb/active_prompt/battle/service.py#L749). |
| GPT-5.4 | [Recorded judge decision](index.html#decision) | One judge request receives the complete bundle. The response is parsed into a winner or disqualification, a short reason and confidence. [Read the request and parser path](https://github.com/CinvanaAI/transcript-model-evaluator/blob/d0358512315b4ca4c16471e16061f64bf35541cb/active_prompt/battle/service.py#L791). |
| Save record | [Decision and provenance](index.html#record) | The evaluator saves the battle's judge request, response, decision and failure fields, together with all ten candidate item records. [Read persistence](https://github.com/CinvanaAI/transcript-model-evaluator/blob/d0358512315b4ca4c16471e16061f64bf35541cb/active_prompt/battle/service.py#L854). |

The two selected comparisons are historical wins by `gpt-4.1-mini-2025-04-14` over `gpt-5-chat-latest`, and by `gpt-4.1-mini` over `gpt-4.1`. Every candidate response in those two battles succeeded and stopped normally. The error branches explain preserved application behavior; they do not imply that either featured battle failed.

One judgment covers all ten examples. Browsing an individual example does not create a separate judge ruling for that example. The seven weighted rubric categories total 100 points, but these records do not contain measured numeric category scores. The shown confidence is the judge's recorded confidence, not a calibrated probability of correctness or a score derived from the rubric.

## Failure branches

Candidate failures remain in the evidence bundle with their outcomes and error text. A completed battle therefore does not, in general, prove that both candidates succeeded on every input. The two featured battles happen to have successful candidate responses throughout.

A judge provider failure or parse failure is a different condition from a judge-issued disqualification. In the preserved source, that failure path records a failure reason and resolves the comparison toward B while disqualifying A; this is application fallback behavior, not a model judgment. The record distinguishes `winner`, `resolved_winner`, `failure_reason` and disqualification fields. [Inspect the exact failure handling](https://github.com/CinvanaAI/transcript-model-evaluator/blob/d0358512315b4ca4c16471e16061f64bf35541cb/active_prompt/battle/service.py#L813).

## What this view does not reconstruct

The cache is a supported source mechanism; these selected records do not identify whether a particular output was a cache hit. Repeated saved envelopes must not be counted as fresh provider calls or billing evidence.

The recovered 25-model ranking is a separately backfilled endpoint. The migration grouped a prompt-wide battle directory without preserving every original session boundary or intermediate ladder. The diagram consequently ends at the battle record and does not invent a ranking transition. [Inspect the grouping migration](https://github.com/CinvanaAI/transcript-model-evaluator/blob/d0358512315b4ca4c16471e16061f64bf35541cb/active_prompt/battle/storage.py#L48).

Today's standalone Mortal Kombat implementation evaluates candidates before its insertion ladder. This historical companion describes the preserved evaluator's battle-local output resolution and the archived comparisons, rather than presenting them as runs of the new standalone workflow.
