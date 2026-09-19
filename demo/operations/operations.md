# How Mortal Kombat operates

Give several candidates the same task, keep their answers, compare the saved answers, and build a ladder whose decisions can be inspected.

This guide maps the standalone tournament branch, with source links pinned to the reviewed core snapshot. The recorded extraction example is synthetic. For original provider responses and judge decisions, read the [two historical model battles](../history/) and their companion flow. Those records come from the archived evaluator, whose execution path differs from this standalone workflow. Sequence views show order and responsibility; conditional labels describe alternative paths, not steps every run takes.

Source snapshot: `a8c714530e82e945b48aa939f4e14bb0bd26fa83`. [Open the complete operating path](00-overview.html).

## Start in the desktop workbench

Run `mortal-kombat gui` to prepare a task: configure connections, discover model IDs, inspect documented model facts and explicitly probe a selected model for a short text response. Research uses documentation you supply and preserves source quotes. Discovery, sourced claims and observed responses remain separate evidence.

Single and Batch capture answers without a judge or ranking. Battle compares exactly two candidates; Tournament uses the ladder explained below. The provider adapter supports both OpenAI Responses and an explicitly selected Chat Completions endpoint, plus Ollama chat. [Workbench controls](https://github.com/CinvanaAI/mortal-kombat/blob/main/docs/WORKBENCH.md) · [Model preparation](https://github.com/CinvanaAI/mortal-kombat/blob/main/docs/PROVIDERS.md).

## 01. Define the job, then choose whether to execute

A task file is the experiment contract. Planning validates that contract; execution is a separate step.

[Open sequence view](01-setup.html)

The JSON task supplies instructions, source artifacts, candidate configurations, a rubric, and a judge. Rules judging requires an expected string value for every rubric field in every artifact. Provider judging receives a written rubric instead. The validator checks supported fields, unique artifact/candidate/judge IDs, provider references, URLs, token limits, optional rate records, and the provider-call limit.

`mortal-kombat run task.json` validates and prints a plan without calling providers or writing a result. The plan reports candidate/artifact counts, whether network access is needed, the configured call limit, a normalized task hash, and upper bounds: live candidates × artifacts, plus at most n(n−1)/2 judge calls in provider-judge mode. This is a call-count ceiling, not a dollar quote.

`run ... --execute --out new-folder` reserves a new output directory, then calls the workflow with network permission. `demo --out new-folder` uses the packaged fixture offline. The workflow validates again and resolves every required candidate and judge environment variable before its first provider call. Missing keys stop preflight. Because the CLI has already reserved the folder, that failure can leave an empty directory with no result bundle.

| Command | Effect |
| --- | --- |
| `example task.json` | Write a complete editable fixture task; reject an existing file. |
| `run task.json` | Validate and print the plan; no execution. |
| `run task.json --execute --out new-folder` | Execute the configured task, including explicit network routes. |
| `demo --out new-folder` | Run the offline fixture through the same workflow. |
| `report result.json --out new-report` | Render previously saved evidence; no candidate or judge execution. |

Source: [CLI dispatch and output reservation](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/workflow_cli.py#L16) · [validate_task](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/task.py#L26) · [plan_task](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/task.py#L129) · [run_task preflight](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/workflow.py#L70)

## 02. Collect each candidate’s answers across the artifacts

The tournament core drives evaluation. The workflow supplies the candidate/provider callback and records the evidence.

[Open sequence view](02-candidates.html)

The core first establishes a seed order, then loops through candidates. For each candidate it visits the artifacts in task order. The evaluation callback combines the task instructions with one source artifact, adds a started call record, and either reads that artifact’s fixture response or invokes the configured provider. This is sequential work; there is no parallel model race.

The OpenAI adapter appends `/responses` to the configured base URL and sends a non-streaming request with `store: false` and the output-token limit. The Ollama adapter appends `/api/chat`, sets `stream: false`, and supplies `num_predict`. Keys come from named environment variables. The transport refuses redirects, applies the configured timeout and an 8 MB response limit, and requires a JSON-object response. There is no automatic retry or model discovery.

The executor first copies returned text, normalized/raw token usage, available response/model IDs and completion state into the call record. It then calculates and stores the cost estimate, before checking completion and output text. Incomplete or empty output fails the call. In rules mode, a non-object or invalid JSON answer disqualifies the candidate; its remaining artifacts are skipped. The next candidate can still run. A syntactically valid JSON object with missing or wrong fields instead receives fewer points.

The callback returns answer text for one artifact. The core caches successful text and constructs each complete CandidateView internally; it does not export that object to the workflow’s call ledger. Every candidate’s evaluation phase finishes before the ladder begins. Battles reuse these captured views; they do not ask candidates to answer again. The application creates a fresh in-memory cache per run. The lower-level core accepts a caller-supplied cache, but the CLI does not persist or resume one.

| What failed? | Recorded meaning |
| --- | --- |
| Transport, empty text, or incomplete response | Call status is failed; the candidate is disqualified. |
| Rules assessment rejects returned JSON | Call may be completed, while the output assessment is invalid and the candidate is disqualified. |
| Valid object has wrong or missing fields | Candidate remains eligible; exact-field score is lower. |

Source: [run_tournament evaluation phase](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/engine.py#L205) · [execute and evaluate callbacks](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/workflow.py#L94) · [call_provider](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/providers.py#L77) · [HTTP transport](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/providers.py#L28)

## 03. Insert surviving candidates into a ranked ladder

Initial seed order decides who is considered first. Pairwise judgments determine where each survivor lands.

[Open sequence view](03-ladder.html)

The application seeds candidates by provider name and candidate ID, case-insensitively. It passes neither rate costs nor a prior ranking into the core. The reusable core also supports prior-ranking seeds and explicit model costs: known active ranks first, new candidates next, previously disqualified candidates last; newly priced candidates sort by descending input-plus-output unit cost before unpriced candidates. Those optional core inputs are not part of this task CLI.

The first surviving candidate becomes the ladder’s first entry without a battle. For each later survivor, the insertion loop begins at ladder position 0. A is always the candidate being inserted; B is the incumbent at the current position. The judge receives both candidates’ complete saved output sets. Each valid comparison produces one battle record, and its outcome changes the ladder as shown below.

This is an insertion tournament. It compares pairs as insertion requires, which can include every pair in the worst case. It does not repeat judgments for confidence or validate that a judge’s preferences are transitive. Different seed orders or inconsistent judgments can affect the result. Disqualified entries appear separately; their appended numbers in `current_ranking` are status positions, not quality ranks.

| Judge outcome | Ladder action |
| --- | --- |
| `model_a_better` | Insert A immediately before B; finish this candidate. |
| `model_b_better` | Advance one position. If A reaches the end, append it. |
| `model_a_disqualified` | Drop A; finish this candidate. |
| `model_b_disqualified` | Remove B; compare A at the same position against the next incumbent. |
| `both_disqualified` | Remove both A and B; finish this candidate. |

Source: [seed_models](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/engine.py#L144) · [optional cost seed ordering](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/engine.py#L183) · [insertion and five outcome branches](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/engine.py#L264) · [application ModelRef construction](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/workflow.py#L157)

## 04. Choose the judge and understand the failure boundary

Rules and provider judging are alternative modes. A candidate disqualification and a failed judging run have different consequences.

[Open sequence view](04-judging.html)

The rules judge sums exact, case-sensitive field matches across all artifacts. Each present string equal to the expected string earns one point; extra fields earn none. Higher total wins. Equal totals use the lexically smaller candidate ID and explicitly report a deterministic tie-break, not a quality difference. This proves behavior on the chosen extraction cases; it is not a general measure of model quality.

A provider judge receives the instructions, rubric, every source artifact, and labeled A/B outputs. Its prompt requests one of the five documented winner values, a reason, and optional confidence. The workflow requires a JSON object, a nonempty string reason, and confidence that is omitted/null or a finite number from 0 to 1. It rejects booleans, strings, nonfinite values and invalid winners. This stricter workflow boundary is separate from the legacy core parser API.

An exception from candidate evaluation removes that candidate and allows the tournament to proceed. A judge call failure or malformed decision instead propagates out of the core. The workflow returns status `failed`, keeps earlier call/output/decision evidence, and has no returned tournament object or ranking. If the core finishes with no survivors the status is `no-ranked-candidates`; with at least one survivor it is `completed`. A sole survivor can therefore rank without a successful battle.

The configuration requires distinct candidate/judge IDs, but it does not prove that the configured underlying model is independent from the candidates. Provider-judge confidence is the judge’s supplied number, not a calibrated statistical confidence interval. Prompt wording treats evidence as data; it is not an adversarial prompt-injection guarantee.

| Terminal condition | Result available from the workflow |
| --- | --- |
| Preflight rejected before ledger creation | Exception to CLI; no result dictionary. |
| Tournament returned ≥1 survivor | `completed`, ranked survivors, DQs and battle records. |
| Tournament returned 0 survivors | `no-ranked-candidates`, DQs and any completed battles. |
| Judge/other tournament exception | `failed`, error and captured evidence; `tournament: null`. |

Source: [assess_output](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/workflow.py#L15) · [provider judge request](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/workflow.py#L26) · [strict provider decision parser](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/workflow.py#L47) · [judging and result status](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/workflow.py#L135)

## 05. Account for usage and write the inspectable result

The result keeps the evidence needed to explain a ranking. Cost accounting runs alongside the judgments.

[Open sequence view](05-evidence.html)

A cost estimate requires returned input/output token counts and user-configured per-million rates with currency, source and date. If the reported cached-input count is greater than zero, the matching cache rate must be present. A reported count of zero does not require a cached-input rate. If a cache rate is configured but cache usage is missing, the estimate is unavailable. A positive reported cache-write count makes the estimate unavailable; zero cache-write tokens do not block an estimate. Missing counts/rates and impossible cache counts also remain unavailable rather than silently becoming zero.

For supported usage, the amount is ((input − cached input) × input rate + cached input × cached-input rate + output × output rate) / 1,000,000. The workflow groups known subtotals by candidate/judge phase and currency, and counts attempted provider calls with no estimate. A failed call can still have a usable estimate when its returned usage was captured. These are usage-and-rate estimates, not invoices, energy measurements or subscription/hardware costs.

Rates do not enter the application’s judging prompt, rules scores, or seed ModelRefs. A cheaper model does not automatically win. There is a provider-call cap, but no dollar budget or quality-per-dollar optimizer. Fixture calls have no returned billable usage and no configured rates; zero attempted provider calls is not a measured model-cost result.

The workflow returns a `mortal-kombat.result.v1` dictionary with normalized task and hash, plan, call records, outputs/field checks, candidate summaries, decisions, tournament when available, errors and cost summary. The CLI writes `result.json`, then a self-contained escaped `report.html`. Saved-result reporting reads this evidence without executing providers. These are two filesystem writes, not a transaction: an I/O failure can leave a partial folder. The original request/source/output text is retained, so a real result should be reviewed before sharing.

Source: [normalize_response](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/providers.py#L52) · [estimate_cost](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/providers.py#L97) · [cost and evidence finalization](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/workflow.py#L167) · [render_report / save_report](https://github.com/CinvanaAI/mortal-kombat/blob/a8c714530e82e945b48aa939f4e14bb0bd26fa83/src/prompt_tournament/report.py#L8)

## A recorded synthetic walkthrough

The bundled example uses two source artifacts and three fixture candidates. This is an existing engine result, not a live model evaluation.

| Recorded step | What the evidence shows |
| --- | --- |
| Seed | complete-fixture → malformed-fixture → missing-owner-fixture. |
| Evaluate | Complete answers earn 4/4. Malformed JSON disqualifies that candidate after one artifact. Missing-owner answers earn 2/4. |
| First ladder entry | complete-fixture becomes the first survivor; malformed-fixture is skipped. |
| One battle | A = missing-owner-fixture; B = complete-fixture. Exact-field totals choose model_b_better. |
| Final result | complete-fixture first; missing-owner-fixture second; malformed-fixture disqualified. Five captured calls, four successful core evaluations, one battle, zero provider calls. |

[Exact recorded JSON](recorded-example.json)

From this version’s checkout with Python 3.11 or newer:

```text
python -m pip install .
mortal-kombat demo --out my-first-tournament
mortal-kombat report my-first-tournament/result.json --out rendered-again
```

Use new output folders. Timestamps differ; compare the task hash, outputs, decisions and ranking rather than the entire result file.

