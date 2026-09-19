# Rubric Rumble: inspect the decision

Open [index.html](index.html) locally, or serve this directory as a static site. The page embeds the actual result and observed ladder trace; it has no external fonts, scripts, images, analytics, or automatic network requests.

The task extracts owner/action fields from two synthetic records. Two valid candidates score 4/4 and 2/4. A third returns plain text and is disqualified after its first artifact. Exactly one battle is recorded. This is a real execution with fixture responses, not a real-model benchmark.

## Reproduce

From the repository root, with Python 3.11 or newer:

```text
python -m pip install -e .
rubric-rumble demo --out runs/first-evaluation
```

Compare the effective task fingerprint and outcomes with [result.json](result.json). Run timestamps differ. The page's JSON download is an exact byte copy of `examples/demo-result.json`; the [task](task.json) is an exact copy of `examples/extraction-task.json`.

The [trace](trace.json) records states observed through Python tracing of the unchanged engine. Its four phases are output checking, seeding, the single comparison, and final insertion. It is presentation evidence alongside the engine result, not four battle records. The source hashes and verification basis are in [source-checks.json](source-checks.json).

No provider call was attempted. Token usage and cost remain unavailable; no local hardware, energy, or subscription cost is inferred. Rules scores decide this fixture. Missing or inconsistent judgments can affect other tournament configurations.

The source hashes describe the replay snapshot `a8c714530e82e945b48aa939f4e14bb0bd26fa83`, not every file in the current checkout. The [operating atlas](operations/) explains the current application.
