# Background

Mortal Kombat grew from CinvanaAI's experiments with task-specific model comparison. Its tournament core was previously presented as Prompt Tournament Engine, extracted from the Active Prompt battle subsystem in Transcript Model Evaluator. That work has design ancestry through Skeleton and earlier system-building experiments.

This package keeps the original provider-neutral tournament implementation and public Python API. The complete task workflow adapts provider request/response ideas from Model Provider Compatibility Lab, judge request assembly from Transcript Model Evaluator, and their usage/rate handling. It supplies its own portable configuration, synthetic task fixtures and reports so it can be tried independently.

The historical implementations remain intact. This repository does not claim that the current public Skeleton rebuild contains this exact code. The earlier copyright notice is retained alongside the current project notice; the owner authorized MIT licensing for this release.
