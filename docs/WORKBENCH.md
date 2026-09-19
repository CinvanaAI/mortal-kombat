# Desktop workbench

Open the local desktop interface after installing the package:

```sh
rubric-rumble gui
```

You can also open a saved task with `rubric-rumble gui path/to/task.json`, or launch the module directly with `python -m prompt_tournament.workbench`. The desktop uses Tkinter and needs a graphical desktop. Some Linux Python installations provide Tkinter as a separate operating-system package. The CLI remains usable without it.

The workbench opens with the bundled offline demo. It makes no model calls while opening, editing or previewing a task.

## First run

1. Open **Connections & candidates**. The three selected demo candidates are explicitly synthetic fixtures.
2. Open **Examples** to read or edit the two inputs and expected fields. **Judge & rubric** contains the transparent exact-field rules.
3. Open **Run & results**, choose **Tournament**, and select **Preview selected run**. This demo needs no provider calls.
4. Choose a results parent folder, then select **Run preview**. Each run gets a new subfolder; earlier evidence is never overwritten.
5. Select **Open latest report** to inspect responses, failures and decisions.

To try Single, select exactly one candidate in the candidate list. For Battle, select exactly two. Use Ctrl/Command-click or Shift-click for selection; **Select all** includes all candidate rows.

| Mode | Selection | Result |
| --- | --- | --- |
| Single | Exactly one candidate | Responses to the examples; no judging |
| Batch | One or more candidates | Responses from each selected candidate; no judging |
| Battle | Exactly two candidates | One comparison across the example set |
| Tournament | Two or more candidates | A judged ranking with recorded comparisons |

Batch is sequential application execution, not a provider's discounted Batch API. The workbench runs jobs on a worker thread and remains responsive; its progress bar indicates activity, not a fabricated percentage. Closing waits for the current job to finish saving evidence.

## Connect your models

In **Connections & candidates**, give a connection a name and choose OpenAI-compatible or Ollama protocol, its base URL, generation endpoint and API-key **environment variable name**. Set any real credential in your environment before launching the workbench. There is no API-key entry field or secret file loader.

Save the connection, then select **Discover models**. This explicitly contacts the configured model-list endpoint. Select returned IDs to add candidates or choose one provider judge. A model appearing in the list establishes visibility, not text-generation support, context capacity or quality.

If your endpoint does not support model listing, enter a known model ID and use **Add model ID** or **Use as judge**. Candidate **Settings** allow explicit output limits, rate evidence or edits to synthetic fixture responses. Changes must pass task validation before they replace the candidate.

**Probe selected** previews one short generation request per selected discovered model: “Reply with exactly: hi”, with an output limit of 32 tokens per request. Use Ctrl+A in the available-model list to select all returned IDs. The preview states the total request count before you accept. Requests run sequentially; each model's actual response, status and returned usage appear separately and are saved as individual `probe-0001.json` records in a new folder, with the requested model, connection, endpoint and recording time. A failed model does not prevent the next selected probe. This checks the recorded connection and text response; it does not certify broader capabilities. Editing a saved connection clears its old discovery list.

Before an evaluation, preview the selected mode and its maximum candidate/judge calls. A provider-backed run additionally requires **Allow this run to call configured providers**. Editing the task, mode or candidate selection invalidates the frozen preview and requires another preview. No live request is made by a stale preview.

## Edit the evaluation

**Task** holds the instructions and provider-call ceiling. **Examples** holds source text and optional exact expected fields. **Judge & rubric** holds either transparent exact-field rules or a provider judge and written comparison criteria. Include weighting and tie-break instructions in the rubric text when appropriate.

Single and Batch do not call a judge. Battle and Tournament use the configured judge. A provider judge must be explicitly selected; adding candidates does not silently appoint one.

Loading and saving tasks preserve portable JSON configuration. Save validates the whole task, including unselected candidates, before writing. To keep an incomplete draft, finish the required task fields first. Raw credentials and unknown configuration fields are rejected.

## Research documented capabilities

**Model research** is separate from discovery and greeting probes. Enter a target model ID, a researcher connection/model, an official documentation URL, and the source text to inspect. The preview explains the one generation request and the text being sent. Nothing is fetched or researched automatically.

The returned research records supported context/output limits and modalities, source quotations, unknowns, source identity and researcher usage. Review that evidence before relying on it; a quotation match alone does not make an inferred alias association certain. Recording time describes this research receipt, not the source's publication date. The target model ID is separate from the researcher connection and does not establish a target provider. The research result is saved to a new folder as `model-research.json`; storage is reserved before the request. It is not silently applied to candidate limits or used as a measured benchmark.

Reports, probes and research records may contain the task text and model outputs you supplied. They stay in your chosen local folders; this workbench does not publish them.
