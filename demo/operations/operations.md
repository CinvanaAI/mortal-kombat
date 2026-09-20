# Rubric Rumble: how the whole system runs

A source-linked atlas of the desktop/CLI workflow, preparation actions, capture and comparison modes, and saved evidence.

Behavioral source basis: `v0.3.2`. Public branding uses Rubric Rumble; retained compatibility identifiers are called out below. Report presentation follows the current source; behavior links are pinned to the reviewed snapshot.

[Open the complete operating map](00-overview.html) · [Offline replay](../) · [Historical battles](../history/)

## Start with the job you want to do

[Open the sequence](00-overview.html) · [Editable JSON](00-overview.sequence.json)

Rubric Rumble is a local desktop and command-line workbench for collecting model answers and comparing them against a task. Open `rubric-rumble gui` to load the offline starter task or a saved JSON task. The Task, Connections & candidates, Examples, Judge & rubric, Model research, and Run & results tabs describe different parts of that work.

The complete path is: choose candidates and examples, select an execution mode, validate and preview the request ceiling, explicitly execute, then inspect the saved results. Model discovery, greeting probes, and documented-capability research are optional preparation actions you invoke separately. They do not run just because the workbench opens.

The desktop keeps network work on a worker thread and reports results on the Tk thread. Editing and previewing do not call models. Its copied preview fixes the selected task and mode; changing either requires a new preview. The CLI exposes the same task workflow without opening a desktop.

The diagrams show call and data ownership from top to bottom. Conditional labels describe alternatives, not instructions to perform every branch. The text below gives the exact boundary for each view. On narrow screens, use the diagram canvas pan and zoom controls; the guide itself reads as a normal page.

