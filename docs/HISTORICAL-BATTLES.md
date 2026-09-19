# Two recorded model battles

[Open the battle viewer](https://cinvanaai.github.io/rubric-rumble/history/).

On March 18, 2026, the GPT-5.4 judge chose **Gemma 3 27B over DeepSeek V3.1 671B**, citing stronger format compliance and preservation of execution-critical details. In the second selected battle, it chose **gpt-4.1-mini-2025-04-14 over gpt-5-chat-latest**, citing fewer unsupported additions. Both candidates in each comparison completed all ten examples with a normal stop and received identical request text per example.

## Read the decision yourself

The task turns transcripts into grounded implementation notes in seven fixed sections. The 100-point rubric supplies weighted criteria for objectives, facts, decisions, implementation, constraints, next steps and format. Each saved judgment covers the complete ten-example bundle: a winner, reason and self-reported confidence. The judge did not return numerical category scores or separate winners for individual examples.

The viewer includes the task, all ten generated benchmark examples, forty literal candidate answers, the rubric, both assembled judge requests and their rulings. Each battle retains the exact judge instructions used at that time; the earlier instructions forced a winner and the later instructions allowed disqualification.

## Model context

Google identifies the selected [Gemma 3 variant as 27B](https://ai.google.dev/gemma/docs/core/model_card_3). DeepSeek describes [V3.1 as a mixture-of-experts model with 671B total parameters and 37B activated per token](https://huggingface.co/deepseek-ai/DeepSeek-V3.1). The visible size contrast refers to total parameters; these records do not establish a compute or price ratio.

The captured OpenAI IDs are shown exactly, including the dated mini snapshot and `gpt-5-chat-latest` alias. The latter is the Chat variant used in the record.

## Historical process and public projection

The [historical flow](https://cinvanaai.github.io/rubric-rumble/history/historical-flow.html) follows the archived evaluator: resolve both candidates on every example, assemble the full comparison, judge it, and save the evidence. The [current standalone workflow](https://cinvanaai.github.io/rubric-rumble/operations/) evaluates candidates before ladder insertion. The archive does not establish the exact code revision for every historical call.

Publication uses an allowlisted projection. Reviewed benchmark text, outputs, model labels, timestamps, usage fields and judge text are preserved; machine paths, provider response IDs, credentials and unrelated private records are excluded. The complete raw archive remains private. These are two selected historical comparisons, not a reconstructed overall ranking. No billing amount was recovered for these cases.
