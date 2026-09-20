# Changes

## 0.3.2 — Provider judging fixes

- Accept one decision JSON object inside a code fence or surrounding prose, while rejecting duplicate keys, multiple objects and invalid decision fields.
- Withhold configured candidate identities from the judge and randomly assign A/B once per whole-set comparison. Preserve the assignment, call sequence and presented winner, then map wins and disqualifications back to the tournament pair.
- Show that A/B assignment beside the judge's reason and link the decision to its recorded call. Earlier reports remain readable.
- Keep the equal-quality tie instruction explicit: choose displayed A and state that quality was equal. This adds no calls, retries or separate tie-breaking protocol; exact-field rules are unchanged.

## 0.3.1 — Rubric Rumble

- Give the project a new public identity while retaining existing commands, Python imports and saved-file formats.
- Expand the operating atlas to cover model preparation, all four run modes, failure paths and saved evidence.
- Put source examples and comparison evidence into the generated report's reading flow.
- Document current scope, related tools, and the original character-roster and animated-match ideas as future possibilities.
- Correct the distinction between capture-mode failures and tournament disqualification.

## 0.3.0 — Standalone workbench

- Add the portable desktop interface, connection discovery, explicit greeting probes and research from supplied documentation.
- Support Single and Batch capture, a two-candidate Battle, and Tournament mode.
- Present two complete historical comparisons separately from the synthetic first-run example.

## Earlier public continuation

The standalone task/provider/judge/report workflow grew around the retained tournament library. See [Background](docs/ORIGIN.md) for the distinction between the historical evaluator, its extracted core and the current application.
