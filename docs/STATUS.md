# Project status

**Rubric Rumble is a runnable experimental workbench.** The current release completes the path from a configured task to saved outputs, judgments and a readable result. It includes a desktop interface and a command line. It is not a finished fighting game or a predictive model router.

## Available now

| Part | What you can do |
| --- | --- |
| Prepare | Configure OpenAI-compatible or Ollama connections, list available model IDs, explicitly test short text responses and research facts from documentation you supply |
| Define | Set instructions, examples, candidate models, a rubric and an optional provider judge; validate and preview before execution |
| Run | Capture one model or a batch without judging, compare two models, or run an insertion tournament |
| Inspect | Read source examples alongside captured answers, exact-field checks or provider decisions, failures and available usage-based cost estimates |
| Revisit | Open saved JSON/HTML locally without calling models again; inspect two separately preserved historical battles |
| Adapt | Use the retained Python tournament API or modify the MIT-licensed application |

Start with the [README](../README.md), [desktop guide](WORKBENCH.md) or [complete operating atlas](https://cinvanaai.github.io/rubric-rumble/operations/).

## What the evidence establishes

The offline starter runs the real workflow using declared synthetic responses. Automated tests use fixtures and injected transports. The standalone provider adapters therefore have controlled request/response coverage; this release does not claim a new live-provider benchmark across every supported endpoint.

The two [historical battles](HISTORICAL-BATTLES.md) retain actual March 2026 outputs and GPT-5.4 judgments from the earlier evaluator. They demonstrate those particular comparisons under their recorded task and rubric. The current portable workbench is a public continuation, not the historical executable that produced them.

The repository's [verification workflow](../.github/workflows/verify.yml) runs the tests, offline example and package build. Interface and publication checks are scoped to the release being reviewed; a green workflow is not a claim that every provider account or model configuration will work.

## Boundaries that matter

- All modes execute candidate calls sequentially. Batch means multiple candidates, not a provider's discounted Batch API.
- The insertion ladder is not necessarily all pairs. Seed order, position bias and inconsistent judge preferences can change outcomes. Repeated judges and calibrated confidence are not implemented.
- A whole-set battle returns one decision. It does not imply separate numerical rubric scores or per-example winners.
- Cost estimates need returned usage and dated rates you supply. Costs do not choose the winner, and the call ceiling is not a dollar budget.
- Discovery, a successful greeting and a sourced documentation claim establish different things. Research does not fetch the web or automatically update candidate limits.
- The desktop needs Tkinter. Manual model IDs support endpoints without model listing; greeting probes for these manually configured candidates are available through the CLI.
- There is no persisted resume, automatic retry, cross-run cache or animated character roster in the application. [Future ideas](FUTURE-IDEAS.md) discusses these separately.

## Development direction

The original experiment was set aside. This public continuation makes the useful workflow and selected historical evidence accessible independently. Future work can follow a concrete need or an interesting experiment; the ideas list is not a delivery schedule.

The release is complete when a newcomer can understand the task, try it, inspect the result and see the limits. Feature expansion is a separate decision. [Related tools](RELATED-TOOLS.md) provides context for choosing a more extensive evaluation or routing system.
