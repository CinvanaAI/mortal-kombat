# Connections and model preparation

Configure a provider in the task file using its base URL and the **name** of an environment variable containing your key. Never put the key itself in a task. OpenAI uses a base ending in `/v1`; Ollama uses the server root. Remote connections require HTTPS; loopback HTTP is supported for local Ollama.

## Discover models

```text
rubric-rumble models examples/openai-task.json --provider openai
```

Replace the provider name with the key under `providers` in your task. This explicitly requests the connection's model list; it does not generate model responses. The desktop workbench exposes the same operation as Discover.

OpenAI discovery uses [GET /models](https://developers.openai.com/api/reference/python/resources/models/methods/list); Ollama uses [GET /api/tags](https://docs.ollama.com/api/tags). Discovery returns identifiers, not a guarantee that every listed model supports your selected text endpoint. Image, audio, embedding and unsupported models may be listed by a connection.

## Select the execution endpoint

OpenAI providers default to `"endpoint": "responses"`. Set `"endpoint": "chat-completions"` when the chosen model or compatible service uses Chat Completions. There is no silent retry through another endpoint. Ollama uses `/api/chat` with `"endpoint": "chat"`.

Candidates and the judge can use different configured connections. Batch means local sequential execution over selected models and examples; it is not a provider's asynchronous Batch API.

## Check a response before a tournament

In the workbench, select candidate models and choose **Probe selected**. The equivalent command first previews the count:

```text
rubric-rumble probe my-task.json --candidate my-candidate-id
rubric-rumble probe my-task.json --candidate my-candidate-id --execute --out runs/greeting-check
```

Repeat `--candidate` to check several candidates. Each selected model receives `Reply with exactly: hi` with a 32-token output budget. Results distinguish a completed text response, an empty response, an incomplete response and a failed call. A model can exhaust this small budget without being incapable of text generation; increase the normal task's output limit for a fuller trial. A greeting response establishes a working text request through that connection, not the model's quality on your task.

The command saves model/connection identity, time, returned text and usage in `probes.json`. Probes are explicit generation requests and may be billed by the provider. They are separate from tournament scores and from [documented model research](MODEL-RESEARCH.md).

## Run modes

| Mode | Selected candidates | Judgment |
| --- | --- | --- |
| Single | Exactly one | Captures all example responses; no judge calls |
| Batch | One or more | Captures all example responses; no judge calls |
| Battle | Exactly two | One pairwise comparison over the complete example set |
| Tournament | Two or more | Inserts candidates into a ladder using pairwise comparisons |

Preview a task before running it. The plan shows the candidate-call count, maximum judge-call count and configured call limit. Each run uses a new directory. Runtime output may contain your task's private information; review it before sharing.
