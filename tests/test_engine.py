from __future__ import annotations

import pytest

from prompt_tournament import (
    Artifact,
    JudgeDecision,
    ModelRef,
    parse_judge_output,
    run_tournament,
    seed_models,
)


def model(name: str, cost: float | None = None) -> ModelRef:
    return ModelRef(
        provider="Demo",
        provider_key="demo",
        model_id=name,
        display_label=f"Demo : {name}",
        input_cost_per_million=cost,
        output_cost_per_million=cost,
    )


ARTIFACTS = [Artifact("one", "one.txt", "synthetic source")]


def test_judge_parser_extracts_json_and_clamps_confidence() -> None:
    decision = parse_judge_output(
        'Result: {"winner":"model_a_better","short_reason":"clearer","confidence":3}'
    )
    assert decision == JudgeDecision("model_a_better", "clearer", 1.0)


def test_judge_parser_rejects_unknown_winner() -> None:
    with pytest.raises(ValueError, match="winner must be"):
        parse_judge_output('{"winner":"tie"}')


def test_seed_order_preserves_active_then_new_then_disqualified() -> None:
    ordered = seed_models(
        [model("new-low", 1), model("old"), model("new-high", 5), model("dq")],
        [
            {"provider_key": "demo", "model_id": "old", "rank": 1, "status": "Ranked"},
            {"provider_key": "demo", "model_id": "dq", "rank": 2, "status": "Disqualified"},
        ],
    )
    assert [entry.model_id for entry in ordered] == ["old", "new-high", "new-low", "dq"]


def test_seed_order_deduplicates_candidates() -> None:
    assert [entry.model_id for entry in seed_models([model("a"), model("a"), model("b")])] == [
        "a",
        "b",
    ]


def test_ladder_insertion_records_each_comparison() -> None:
    scores = {"a": 1, "b": 3, "c": 2}

    def evaluate(candidate: ModelRef, artifact: Artifact) -> str:
        return f"{candidate.model_id}:{artifact.artifact_id}"

    def judge(left, right) -> JudgeDecision:
        winner = "model_a_better" if scores[left.model.model_id] > scores[right.model.model_id] else "model_b_better"
        return JudgeDecision(winner, "synthetic score", 1.0)

    result = run_tournament(
        prompt_id="p",
        models=[model("a"), model("b"), model("c")],
        artifacts=ARTIFACTS,
        evaluate=evaluate,
        judge=judge,
    )
    assert [entry.model_id for entry in result.ranking] == ["b", "c", "a"]
    assert [battle.battle_id for battle in result.battles] == [
        "battle-0001",
        "battle-0002",
        "battle-0003",
    ]


def test_cache_prevents_repeat_evaluation() -> None:
    calls = 0
    cache: dict[str, str] = {}

    def evaluate(candidate: ModelRef, artifact: Artifact) -> str:
        nonlocal calls
        calls += 1
        return candidate.model_id

    judge = lambda left, right: JudgeDecision("model_a_better", "synthetic", 1.0)
    first = run_tournament(
        prompt_id="p",
        models=[model("a"), model("b")],
        artifacts=ARTIFACTS,
        evaluate=evaluate,
        judge=judge,
        cache=cache,
    )
    second = run_tournament(
        prompt_id="p",
        models=[model("a"), model("b")],
        artifacts=ARTIFACTS,
        evaluate=evaluate,
        judge=judge,
        cache=cache,
    )
    assert first.evaluations == 2
    assert second.evaluations == 0
    assert second.cache_hits == 2
    assert calls == 2


def test_evaluation_failure_disqualifies_without_judging() -> None:
    def evaluate(candidate: ModelRef, artifact: Artifact) -> str:
        if candidate.model_id == "broken":
            raise RuntimeError("offline failure")
        return "ok"

    result = run_tournament(
        prompt_id="p",
        models=[model("broken"), model("a"), model("b")],
        artifacts=ARTIFACTS,
        evaluate=evaluate,
        judge=lambda left, right: JudgeDecision("model_a_better", "ok", 1.0),
    )
    assert [entry.model.model_id for entry in result.disqualified] == ["broken"]
    assert "evaluation failed" in result.disqualified[0].reason
    assert all("broken" not in (battle.model_a.model_id, battle.model_b.model_id) for battle in result.battles)


def test_judge_can_disqualify_incumbent() -> None:
    result = run_tournament(
        prompt_id="p",
        models=[model("a"), model("b")],
        artifacts=ARTIFACTS,
        evaluate=lambda candidate, artifact: "ok",
        judge=lambda left, right: JudgeDecision("model_b_disqualified", "invalid output", 0.9),
    )
    assert [entry.model_id for entry in result.ranking] == ["b"]
    assert [entry.model.model_id for entry in result.disqualified] == ["a"]


def test_judge_model_is_excluded_and_result_serializes_ranked_tail() -> None:
    judge_model = model("judge")
    result = run_tournament(
        prompt_id="p",
        models=[judge_model, model("a"), model("b")],
        artifacts=ARTIFACTS,
        evaluate=lambda candidate, artifact: "ok",
        judge=lambda left, right: JudgeDecision("model_a_disqualified", "bad", 1.0),
        judge_model=judge_model,
    )
    payload = result.as_dict()
    assert [entry["model_id"] for entry in payload["current_ranking"]] == ["a", "b"]
    assert [entry["status"] for entry in payload["current_ranking"]] == [
        "Ranked",
        "Disqualified",
    ]
    assert all(entry["model_id"] != "judge" for entry in payload["current_ranking"])

