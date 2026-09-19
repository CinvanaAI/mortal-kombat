# Task configuration

`mortal-kombat example task.json` writes every field needed for an offline run. The schema is intentionally small and rejects unknown fields so an inline `api_key` cannot be accidentally treated as public configuration.

- `instructions`: what candidates should do.
- `artifacts`: unique IDs, source text, and optional expected answers.
- `models`: unique candidate IDs and either fixture responses or a configured provider/model pair.
- `rubric`: the exact-field contract or a pairwise judging description.
- `judge`: transparent rules or a separate provider model.
- `providers`: explicit base URLs and optional environment-variable names for credentials.
- `max_calls`: a ceiling on provider calls for this run. Each model also has `max_output_tokens`, defaulting to 1024.

The plan reports maximum candidate and judge calls. The call limit is not a dollar budget. No tools, external browsing, or automatic retries are enabled by these adapters.

## Live providers

The complete example files contain placeholders for two model names. Choose models present in your setup; the tool does not invent availability or discover all models automatically.

Ollama uses `/api/chat` with streaming disabled. OpenAI uses `/responses` with `store: false`. The output is still sent to the configured provider when you explicitly execute; the local report is not an assertion about the provider's retention policy. API keys live in the environment named by `api_key_env`. The tool refuses HTTP except for loopback endpoints and refuses redirects.

The adapter shapes and usage fields follow [OpenAI's Responses reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create) and [Ollama's chat reference](https://docs.ollama.com/api/chat). They are tested with synthetic HTTP responses; live account/model behavior must be verified with your own configuration.

## Provider judging

For an open-ended task, replace the rules judge with:

```json
{"kind": "provider", "model": {"id": "independent-judge", "provider": "local", "model": "YOUR_JUDGE_MODEL", "max_output_tokens": 1024}}
```

Use a `rubric` with `kind: "pairwise"` and a concrete `description` of what counts as better. The judge receives instructions, rubric, original artifacts, and both captured responses. It must return a JSON decision with `winner`, `short_reason`, and optional `confidence`. The five outcomes are A wins, B wins, A disqualified, B disqualified, or both disqualified. A malformed judge response fails the run; prior call evidence is still retained.

Judge IDs must differ from candidate IDs. If the same underlying model is deliberately used as both judge and candidate under different IDs, the tool does not claim independent judgment. Choose that relationship consciously.

## Rates and estimates

Optional `rates` belong to each candidate or judge model. Required fields are `input_per_million`, `output_per_million`, `currency`, `source`, and ISO date `as_of`; `cached_input_per_million` is optional. Use the applicable rates for the actual route/account. The program retains your source/date rather than fetching or claiming current prices.

Input/output token counts come only from provider responses. Cached-input pricing requires compatible reported cache counts and a supplied cached-input rate. Reported cache-write tokens are not priced by this version. Unsupported or incomplete inputs produce an unavailable estimate. Candidate and judge subtotals remain separate, and currencies are never mixed.

## Failures and evidence

Candidate provider failures disqualify that candidate while others can continue. Invalid JSON in rules mode is retained and disqualifies the candidate during output validation; remaining artifacts for that candidate are skipped. A failure of the provider judge stops the ranking; the JSON/HTML bundle keeps the attempted calls and earlier decisions. Re-running requires a new output directory and makes fresh calls. There is no automatic paid retry or silent cache reuse.

`mortal-kombat report runs/first-run/result.json --out runs/replay` renders saved evidence without running candidates or providers. The output directory must be new. The Python `save_report` function accepts a `renderer` callback for a different presentation of the same result dictionary.

Reports preserve prompts and candidate text because those are the evaluation evidence. Treat your own real-data result directories as private until reviewed.
