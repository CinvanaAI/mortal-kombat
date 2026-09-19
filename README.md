# Mortal Kombat

Task-specific model evaluation.

**Give candidate models the same task, compare what they return, and inspect why each one won or failed.**

Mortal Kombat turns a task, its examples, and a declared judging rule into a recorded tournament. You get the exact outputs, field checks or judge decisions, a final ranking, and usage-based cost estimates when the necessary evidence exists.

Follow [how the whole system runs](https://cinvanaai.github.io/mortal-kombat/operations/) through task setup, provider execution, the tournament ladder, judging, and saved results. The guide includes six linked operational diagrams and a readable source map.

Explore the [recorded evaluation](https://cinvanaai.github.io/mortal-kombat/) to inspect the source, field checks, disqualification and ladder decisions before installing anything. For an offline replay, download or clone this repository, then open `demo/index.html` in a browser.

## Run your first evaluation

Python 3.11 or newer; the application uses only the standard library.

```text
python -m pip install -e .
mortal-kombat demo --out runs/first-run
```

Open `runs/first-run/report.html`. The complete machine-readable record is beside it in `result.json`.

The first task extracts an owner and next action from two short source records. Three synthetic candidates supply complete JSON, JSON missing the owner, and plain text. The transparent rules judge produces:

| Candidate | Exact fields | Result |
| --- | --- | --- |
| complete-fixture | 4 of 4 | First |
| missing-owner-fixture | 2 of 4 | Second |
| malformed-fixture | 0 of 4 | Disqualified: not JSON |

This is a real run of the evaluation workflow using fixed fixture responses. No model is called. The example shows correctness checks and failure handling; it is not a benchmark of real models. Fixture responses have no token bill, so their monetary cost is unavailable.

## Make the task yours

```text
mortal-kombat example my-task.json
mortal-kombat run my-task.json
mortal-kombat run my-task.json --execute --out runs/my-task
```

`example` writes a complete editable task. Change its source records, expected fields or supplied fixture responses. `run` alone validates it and prints the plan. `--execute` runs the chosen configuration. Every result uses a new output directory; existing runs are never overwritten.

For real models, start with [the Ollama configuration](examples/ollama-task.json) or [the OpenAI configuration](examples/openai-task.json). Replace the two model placeholders with models available to your own setup. OpenAI credentials are read from the named environment variable, never from the task file. Configure any rates yourself; none are bundled as current prices.

The rules judge works with real model responses too. For tasks without exact reference answers, [provider judging](docs/TASKS.md#provider-judging) uses a separately configured model and your rubric.

## What you can inspect

- Each source artifact, the task instructions, and the exact rubric.
- Every attempted candidate call and its captured text or bounded error.
- Per-field expected/actual checks for the extraction rules judge.
- Pairwise decisions, reasons, disqualifications, and the final ladder.
- Provider-returned usage and separately labeled candidate/judge cost estimates.
- The effective task configuration and its SHA-256 fingerprint.

## How to read a result

A ranking answers the question defined by your task and judge. Exact-field checks deliberately reward literal correctness. Provider judging depends on that judge's decisions. The ladder may not compare every possible pair; order and inconsistent judgments can affect the result. Tied rules scores use candidate ID order, explicitly recorded as a tie-break.

Cost is displayed alongside the result. It does not silently decide the winner. Missing usage, missing rates, or unsupported cache-write pricing stays unavailable. The report is an estimate from returned usage and your dated rates, not a provider invoice or a measure of local hardware cost.

Each command run evaluates fresh responses. There is no cross-run cache in the application workflow. The lower-level library still supports caller-owned caching.

## Library and development

Existing `prompt_tournament` imports and the original `prompt-tournament-demo` command remain available. See [the API](docs/API.md) for the full workflow and the small tournament core.

```text
python -m pip install -e ".[test]"
python -m pytest -q
```

Tests use fixtures and injected transports. [Background](docs/ORIGIN.md) explains how the project grew. [MIT licensed](LICENSE.md); [security and local output](SECURITY.md).
