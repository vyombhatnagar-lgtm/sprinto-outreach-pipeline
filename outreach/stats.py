"""Dashboard numbers, computed from stored step records (no model calls)."""
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable

VERDICTS = ("GO", "GO_FLAGGED", "NO_GO", "MANUAL_REVIEW")


def summarize(records: Iterable[Any]) -> Dict[str, Any]:
    verdicts: Counter = Counter()
    per_run: Dict[str, Counter] = defaultdict(Counter)
    scores, contacts, drafts, sent = [], 0, 0, 0
    for r in records:
        if r.step == "qualify" and r.status == "ok":
            q = (r.output or {}).get("qualification", {})
            v = q.get("decision")
            if v in VERDICTS:
                verdicts[v] += 1
                per_run[r.run_id][v] += 1
                scores.append(float(q.get("weighted_score", 0)))
        elif r.step == "poc" and r.status == "ok" and (r.output or {}).get("chosen"):
            contacts += 1
        elif r.step == "draft" and r.status == "ok":
            drafts += 1
            per_run[r.run_id]["drafts"] += 1
        elif r.step == "send" and r.status == "ok":
            sent += 1
    analysed = sum(verdicts.values())
    go = verdicts["GO"] + verdicts["GO_FLAGGED"]
    return {
        "analysed": analysed,
        "go": go,
        "go_rate": round(100 * go / analysed) if analysed else 0,
        "review": verdicts["MANUAL_REVIEW"],
        "no_go": verdicts["NO_GO"],
        "avg_score": round(100 * sum(scores) / len(scores)) if scores else 0,
        "contacts": contacts,
        "drafts": drafts,
        "sent": sent,
        "verdicts": {v: verdicts[v] for v in VERDICTS},
        "per_run": {k: dict(v) for k, v in per_run.items()},
    }
