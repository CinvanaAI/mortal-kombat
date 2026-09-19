# Documented model facts

Model research extracts a small capability catalog from source text you supply. It keeps the source, URL, recording date, SHA-256 hash, supporting quotations, and the research model's identity alongside the result. It complements the separate connection/text probe and task evaluation.

Choose the target model identifier, paste the relevant official documentation and its HTTPS URL, and choose a configured research provider/model. This operation makes exactly one explicit generation request to the researcher. It does not execute the target model, fetch the URL, browse for sources, or write files; the workbench or caller saves the returned record.

The four extracted fields are:

| Field | Known value | Unknown value |
|---|---|---|
| `context_window_tokens` | Positive integer token count | `null` |
| `max_output_tokens` | Positive integer token count | `null` |
| `input_modalities` | Unique list drawn from `text`, `image`, `audio`, `video`, `embeddings` | `null` |
| `output_modalities` | Same modality vocabulary | `null` |

Each known field requires a verbatim quote from the supplied document. Unknown values require null quotes. The response must identify the requested model and include a source quote for that association. Missing facts remain unknown; text input does not imply text output, and names are not used to guess capabilities.

## Python API

```python
from prompt_tournament.model_research import research_model

# Invoking this function sends the supplied source text to this researcher.
result = research_model(
    target_model_id="the-provider-model-id",
    source_text=document_text,
    source_url="https://the-provider.example/docs/model",
    provider={
        "kind": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
    research_model={"model": "your-research-model-id", "max_output_tokens": 2048},
)
```

Both existing OpenAI endpoints and the Ollama adapter are supported. Credentials come only from the configured environment variable and are not included in the returned receipt. Source text is limited to 400 KB, the returned JSON text to 200 KB, and the researcher's requested output limit to 1–16,384 tokens. These byte limits do not estimate a model's context length.

The result has schema `mortal-kombat.model-research.v1`, status `completed`, `target_model_id`, `source`, `model_identification`, `catalog`, per-field `evidence`, an `unknowns` list, `researcher`, `validation`, and the exact `raw_response`. `source.recorded_at` is when this supplied document was recorded; it is not a claim that its URL was fetched then or that the document was published then.

`model_identification.exact_identifier_in_quote` tells you whether the requested identifier occurs as a complete identifier in the quoted source. A provider alias can differ from a documentation title. In that case the association remains the researcher's claim for operator review; the function does not invent or save a canonical alias mapping.

## What validation establishes

The parser rejects duplicate or unexpected fields, malformed JSON, invalid field types, nonfinite numbers, unsupported modality labels, changed target IDs, missing identity evidence, and quotations absent from the supplied text. Incomplete/empty provider responses and transport failures do not produce an accepted catalog.

Quote matching establishes where the text came from. It does not independently prove that a number applies to the selected variant or that the quoted document is authoritative. Review those associations in the retained source. The function does not mark the target as tested, enable it for a task, or overwrite connection/probe evidence.

The source-URL field records the operator's citation. No claim of verified official-domain ownership, automated web research, live context-limit testing, price research, or task compatibility is made by this small catalog.

Run the offline consumer checks without any provider calls:

```text
python -m pytest tests/test_model_research.py -q
```
