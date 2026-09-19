"""Pure ladder-tournament mechanics with injectable evaluation and judging."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable, MutableMapping


WINNERS = (
    "model_a_better",
    "model_b_better",
    "model_a_disqualified",
    "model_b_disqualified",
    "both_disqualified",
)


@dataclass(frozen=True)
class ModelRef:
    provider: str
    provider_key: str
    model_id: str
    display_label: str
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.provider_key, self.model_id)


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    filename: str
    source_text: str


@dataclass(frozen=True)
class CandidateView:
    model: ModelRef
    outputs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class JudgeDecision:
    winner: str
    short_reason: str
    confidence: float | None


@dataclass(frozen=True)
class BattleRecord:
    battle_id: str
    model_a: ModelRef
    model_b: ModelRef
    decision: JudgeDecision


@dataclass(frozen=True)
class Disqualification:
    model: ModelRef
    reason: str


@dataclass(frozen=True)
class TournamentResult:
    prompt_id: str
    ranking: tuple[ModelRef, ...]
    disqualified: tuple[Disqualification, ...]
    battles: tuple[BattleRecord, ...]
    cache_hits: int
    evaluations: int

    def as_dict(self) -> dict[str, Any]:
        active_entries = [
            {"rank": index, "status": "Ranked", **asdict(model)}
            for index, model in enumerate(self.ranking, start=1)
        ]
        disqualified_entries = [
            {
                "rank": len(active_entries) + index,
                "status": "Disqualified",
                **asdict(entry.model),
                "reason": entry.reason,
            }
            for index, entry in enumerate(self.disqualified, start=1)
        ]
        return {
            "prompt_id": self.prompt_id,
            "current_ranking": active_entries + disqualified_entries,
            "battles": [
                {
                    "battle_id": battle.battle_id,
                    "model_a": asdict(battle.model_a),
                    "model_b": asdict(battle.model_b),
                    "decision": asdict(battle.decision),
                }
                for battle in self.battles
            ],
            "cache_hits": self.cache_hits,
            "evaluations": self.evaluations,
        }


Evaluator = Callable[[ModelRef, Artifact], str]
Judge = Callable[[CandidateView, CandidateView], JudgeDecision]


def parse_judge_output(raw_output: str | None) -> JudgeDecision:
    """Parse a strict decision from plain JSON or a response containing JSON."""

    if raw_output is None or not raw_output.strip():
        raise ValueError("judge returned no output")
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        start, end = raw_output.find("{"), raw_output.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("judge output did not contain JSON")
        try:
            payload = json.loads(raw_output[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("judge output JSON could not be parsed") from exc
    if not isinstance(payload, dict):
        raise ValueError("judge output must be an object")
    winner = str(payload.get("winner", "")).strip()
    if winner not in WINNERS:
        raise ValueError(f"winner must be one of: {', '.join(WINNERS)}")
    reason = str(payload.get("short_reason", "")).strip() or "No reason provided."
    raw_confidence = payload.get("confidence")
    if raw_confidence in (None, ""):
        confidence = None
    else:
        try:
            confidence = max(0.0, min(1.0, float(raw_confidence)))
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence must be numeric") from exc
    return JudgeDecision(winner=winner, short_reason=reason, confidence=confidence)


def seed_models(
    models: list[ModelRef],
    prior_ranking: list[dict[str, Any]] | None = None,
) -> list[ModelRef]:
    """Order known-ranked, new, then previously disqualified candidates."""

    active: dict[tuple[str, str], int] = {}
    disqualified: dict[tuple[str, str], int] = {}
    for entry in prior_ranking or []:
        pair = (str(entry.get("provider_key", "")), str(entry.get("model_id", "")))
        try:
            rank = int(entry.get("rank", 0))
        except (TypeError, ValueError):
            continue
        if not all(pair) or rank <= 0:
            continue
        target = disqualified if entry.get("status") == "Disqualified" else active
        target[pair] = rank

    unique: list[ModelRef] = []
    seen: set[tuple[str, str]] = set()
    for model in models:
        if model.key not in seen:
            unique.append(model)
            seen.add(model.key)

    fallback = sorted(unique, key=_new_candidate_key)
    fallback_positions = {model.key: index for index, model in enumerate(fallback)}

    def key(model: ModelRef) -> tuple[int, int]:
        if model.key in active:
            return (0, active[model.key])
        if model.key in disqualified:
            return (2, disqualified[model.key])
        return (1, fallback_positions[model.key])

    return sorted(unique, key=key)


def _new_candidate_key(model: ModelRef) -> tuple[int, float, str, str]:
    if model.input_cost_per_million is None or model.output_cost_per_million is None:
        return (1, 0.0, model.provider.casefold(), model.model_id.casefold())
    total = model.input_cost_per_million + model.output_cost_per_million
    return (0, -total, model.provider.casefold(), model.model_id.casefold())


def _cache_key(prompt_id: str, model: ModelRef, artifact: Artifact) -> str:
    payload = json.dumps(
        {
            "prompt_id": prompt_id,
            "model": model.key,
            "artifact_id": artifact.artifact_id,
            "filename": artifact.filename,
            "source_text": artifact.source_text,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_tournament(
    *,
    prompt_id: str,
    models: list[ModelRef],
    artifacts: list[Artifact],
    evaluate: Evaluator,
    judge: Judge,
    prior_ranking: list[dict[str, Any]] | None = None,
    cache: MutableMapping[str, str] | None = None,
    judge_model: ModelRef | None = None,
) -> TournamentResult:
    """Evaluate candidates once, then insert them into a judged ladder."""

    if not prompt_id.strip():
        raise ValueError("prompt_id is required")
    if not artifacts:
        raise ValueError("at least one artifact is required")
    candidates = [model for model in models if judge_model is None or model.key != judge_model.key]
    candidates = seed_models(candidates, prior_ranking)
    if len(candidates) < 2:
        raise ValueError("at least two non-judge candidates are required")

    output_cache: MutableMapping[str, str] = cache if cache is not None else {}
    views: dict[tuple[str, str], CandidateView] = {}
    disqualified: list[Disqualification] = []
    disqualified_keys: set[tuple[str, str]] = set()
    cache_hits = 0
    evaluations = 0

    for model in candidates:
        outputs: list[tuple[str, str]] = []
        try:
            for artifact in artifacts:
                key = _cache_key(prompt_id, model, artifact)
                if key in output_cache:
                    text = output_cache[key]
                    cache_hits += 1
                else:
                    text = evaluate(model, artifact)
                    if not isinstance(text, str) or not text.strip():
                        raise ValueError("candidate returned no output")
                    output_cache[key] = text
                    evaluations += 1
                outputs.append((artifact.artifact_id, text))
        except Exception as exc:
            disqualified.append(Disqualification(model, f"evaluation failed: {type(exc).__name__}: {exc}"))
            disqualified_keys.add(model.key)
            continue
        views[model.key] = CandidateView(model=model, outputs=tuple(outputs))

    ladder: list[ModelRef] = []
    battles: list[BattleRecord] = []

    def disqualify(model: ModelRef, reason: str) -> None:
        if model.key not in disqualified_keys:
            disqualified.append(Disqualification(model, reason))
            disqualified_keys.add(model.key)
        ladder[:] = [entry for entry in ladder if entry.key != model.key]

    for candidate in candidates:
        if candidate.key in disqualified_keys:
            continue
        if not ladder:
            ladder.append(candidate)
            continue
        position = 0
        inserted = False
        while position < len(ladder):
            incumbent = ladder[position]
            decision = judge(views[candidate.key], views[incumbent.key])
            if decision.winner not in WINNERS:
                raise ValueError(f"judge returned invalid winner: {decision.winner}")
            battles.append(
                BattleRecord(
                    battle_id=f"battle-{len(battles) + 1:04d}",
                    model_a=candidate,
                    model_b=incumbent,
                    decision=decision,
                )
            )
            if decision.winner == "model_a_disqualified":
                disqualify(candidate, decision.short_reason)
                inserted = True
                break
            if decision.winner == "model_b_disqualified":
                disqualify(incumbent, decision.short_reason)
                continue
            if decision.winner == "both_disqualified":
                disqualify(candidate, decision.short_reason)
                disqualify(incumbent, decision.short_reason)
                inserted = True
                break
            if decision.winner == "model_a_better":
                ladder.insert(position, candidate)
                inserted = True
                break
            position += 1
        if not inserted and candidate.key not in disqualified_keys:
            ladder.append(candidate)

    return TournamentResult(
        prompt_id=prompt_id,
        ranking=tuple(ladder),
        disqualified=tuple(disqualified),
        battles=tuple(battles),
        cache_hits=cache_hits,
        evaluations=evaluations,
    )

