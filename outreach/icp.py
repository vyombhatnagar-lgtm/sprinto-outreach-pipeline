"""ICP scorecard and evidence map (config/icp.yaml) and the decision rule.

The LLM never decides the verdict. It assigns a status per criterion, backed by
profile fields; `decide()` applies a fixed rule that is stored next to the
result. "Is there enough to judge?" is answered in code from the evidence map
(outreach/research.py), not by asking the model (L4 slide 30).
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from .models import CriterionScore

UNKNOWN_POLICIES = ("manual_review", "assume_met_flag", "zero_flag")
UNANSWERED_POLICIES = ("assume_gap_and_flag", "manual_review", "qualify_lower_and_flag")


@dataclass(frozen=True)
class Criterion:
    id: str
    weight: float
    question: str
    met_when: str
    gate: bool = False
    if_unknown: str = "zero_flag"
    fields: Tuple[str, ...] = ()
    partial_when: Optional[str] = None
    not_met_when: Optional[str] = None
    origin: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    fields_any: Tuple[str, ...]
    ladder: Tuple[str, ...]
    limit: int
    if_unanswered: str
    short_circuit: Optional[str] = None
    origin: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Scorecard:
    criteria: Tuple[Criterion, ...]
    questions: Tuple[Question, ...]
    max_fetches: int
    go_threshold: float
    max_unknown_share: float
    points: Dict[str, float]

    @property
    def ids(self) -> List[str]:
        return [c.id for c in self.criteria]

    def get(self, criterion_id: str) -> Criterion:
        for c in self.criteria:
            if c.id == criterion_id:
                return c
        raise KeyError(criterion_id)


def load_scorecard(path: Path) -> Scorecard:
    raw = yaml.safe_load(path.read_text())
    criteria = tuple(
        Criterion(
            id=c["id"], weight=float(c.get("weight", 0)), question=c["question"], met_when=c["met_when"],
            gate=bool(c.get("gate", False)), if_unknown=c.get("if_unknown", "zero_flag"),
            fields=tuple(c.get("fields", [])), partial_when=c.get("partial_when"),
            not_met_when=c.get("not_met_when"), origin=tuple(c.get("origin", [])),
        )
        for c in raw["criteria"]
    )
    ids = [c.id for c in criteria]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate criterion ids in ICP config")
    for c in criteria:
        if c.if_unknown not in UNKNOWN_POLICIES:
            raise ValueError(f"{c.id}: if_unknown must be one of {UNKNOWN_POLICIES}")
    em = raw["evidence_map"]
    questions = tuple(
        Question(
            id=q["id"], question=q["question"], fields_any=tuple(q["fields_any"]), ladder=tuple(q["ladder"]),
            limit=int(q["limit"]), if_unanswered=q["if_unanswered"], short_circuit=q.get("short_circuit"),
            origin=tuple(q.get("origin", [])),
        )
        for q in em["questions"]
    )
    for q in questions:
        if q.if_unanswered not in UNANSWERED_POLICIES:
            raise ValueError(f"{q.id}: if_unanswered must be one of {UNANSWERED_POLICIES}")
    d = raw["decision"]
    return Scorecard(
        criteria=criteria, questions=questions, max_fetches=int(em["max_fetches_beyond_home"]),
        go_threshold=float(d["go_threshold"]), max_unknown_share=float(d["max_unknown_share"]),
        points={k: float(v) for k, v in d["points"].items()},
    )


@dataclass(frozen=True)
class Decision:
    decision: str  # GO | GO_FLAGGED | NO_GO | MANUAL_REVIEW
    weighted_score: float
    unknown_weight_share: float
    rule: str
    flags: List[str]
    unknown_criteria: List[str]


def rule_text(card: Scorecard) -> str:
    gates = [c.id for c in card.criteria if c.gate]
    return (
        f"Short-circuit NO_GO if a stop condition is hit while researching. "
        f"Gates {gates}: not_met -> NO_GO. "
        f"Unknown criteria follow their if_unknown policy (manual_review -> MANUAL_REVIEW; "
        f"assume_met_flag -> counted met and flagged; zero_flag -> counted 0 and flagged). "
        f"Unknown weight share > {card.max_unknown_share} -> MANUAL_REVIEW. "
        f"Otherwise weighted score >= {card.go_threshold} -> GO (GO_FLAGGED if anything is flagged), else NO_GO."
    )


def decide(card: Scorecard, scores: List[CriterionScore], short_circuit: Optional[str] = None,
           extra_flags: Optional[List[str]] = None) -> Decision:
    by_id = {s.criterion_id: s for s in scores}
    missing = [cid for cid in card.ids if cid not in by_id]
    if missing:
        raise ValueError(f"Scores missing for criteria: {missing}")

    rule = rule_text(card)
    flags = list(extra_flags or [])
    unknown = [c.id for c in card.criteria if by_id[c.id].status == "unknown"]
    total_weight = sum(c.weight for c in card.criteria) or 1.0
    unknown_share = round(sum(c.weight for c in card.criteria if c.id in unknown) / total_weight, 3)

    earned = 0.0
    for c in card.criteria:
        status = by_id[c.id].status
        if status == "unknown":
            if c.if_unknown == "assume_met_flag":
                earned += c.weight * card.points["met"]
                flags.append(f"{c.id}: not confirmed, assumed met")
            elif c.if_unknown == "zero_flag":
                flags.append(f"{c.id}: unknown, counted as 0")
        else:
            earned += c.weight * card.points.get(status, 0.0)
    score = round(earned / total_weight, 3)

    def out(verdict: str) -> Decision:
        return Decision(verdict, score, unknown_share, rule, flags, unknown)

    if short_circuit:
        return out("NO_GO")
    for c in card.criteria:
        if c.gate and by_id[c.id].status == "not_met":
            return out("NO_GO")
    if any(by_id[c.id].status == "unknown" and c.if_unknown == "manual_review" for c in card.criteria):
        flags.append("a gate criterion could not be answered from public pages")
        return out("MANUAL_REVIEW")
    if unknown_share > card.max_unknown_share:
        flags.append(f"{unknown_share:.0%} of the scorecard weight is unknown")
        return out("MANUAL_REVIEW")
    if score >= card.go_threshold:
        return out("GO_FLAGGED" if flags else "GO")
    return out("NO_GO")
