"""Evidence-based weights: does the trust score predict real incidents?

Labels come from an incident log (restatements, executive disputes, decisions taken
on a wrong number). For each score component we measure how well a low value
predicts an incident (AUC: 0.5 = coin flip, 1.0 = perfect), then suggest weights
that lean towards the components with signal, shrunk towards the current weights
so a small sample cannot swing them wildly.
"""

from __future__ import annotations

from .scoring import MTS_WEIGHTS

SHRINKAGE = 0.5  # 0 = trust only the data, 1 = keep current weights
MIN_WEIGHT = 0.05


def auc(scores_pos: list[float], scores_neg: list[float]) -> float | None:
    """Probability that a random incident metric scores LOWER than a random clean one."""
    if not scores_pos or not scores_neg:
        return None
    wins = 0.0
    for p in scores_pos:
        for n in scores_neg:
            wins += 1.0 if p < n else 0.5 if p == n else 0.0
    return wins / (len(scores_pos) * len(scores_neg))


def calibrate(engine) -> dict:
    store = engine.store
    incident_metrics: dict[str, int] = {}
    for inc in store.incidents:
        if inc.metric_id in store.metrics:
            incident_metrics[inc.metric_id] = incident_metrics.get(inc.metric_id, 0) + 1
    ids = [m.id for m in store.metrics.values() if m.certification != "deprecated"]
    pos = [i for i in ids if i in incident_metrics]
    neg = [i for i in ids if i not in incident_metrics]
    weights = dict(engine.weights)

    comps = {}
    for key in MTS_WEIGHTS:
        raw = {i: next(c.raw for c in engine.metric_scores[i].components if c.key == key) for i in ids}
        comps[key] = auc([raw[i] for i in pos], [raw[i] for i in neg])

    def base(i: str, w: dict) -> float:
        return sum(w[c.key] * c.raw for c in engine.metric_scores[i].components)

    def penalty(i: str) -> float:
        return min(30.0, sum(-p["points"] for p in engine.metric_scores[i].penalties))

    def full(i: str, w: dict) -> float:
        return max(0.0, min(100.0, base(i, w) - penalty(i)))

    current_auc = auc([full(i, weights) for i in pos], [full(i, weights) for i in neg])

    signal = {k: max((a or 0.5) - 0.5, 0.0) for k, a in comps.items()}
    total = sum(signal.values())
    if total > 0:
        data_w = {k: v / total for k, v in signal.items()}
        suggested = {k: SHRINKAGE * weights[k] + (1 - SHRINKAGE) * data_w[k] for k in weights}
        suggested = {k: max(MIN_WEIGHT, v) for k, v in suggested.items()}
        norm = sum(suggested.values())
        suggested = {k: round(v / norm, 3) for k, v in suggested.items()}
        drift = round(1 - sum(suggested.values()), 3)  # rounding residue onto the largest weight
        top = max(suggested, key=suggested.get)
        suggested[top] = round(suggested[top] + drift, 3)
    else:
        suggested = dict(weights)
    suggested_auc = auc([full(i, suggested) for i in pos], [full(i, suggested) for i in neg])

    n = len(ids)
    caveat = (f"Based on {len(store.incidents)} incidents across {len(pos)} of {n} metrics. "
              + ("Directional only: collect at least 30 incident-tagged metrics before trusting the weights."
                 if len(pos) < 30 else "Sample is large enough to act on, with review."))
    return {
        "metrics": n,
        "metrics_with_incidents": len(pos),
        "incidents": len(store.incidents),
        "current_weights": weights,
        "current_auc": round(current_auc, 3) if current_auc is not None else None,
        "component_auc": {k: (round(v, 3) if v is not None else None) for k, v in comps.items()},
        "suggested_weights": suggested,
        "suggested_auc": round(suggested_auc, 3) if suggested_auc is not None else None,
        "recommendation": (
            "Suggested weights separate incident metrics better; apply and monitor."
            if (suggested_auc or 0) > (current_auc or 0) + 0.01 else
            "Current weights already separate incident metrics as well as the data supports; keep them."),
        "by_metric": sorted(
            [{"metric_id": i, "name": store.name_of(i), "score": engine.metric_scores[i].score,
              "incidents": incident_metrics.get(i, 0)} for i in ids],
            key=lambda r: r["score"]),
        "caveat": caveat,
    }
