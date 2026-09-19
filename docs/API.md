# Python API

For a complete configured task:

```python
from prompt_tournament.workflow import run_task
from prompt_tournament.workflow_cli import demo_task

result = run_task(demo_task())
assert result["status"] == "completed"
print(result["tournament"]["current_ranking"])
```

`run_task` validates the full task first. Live routes require `allow_network=True` and their configured environment variables. A caller can inject `transport(url, headers, payload, timeout)` for offline testing; it returns a provider-shaped JSON object. Do not log the headers.

The original `Artifact`, `ModelRef`, `JudgeDecision`, `run_tournament`, `seed_models` and `parse_judge_output` API remains unchanged. The core accepts evaluation/judge callbacks and an optional caller-owned output cache. It stores supplied prices as metadata and uses them to seed new candidates when available; it does not compute the workflow's cost report. The new workflow seeds by stable candidate identity and records rates separately.

`report.save_report(result, directory)` writes into an existing caller-owned directory. The installed command reserves a new directory first to prevent overwriting prior runs.
