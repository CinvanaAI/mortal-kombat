# Local output and configured execution

The demo is offline. Planning a task makes no provider call. Executing a configured live task sends its source and prompts to the explicitly configured endpoints; a provider judge also receives candidate outputs.

Credentials are read only from named environment variables. Task files reject inline keys and provider URLs with credentials, query strings or fragments. HTTP is limited to loopback addresses; redirects are refused. Returned error bodies and authorization headers are not written to the report.

Result bundles deliberately retain task text, exact outputs and usage evidence. Keep them private until reviewed. HTML escapes all captured text, loads no remote assets and does not execute model output. Runtime reports and environments are ignored by Git.

The call count and output-token limits bound parts of execution; they are not guarantees about a provider's final invoice. The tool makes no automatic retries. Unknown costs remain unknown.
