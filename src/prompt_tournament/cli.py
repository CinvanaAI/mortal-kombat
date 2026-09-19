"""Synthetic, offline demonstration of the tournament mechanics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from .engine import Artifact, CandidateView, JudgeDecision, ModelRef, run_tournament


def _evaluate(model: ModelRef, artifact: Artifact) -> str:
    styles = {
        "careful": "Evidence first; state the boundary and verify the result.",
        "brief": "Verify it, then report it.",
        "verbose": "Begin with context, preserve the evidence, explain the boundary, and report verification.",
    }
    return f"{styles[model.model_id]} Source={artifact.source_text}"


def _judge(model_a: CandidateView, model_b: CandidateView) -> JudgeDecision:
    score_a = sum(len(text) for _, text in model_a.outputs)
    score_b = sum(len(text) for _, text in model_b.outputs)
    winner = "model_a_better" if score_a >= score_b else "model_b_better"
    return JudgeDecision(winner, "Synthetic demo ranks by captured output length.", 1.0)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    models = [
        ModelRef("Demo", "demo", "careful", "Demo : careful", 1.0, 2.0),
        ModelRef("Demo", "demo", "brief", "Demo : brief", 0.2, 0.4),
        ModelRef("Demo", "demo", "verbose", "Demo : verbose", 2.0, 4.0),
    ]
    result = run_tournament(
        prompt_id="synthetic_review",
        models=models,
        artifacts=[Artifact("fixture-1", "fixture.txt", "A synthetic benchmark artifact.")],
        evaluate=_evaluate,
        judge=_judge,
    )
    output = Path("demo-output") / "ranking.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8")
    print(f"Saved synthetic tournament: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

