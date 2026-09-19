# Related tools

Rubric Rumble is a small experimental workbench for task-specific model comparisons. Its particular form is an inspectable tournament: prepare candidates, capture answers, judge complete example sets and keep the decisions behind the ladder.

There are substantially broader tools in this space. These comparisons describe their documented capabilities as checked on September 19, 2026; they are not a head-to-head test of reliability, accuracy or cost.

| Tool | What it does | Where it overlaps |
| --- | --- | --- |
| [Promptfoo](https://github.com/promptfoo/promptfoo) | An open-source evaluation and security-testing toolkit with provider comparisons, assertions, reports and automated checks | The closest comparison for running task-specific tests. It supports model judges, custom rubrics and selecting a preferred output. Its scope is broader than this workbench. |
| [Not Diamond](https://docs.notdiamond.ai/docs/what-is-model-routing) | Predicts which model should receive an incoming request, using pretrained or custom routers | Related to deciding which model to use. Rubric Rumble evaluates examples; it does not train or serve a predictive router. |
| [Portkey Gateway](https://github.com/Portkey-AI/gateway) | An open-source provider gateway with routing rules, retries, fallbacks and load balancing | Related to connecting models and operating requests reliably. It is infrastructure beneath or beside an evaluation workflow. |

Promptfoo's [LLM-as-a-judge guide](https://www.promptfoo.dev/docs/guides/llm-as-a-judge/) describes rubric scoring, preference judgments and judge calibration. If your goal is a broader evaluation setup, that is a useful place to investigate.

Not Diamond's [custom-router training](https://docs.notdiamond.ai/docs/router-training-quickstart) uses representative inputs, candidate responses and numeric evaluation scores. The historical comparisons here contain pairwise winners and reasons, not a ready-made dataset of per-model numeric scores. An export or integration would require an explicit design.

The linked Portkey repository describes the open-source gateway. Features presented separately as hosted or enterprise offerings should not be assumed to come with that code.

## Where this project fits

Use this repository to try the tournament workflow, inspect a compact Python implementation, or study the recorded battles and their limitations. The code and evidence remain useful to examine even if you choose another tool for your own application. The [future ideas](FUTURE-IDEAS.md) show directions we considered; they are not claims of feature parity.
