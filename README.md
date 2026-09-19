# Rubric Rumble

**Same task. Same rubric. Let the answers compete.**

Which model actually does the job you care about? Rubric Rumble lets you give candidates the same examples, compare their answers, and open the judge's decision. It grew out of a model fight club inside our earlier system-building experiments. Sometimes the smaller contestant won. The interesting part was finding out why.

This is a runnable experimental Python workbench with a desktop interface, four evaluation modes, and local reports. Formerly **Mortal Kombat**. [What changed](docs/RENAMING.md).

| Take a look | What you will find |
| --- | --- |
| [Read two actual battles](https://cinvanaai.github.io/rubric-rumble/history/) | Every test input, all forty model answers, the rubric and the two recorded judge decisions |
| [Follow the whole system](https://cinvanaai.github.io/rubric-rumble/operations/) | An explorable operating atlas, from discovering models to the saved result |
| [Try the offline replay](https://cinvanaai.github.io/rubric-rumble/) | A small extraction task with fixed responses; inspect checks, failures and ladder changes in your browser |
| [Open the sketchbook](docs/FUTURE-IDEAS.md) | Original characters, a selection screen and an animated fight driven by recorded outcomes: ideas we have not built yet |

## A battle worth opening

On the same ten-example transcript task and weighted rubric, the recorded GPT-5.4 judge chose **Gemma 3 27B over DeepSeek V3.1 671B**, and **GPT-4.1 mini over GPT-5 Chat**. These are two particular whole-set judgments from March 2026.

Read the actual answers and decide what you make of the judgment. Each battle has one whole-set verdict, not ten individual scores. DeepSeek's 671B is its total parameter count, with 37B active per token; the comparison does not establish a compute or cost ratio. [Open the battles](https://cinvanaai.github.io/rubric-rumble/history/) · [Methods and context](docs/HISTORICAL-BATTLES.md).

## Run your first tournament

You need Python 3.11 or newer. The application uses the standard library. Clone the repository below, or download and extract its ZIP and open a terminal in that folder.

```text
git clone https://github.com/CinvanaAI/rubric-rumble.git
cd rubric-rumble
python -m pip install -e .
rubric-rumble demo --out runs/first-run
```

Open `runs/first-run/report.html`. It shows the original examples alongside the answers and decisions. The complete record is in `result.json` beside it.

The starter uses three explicitly synthetic candidates on two owner/action examples:

| Candidate | Exact fields | Outcome |
| --- | --- | --- |
| complete-fixture | 4 of 4 | First |
| missing-owner-fixture | 2 of 4 | Second |
| malformed-fixture | 0 of 4 | Disqualified: not JSON |

This runs the actual evaluation workflow with fixed fixture responses and **zero model calls**. It demonstrates the mechanism. It is not another real-model benchmark, and fixture costs are unavailable.

A versioned Python wheel is also available in [Releases](https://github.com/CinvanaAI/rubric-rumble/releases/tag/v0.3.1). After downloading it, install the file with `python -m pip install path/to/the-downloaded.whl`. The same commands below then work.

For the desktop interface, run:

```text
rubric-rumble gui
```

The workbench opens with the offline task. Python needs Tkinter and a graphical desktop; some Linux installations provide Tkinter separately. [Desktop walkthrough](docs/WORKBENCH.md).

## Make it your experiment

Prepare a task in the desktop, or write an editable example:

```text
rubric-rumble example my-task.json
rubric-rumble run my-task.json
rubric-rumble run my-task.json --execute --out runs/my-task
```

The middle command validates and previews. Execution is explicit, and every run uses a new output folder.

Configure your own [Ollama](examples/ollama-task.json) or [OpenAI-compatible](examples/openai-task.json) models. The workbench can list model IDs, explicitly probe a short text response, and extract model facts from documentation you supply. Credentials are read from named environment variables. [Connections](docs/PROVIDERS.md) · [Research](docs/MODEL-RESEARCH.md) · [Task format and judging](docs/TASKS.md).

| Mode | What it does |
| --- | --- |
| Single | Capture one candidate's answers; no judge |
| Batch | Capture all selected candidates sequentially; no judge |
| Battle | Compare exactly two candidates across the example set |
| Tournament | Build an insertion ladder from recorded comparisons |

Use `--mode single`, `--mode batch`, `--mode battle` or `--mode tournament` with `run`, or choose the mode in the desktop.

## What a result means

You get the task, source examples, captured answers, field checks or judge reasons, failures, and available usage-based cost estimates. The insertion ladder may not compare every pair. Seed order and inconsistent judgments can affect the ranking. Exact-field ties use a recorded candidate-ID tie-break.

Cost is shown alongside quality evidence; it does not choose the winner. Estimates need provider-returned usage and your dated rates. Missing evidence stays unavailable. The call limit is not a dollar budget.

Reports keep your input and model output locally, so review real-data runs before sharing. [Security and local output](SECURITY.md).

## Where this stands

The current release completes the prepare → run → inspect loop. The character roster, animated matches, resumed runs and learned routing are future possibilities. [Project status](docs/STATUS.md) separates current behavior, evidence and limits. [Related tools](docs/RELATED-TOOLS.md) compares the scope with Promptfoo, Not Diamond and Portkey.

The tournament's history is part of the project: [where it came from](docs/ORIGIN.md), [what changed](CHANGELOG.md), and [what we wanted to try next](docs/FUTURE-IDEAS.md).

## Build on it

Own code is [MIT licensed](LICENSE.md). The Python distribution remains `prompt-tournament-engine`; existing `prompt_tournament` imports, `prompt-tournament-demo` and the earlier CLI alias continue to work. [Library API](docs/API.md) · [Names and compatibility](docs/RENAMING.md#names-you-may-see).

```text
python -m pip install -e ".[test]"
python -m pytest -q
```

Tests use fixtures and injected transports. For a bug, include the version, chosen mode and a small synthetic task that reproduces it. Review any attached report for private material first. [Report an issue](https://github.com/CinvanaAI/rubric-rumble/issues).