Source: [Workbench](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L150) · [_preview](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L669) · [_run](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L687) · [main](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow_cli.py#L19)

## Find the models a connection actually lists

[Open the sequence](06-inventory.html) · [Editable JSON](06-inventory.sequence.json)

Save a named connection with its protocol, base URL, generation endpoint, and API-key **environment variable name**. The adapter reads that named environment value when explicitly invoked. It does not load credential files. OpenAI-compatible connections use HTTPS; loopback HTTP is allowed for local endpoints such as Ollama.

**Discover models** makes one GET request: `/models` for an OpenAI-compatible connection or `/api/tags` for Ollama. The adapter rejects malformed lists, validates every ID, and returns sorted unique identifiers. The CLI equivalent is `rubric-rumble models task.json --provider connection-name`.

Choose listed IDs to add candidates, or choose exactly one as a provider judge. A known manual ID can also be added or used as judge when model listing is unavailable. Editing the saved connection that produced the visible list clears that old list.

A listed ID means the connection exposed it. It does not establish text generation, a supported endpoint, token limits, task quality, or continued availability. Discovery does not launch greetings, research, retries, or a tournament.

Source: [_connection](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/providers.py#L60) · [list_models](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/providers.py#L102) · [_save_connection](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L495) · [_add_models](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L522)

## Observe a short response before running a larger task

[Open the sequence](07-probes.html) · [Editable JSON](07-probes.sequence.json)

Select one or more discovered models and choose **Probe selected**. Its preview gives the exact request count: one request for each selected model, run sequentially. After explicit confirmation, each request uses `Reply with exactly: hi` and an output ceiling of 32 tokens. Discovery alone never sends that prompt.

The CLI accepts repeated candidate IDs: `rubric-rumble probe task.json --candidate first --candidate second`. This prints a plan. Add `--execute --out new-probes` to execute, after the required key checks and a new output directory are reserved.

Every observation has its own status: `text-response`, `empty`, `incomplete`, or `failed`. A nonempty completed response qualifies as text-response even if it does not literally say “hi”. The adapter keeps an exact output prefix of at most 4096 characters and marks truncation. Returned token usage and completion metadata remain visible.

The desktop writes separate `probe-NNNN.json` records with the model, connection, endpoint and recording time. The CLI updates `probes.json` after each observation. A failed greeting does not cancel the remaining selected probes. These records show what happened to those requests; they are not a general capability certificate.

Source: [probe_model](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/providers.py#L184) · [execute_probes](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L109) · [_probe](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L569) · [main](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow_cli.py#L19)

## Keep documented facts separate from observed behavior

[Open the sequence](08-research.html) · [Editable JSON](08-research.sequence.json)

In **Model research**, provide a target model ID, a researcher connection and model, an official source URL, and the documentation text to inspect. The URL records provenance; this module does not fetch it or browse for sources. The target is the subject of the document. Only the configured researcher model receives the generation request.

After the one-request preview is accepted, the desktop reserves a new evidence file before calling the researcher. The module validates the supplied text and settings, then asks for context-window tokens, maximum output tokens, input modalities and output modalities. Unknown values must remain null. Source text is limited to 400 KB and returned research text to 200 KB.

A complete nonempty response must be one strict JSON object. Duplicate keys, unsupported fields, invalid values and unsupported modality labels fail validation. The target identity needs a source quote, and every non-null fact needs a verbatim supporting quote present in the supplied text.

The returned record keeps the supplied source and hash, quoted evidence, unknowns, researcher usage, raw response and target-association flag. Literal quotes prove textual provenance; they do not prove the model interpreted the quote correctly. An alias association remains visible for operator review. The timestamp records this receipt, not document publication.

The desktop saves `model-research.json` and shows the supported limits above the underlying evidence. It does not silently update candidate limits or test the target. On a research failure the desktop wrapper retains a sanitized failure record; the return-only API itself does not write files.

Source: [research_model](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/model_research.py#L127) · [_parse_response](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/model_research.py#L71) · [execute_research](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L87) · [_start_research](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L379)

## Validate a task, preview the request ceiling, then run

[Open the sequence](01-setup.html) · [Editable JSON](01-setup.sequence.json)

A task supplies instructions, source artifacts, candidate configurations, named connections, and a maximum provider-call count. Judged modes also require rules or a provider judge and a rubric. The validator rejects unsupported configuration fields, duplicate identities, invalid model counts, missing fixture outputs and malformed rates before execution.

A rules rubric lists exact field names, and every artifact must supply expected string values for those fields. A provider rubric is written comparison criteria sent with the full example set. Include desired weighting and tie-break instructions in that text; the program does not fabricate category scores.

The plan includes the normalized task fingerprint, selected mode, candidate and artifact counts, maximum candidate calls, maximum judge calls, configured shared ceiling, and whether a provider is required. For n candidates and a provider judge, the comparison ceiling is n × (n − 1) / 2. It is a maximum possible count, not a promised call total or a monetary quote.

CLI `rubric-rumble run task.json --mode battle` stops after the plan. Execution needs `--execute --out new-results`. In the desktop, Run checks the current selection against the frozen preview and requires its explicit provider-call checkbox when needed. Both reserve a new result directory before executing.

`run_task` revalidates, recomputes the plan, rejects required network access without permission, and checks every required candidate key and any used provider-judge key before the first call. Only then does it initialize the run report. A preflight failure therefore produces an error before a result dictionary exists; a wrapper may already have reserved an empty output folder.

Source: [validate_task](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/task.py#L26) · [plan_task](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/task.py#L140) · [execute_preview](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L51) · [run_task](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow.py#L53)

## Choose between capturing answers and judging them

[Open the sequence](09-modes.html) · [Editable JSON](09-modes.sequence.json)

The selected mode changes the work performed, not just the report title. Desktop selection determines the candidates copied into the task. The CLI uses the candidates listed in the task file; it does not silently choose the first candidate to satisfy a mode.

Single and Batch attempt every requested candidate/artifact pair. They do not call an unused judge, assess exact-field quality, create decisions or infer a ranking from successful execution. Individual errors are recorded and capture continues. Batch is sequential local application work, not a provider’s discounted Batch API.

Battle and Tournament share the core evaluation and insertion algorithm. Battle requires two candidates; if evaluation removes a candidate, no pairwise judgment may occur. Tournament requires at least two candidates and can compare surviving pairs as insertion needs them.

| Mode | Candidate selection | Behavior |
| --- | --- | --- |
| Single | Exactly one | Capture its responses; no judge or ranking |
| Batch | One or more | Capture each candidate’s responses; no judge or ranking |
| Battle | Exactly two | Evaluate, then compare survivors once when possible |
| Tournament | Two or more | Evaluate, then build a judged insertion ranking |

Source: [validate_task](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/task.py#L26) · [select_task](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workbench.py#L29) · [run_task](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow.py#L53)

## Capture each answer with its source and call evidence

[Open the sequence](02-candidates.html) · [Editable JSON](02-candidates.sequence.json)

For one candidate and artifact, the evaluation callback combines the task instructions with the source text and creates a started call record. Fixture candidates supply their configured synthetic text. A live candidate first checks the shared provider-call ceiling, then sends one request through the selected adapter. The same ceiling includes candidate and judge calls.

OpenAI Responses uses `/responses`, explicitly selected Chat Completions uses `/chat/completions`, and Ollama uses `/api/chat`. The adapter normalizes answer text, returned model, usage and completion information. HTTP errors and connection failures are bounded; raw authorization headers and provider error bodies are not copied into those error messages.

The workflow stores the returned response before estimating its token cost. Incomplete or empty output becomes failed evidence. In a judged rules run, exact-field assessment is also stored; a response that is not a JSON object disqualifies that candidate and skips its remaining artifacts. Missing or incorrect string fields reduce the score without automatically disqualifying a valid object.

The callback returns answer text. In judged modes, the core owns its successful text cache and creates complete CandidateViews. All candidate evaluation finishes before ladder comparison starts. The complete workflow gives the core a fresh cache, so it does not reuse a previous run’s answers.

Source: [execute](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow.py#L74) · [evaluate](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow.py#L104) · [call_provider](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/providers.py#L167) · [normalize_response](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/providers.py#L130) · [run_tournament](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/engine.py#L205)

## Judge the whole answer set under the chosen rubric

[Open the sequence](04-judging.html) · [Editable JSON](04-judging.sequence.json)

The core calls the judge with candidate A and incumbent B. Each view contains that candidate’s answer for every completed source artifact. The rules path totals exact, case-sensitive expected-field matches across the set. More matches win; equal totals choose the lexically smaller candidate ID and record that this is a deterministic tie-break rather than a quality difference.

The provider path randomly assigns the two complete answer sets to displayed A and B. It sends the task, rubric, every source, any expected values, and both output columns without adding candidate IDs or model metadata. Source or output text can still reveal identity. One request produces one whole-set judgment. The assignment is saved locally before the call, including when the call fails.

A provider decision may be plain JSON or one JSON object inside prose or a code fence. Its winner must be supported, short_reason must be a nonempty string, and optional confidence must be null or a finite number from zero to one. Duplicate keys, competing objects, malformed JSON and invalid fields fail. Outcomes remain model_a_better, model_b_better, model_a_disqualified, model_b_disqualified, or both_disqualified.

The workflow saves the displayed A/B assignment, exact call link and raw verdict, then maps that verdict back to the core’s candidate order, including disqualification. The report shows the judge’s assignment beside its explanation. Equal quality still requires a choice: the judge is instructed to choose displayed A and identify the tie-break; random assignment therefore makes equal-quality placement random. One randomized call does not eliminate position effects. Failed or malformed judgments stop the ranking with their evidence retained.

Source: [build_judge_request](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow.py#L27) · [judge](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow.py#L118) · [parse_provider_decision](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/judging.py#L26) · [run_tournament](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/engine.py#L205)

## Insert survivors according to recorded comparisons

[Open the sequence](03-ladder.html) · [Editable JSON](03-ladder.sequence.json)

The core first creates seed order and evaluates the candidates. Evaluation failures are marked disqualified; their remaining artifacts are skipped. The first surviving candidate starts an empty ladder. Each next survivor begins as A against the current incumbent B at the top position.

If A is better, it is inserted before B. If B is better, A advances to the next position and is appended at the end if it never wins. If A is disqualified, it is removed and its insertion stops. If B is disqualified, B is removed and A continues at that position. If both are disqualified, both are removed and A stops.

The next surviving seed repeats the process. The result contains the final ranking, battle records, disqualifications, successful evaluation count and cache-hit count. Comparisons occur as insertion needs them: every pair is possible in the worst case, but an all-pairs pass is not required.

This algorithm assumes the pairwise decisions are useful for building an order; it does not establish transitive quality or statistical significance. A different task, rubric, seed or judge can produce a different order. Configured token rates do not choose winners. In the full workflow the seed does not receive those rates.

Source: [seed_models](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/engine.py#L144) · [run_tournament](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/engine.py#L205) · [run_task](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow.py#L53)

## Read the result, including what failed or stayed unknown

[Open the sequence](05-evidence.html) · [Editable JSON](05-evidence.sequence.json)

Each recorded call includes its phase, candidate identity, request text, returned text, usage when available, completion or error, and an estimated cost or explicit reason that estimation is unavailable. Captured outputs, rules assessments, valid pairwise decisions and candidate summaries remain separate fields.

Capture status is completed when no requested output failed, failed when all failed, and partial otherwise. A returned judged result is completed if it has a ranking, or no-ranked-candidates if none remain. An exception from judging or the outer run becomes failed evidence. Candidate disqualification alone does not make a completed surviving ranking a failed run.

When judging raises, earlier call records, captured outputs and already accepted decisions remain in the report, but the core does not return its partial ladder. The report therefore leaves tournament null. It does not reconstruct or invent an intermediate ranking.

Cost is estimated from returned input/output counts and explicitly configured rates with currency, source and as-of date. Positive cached-input counts require a cache rate; an explicit zero does not. If a cache rate is supplied but cache usage is absent, the estimate is unavailable. Positive cache-write counts are also unavailable because this estimator does not price them.

Missing rates, incomplete usage or inconsistent cached counts also leave cost unknown. Available amounts are subtotaled by candidate/judge phase and currency; omitted attempted calls are counted. Hardware, energy, subscriptions and provider invoices are not inferred. These monetary estimates never enter the judge’s winner decision.

The wrapper saves result.json and report.html in the new folder. The HTML escapes captured text and links to the complete evidence. `rubric-rumble report result.json --out another-new-folder` renders saved evidence without running a task or contacting a provider.

Source: [run_task](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow.py#L53) · [estimate_cost](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/providers.py#L210) · [Report rendering and saving](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/report.py) · [main](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/workflow_cli.py#L19)

## Understand what the retained core does for a caller

[Open the sequence](10-core-api.html) · [Editable JSON](10-core-api.sequence.json)

The `prompt_tournament` Python API remains usable independently of the complete task workflow. `run_tournament` accepts ModelRefs, Artifacts, an evaluate callback returning text, and a judge callback returning JudgeDecision. Its TournamentResult contains ranking/battles/disqualifications and counts; it does not embed a complete captured-output ledger or save a report for you.

A caller may pass prior ranking, a reusable text cache and a judge_model to exclude by identity. Seed order puts known-ranked candidates first, new candidates next and previously disqualified candidates last. New candidates with both price fields use their summed price in descending order for seeding, followed by stable provider/model ordering. This affects who is compared first, not the result of a comparison.

The cache key includes prompt_id, model identity, artifact ID, filename and source text. The caller owns the meaning and validity of cached text and must change prompt_id when other task context changes. The complete workflow supplies a task fingerprint in its prompt ID, a fresh cache, no prior ranking, no judge-model exclusion argument and no price metadata on its ModelRefs.

The retained legacy parse_judge_output helper keeps its historical coercion and confidence-clamping behavior. The complete workflow uses the separate strict parse_provider_decision boundary and remaps its randomized displayed A/B verdict for the core. Direct core callers remain responsible for their own callbacks, presentation order, evidence and stricter contracts.

Rubric Rumble is the public name and preferred command. Existing mortal-kombat commands, prompt_tournament imports and mortal-kombat.* JSON schema identifiers remain compatibility surfaces.

Source: [run_tournament](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/engine.py#L205) · [_cache_key](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/engine.py#L190) · [_new_candidate_key](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/engine.py#L183) · [parse_judge_output](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/engine.py#L112) · [parse_provider_decision](https://github.com/CinvanaAI/rubric-rumble/blob/v0.3.2/src/prompt_tournament/judging.py#L26)

## Inspect a complete record and reproduce a safe first run

Run `rubric-rumble demo --out a-new-demo-folder` for the bundled deterministic extraction fixture. It exercises complete, incomplete and malformed candidate outputs with transparent rules and no provider requests. [Open the recorded offline replay](../) or [inspect the captured result JSON](recorded-example.json).

The [historical battle showcase](../history/) preserves two selected March 2026 model comparisons with their source examples, original answers, rubric and whole-battle judge decisions. Its [historical flow companion](../history/historical-flow.html) describes the preserved source version. Historical output resolution occurred inside each battle; the current complete workflow evaluates candidates before its insertion loop.

Historical records, current source behavior and synthetic demonstration are different evidence. This atlas explains the current complete implementation and retained core boundary. It does not claim an animation, a recovered continuous tournament replay, or quality-per-dollar validation.

Source: [Current package instructions](https://github.com/CinvanaAI/rubric-rumble#readme) · [Editable diagram sources](https://github.com/CinvanaAI/rubric-rumble/tree/main/demo/operations) · [Source map](source-evidence.json)
