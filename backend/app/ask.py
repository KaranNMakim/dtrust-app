"""Ask orchestrator (PRD 7.3): classify -> retrieve -> rank deterministically -> generate -> log.

The structured answer is always built from graph facts. Claude only writes the
`explanation` sentence(s); if it is unavailable a template sentence is used.
"""

from __future__ import annotations

import re
import time
import uuid

from .engine import TrustEngine, conflict_dict, score_dict

INTENTS = ("resolve_metric", "explain_score", "find_conflicts", "lineage", "recommendation_trust", "reconcile")


def classify(question: str) -> str:
    q = question.lower()
    if re.search(r"\brecommend|\bmodel\b|\bsuggest", q):
        return "recommendation_trust"
    if re.search(r"differ|don'?t match|do not match|mismatch|reconcile|disagree|gap between|\bvs\.?\b|versus|(higher|lower) than", q):
        return "reconcile"
    if re.search(r"\bwhy\b|\bexplain\b|\blow\b|\bdrop", q):
        return "explain_score"
    if re.search(r"conflict|duplicate|inconsisten|orphan|circular|cycle", q):
        return "find_conflicts"
    if re.search(r"lineage|where does .* come from|source of|upstream", q):
        return "lineage"
    return "resolve_metric"


def _match_term(engine: TrustEngine, text: str) -> str | None:
    q = text.lower()
    best, best_len = None, 0
    for g in engine.store.glossary.values():
        for cand in [g.term.lower(), *g.synonyms]:
            if cand and re.search(rf"\b{re.escape(cand)}\b", q) and len(cand) > best_len:
                best, best_len = g.id, len(cand)
    return best


def _match_metric(engine: TrustEngine, text: str) -> str | None:
    q = text.lower()
    best, best_len = None, 0
    for m in engine.store.metrics.values():
        for cand in {m.name.lower(), re.sub(r"\s*\(.*?\)", "", m.name.lower()).strip(), m.id}:
            if cand and cand in q and len(cand) > best_len:
                best, best_len = m.id, len(cand)
    return best


def _match_rec(engine: TrustEngine, text: str) -> str | None:
    q = text.lower()
    for r in engine.store.recommendations.values():
        if re.search(rf"\b{re.escape(r.id)}\b", q) or r.title.lower()[:30] in q:
            return r.id
    return None


def ask(engine: TrustEngine, question: str, llm=None) -> dict:
    t0 = time.perf_counter()
    intent = None
    if llm and llm.enabled:
        c = llm.classify(question)
        if c and c.get("intent") in INTENTS:
            intent = c["intent"]
    intent = intent or classify(question)

    if intent == "recommendation_trust":
        body = _recommendation(engine, question)
    elif intent == "reconcile" and (rb := _reconcile(engine, question)):
        body = rb
    elif intent == "find_conflicts":
        body = _conflicts(engine, question)
    elif intent == "explain_score" and _match_metric(engine, question):
        body = _explain(engine, question)
    elif intent == "lineage" and _match_metric(engine, question):
        body = _lineage(engine, question)
    else:
        intent = "resolve_metric"
        body = _resolve(engine, question)

    if llm and llm.enabled and body.get("facts"):
        generated = llm.answer(question, body["facts"])
        if generated:
            body["explanation"] = generated
            body["explanation_source"] = "claude"
    body.setdefault("explanation_source", "template")
    body.pop("facts", None)
    return {
        "answer_id": "ask_" + uuid.uuid4().hex[:8],
        "question": question,
        "intent": intent,
        **body,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
    }


# ---------------------------------------------------------------- intents

def _mentions(question: str, candidates: dict[str, list[str]]) -> list[str]:
    """Ids whose name variants appear in the question, ordered by first appearance."""
    q = question.lower()
    found: dict[str, int] = {}
    for cid, names in candidates.items():
        for n in names:
            i = q.find(n)
            if n and i >= 0 and (cid not in found or i < found[cid]):
                found[cid] = i
    # drop ids whose match is contained in a longer match at the same spot
    return [cid for cid, _ in sorted(found.items(), key=lambda kv: kv[1])]


def _reconcile(engine: TrustEngine, question: str) -> dict | None:
    from .reconcile import reconcile

    store = engine.store
    dash_names = {d.id: list({d.name.lower(), d.name.split(" - ")[0].lower().strip()}) for d in store.dashboards.values()}
    def variants(name: str) -> list[str]:
        stripped = re.sub(r"\s*\(.*?\)", "", name.lower()).strip()
        return [name.lower()] + ([stripped] if " " in stripped and stripped != name.lower() else [])

    metric_names = {m.id: variants(m.name) for m in store.metrics.values() if m.certification != "deprecated"}
    dashes = _mentions(question, dash_names)
    metrics = [m for m in _mentions(question, metric_names) if len(metric_names[m][0]) > 4]
    term_id = _match_term(engine, question)
    pair = None
    if len(dashes) >= 2:
        da, db = dashes[:2]

        def pick(did: str) -> str | None:
            shown = store.dashboards[did].metric_ids
            for mid in shown:
                if term_id and store.metrics[mid].glossary_term_id == term_id:
                    return mid
            return shown[0] if shown and not term_id else None

        ma, mb = pick(da), pick(db)
        if ma and mb:
            pair = (ma, mb, da, db)
    elif len(metrics) >= 2:
        pair = (metrics[0], metrics[1], None, None)
    elif len(metrics) == 1:
        m = store.metrics[metrics[0]]
        cert = [p for p in store.metrics_for_term(m.glossary_term_id or "") if p.certification == "certified" and p.id != m.id]
        if cert:
            pair = (m.id, cert[0].id, None, None)
    if not pair:
        return None
    rec = reconcile(store, *pair)
    return {"found": True, "reconciliation": rec, "confidence": 0.9 if rec["bridge"] else 0.75,
            "explanation": rec["summary"], "citations": [pair[0], pair[1], *(d for d in pair[2:] if d)],
            "facts": {"summary": rec["summary"], "causes": rec["causes"], "bridge": rec["bridge"]}}


def _owner(engine: TrustEngine, m) -> dict:
    return {"email": m.owner_email, "team": m.team,
            "name": _name_from_email(m.owner_email) if m.owner_email else None}


def _name_from_email(email: str) -> str:
    local = email.split("@")[0]
    return " ".join(p.capitalize() for p in re.split(r"[._]", local) if p)


def _resolve(engine: TrustEngine, question: str) -> dict:
    term_id = _match_term(engine, question)
    if not term_id:
        mid = _match_metric(engine, question)
        if mid and engine.store.metrics[mid].glossary_term_id:
            term_id = engine.store.metrics[mid].glossary_term_id
    if not term_id:
        return {"found": False, "confidence": 0.0,
                "explanation": "I could not match that question to a business term in the glossary. "
                               "Try naming the metric, e.g. 'Which revenue metric should I trust?'",
                "citations": []}

    store = engine.store
    g = store.glossary[term_id]
    members = [m for m in store.metrics_for_term(term_id) if m.certification != "deprecated"]

    def rank_key(m):
        exec_use = sum(d.audience == "exec" for d in store.consumers(m.id))
        return (m.certification != "certified", -engine.metric_scores[m.id].score, -exec_use)

    members.sort(key=rank_key)
    top, rivals = members[0], members[1:]
    ts = engine.metric_scores[top.id]
    lineage = engine.metric_lineage(top.id)
    path = lineage[0]["path"] if lineage else [top.name]

    second = engine.metric_scores[rivals[0].id].score if rivals else 0
    margin = ts.score - second
    coverage = 1.0 if lineage else 0.7
    confidence = round(min(0.99, coverage * (0.5 + min(margin, 50) / 50 * 0.5) + (0.05 if top.certification == "certified" else 0)), 2)

    conflict_ids = [c.id for c in engine.conflicts if c.status == "open" and top.id in c.entity_ids]
    rival_rows = []
    for r in rivals:
        rts = engine.metric_scores[r.id]
        rival_rows.append({
            "metric_id": r.id, "name": r.name, "formula": r.formula,
            "trust_score": rts.score, "zone": rts.zone,
            "owner": _owner(engine, r),
            "difference": _difference(engine, top, r),
            "used_in": len(store.consumers(r.id)),
        })

    cert_phrase = f"the certified {g.term} metric" if top.certification == "certified" else f"the highest-trust {g.term} metric (none is certified yet)"
    fresh = next((c for c in ts.components if c.key == "freshness"), None)
    explanation = (
        f"{top.name} is {cert_phrase}, owned by {top.team or 'an unassigned team'}. "
        f"It scores {ts.score:.0f}: {', '.join(_lc(c.evidence[0]) for c in ts.components if c.key in ('lineage', 'usage'))}"
        f"{'; ' + _lc(fresh.evidence[0]) if fresh else ''}. "
        f"{len(rivals)} other definition(s) of {g.term} are in use; prefer {top.name} for reporting."
    )
    facts = {
        "term": g.term, "glossary_definition": g.definition,
        "recommended": {**engine.metric_detail(top.id), "components": score_dict(ts, store)["components"],
                        "lineage": path},
        "rivals": rival_rows, "open_conflicts": conflict_ids,
    }
    return {
        "found": True,
        "term": g.term,
        "certified_metric": {
            "id": top.id, "name": top.name, "formula": top.formula,
            "owner": _owner(engine, top), "certification": top.certification,
            "trust_score": ts.score, "zone": ts.zone,
        },
        "lineage": path,
        "confidence": confidence,
        "explanation": explanation,
        "conflicts": rival_rows,
        "score_breakdown": {c.key: round(c.raw) for c in ts.components} | {
            "penalties": sum(p["points"] for p in ts.penalties)},
        "citations": [top.id, *(n for n in [top.data_product_id] if n), *conflict_ids],
        "facts": facts,
    }


def _lc(text: str) -> str:
    return text[:1].lower() + text[1:]


def _difference(engine: TrustEngine, ref, other) -> str:
    g = engine.store.glossary.get(other.glossary_term_id) if other.glossary_term_id else None
    notes = []
    if g:
        missing = [c for c in g.required_components if c not in other.formula_tokens]
        extra = sorted(other.formula_tokens - ref.formula_tokens)
        if missing:
            notes.append("omits " + ", ".join(missing))
        if extra:
            notes.append("uses " + ", ".join(extra[:3]))
    if not other.owner_email:
        notes.append("no owner")
    fresh = next(c for c in engine.metric_scores[other.id].components if c.key == "freshness")
    if fresh.raw < 100:
        notes.append("stale")
    return "; ".join(notes) or "different formula"


def _explain(engine: TrustEngine, question: str) -> dict:
    mid = _match_metric(engine, question)
    ts = engine.metric_scores[mid]
    sd = score_dict(ts, engine.store)
    return {"found": True, "metric_id": mid, "score": sd, "confidence": 0.95,
            "explanation": ts.explanation, "citations": [mid] + [p["conflict_id"] for p in ts.penalties],
            "facts": sd}


def _lineage(engine: TrustEngine, question: str) -> dict:
    mid = _match_metric(engine, question)
    paths = engine.metric_lineage(mid)
    m = engine.store.metrics[mid]
    if paths:
        p = paths[0]
        expl = f"{m.name} comes from {p['path'][0]} via {len(p['path']) - 2} intermediate step(s); {p['coverage']:.0%} of hops are documented."
    else:
        expl = f"No lineage is recorded for {m.name}."
    return {"found": bool(paths), "metric_id": mid, "lineage_paths": paths, "confidence": 0.9 if paths else 0.3,
            "explanation": expl, "citations": [mid], "facts": {"metric": m.name, "paths": paths}}


def _conflicts(engine: TrustEngine, question: str) -> dict:
    term_id = _match_term(engine, question)
    items = [c for c in engine.conflicts if c.status == "open"]
    if term_id:
        ids = {m.id for m in engine.store.metrics_for_term(term_id)}
        items = [c for c in items if ids & set(c.entity_ids)]
    crit = sum(c.severity == "critical" for c in items)
    expl = f"{len(items)} open conflict(s), {crit} critical. The largest is '{items[0].title}' affecting {items[0].blast_radius} dashboard(s)." if items else "No open conflicts match."
    data = [conflict_dict(c) for c in items[:10]]
    return {"found": bool(items), "conflicts_found": data, "confidence": 0.95, "explanation": expl,
            "citations": [c.id for c in items[:10]], "facts": {"conflicts": data}}


def _recommendation(engine: TrustEngine, question: str) -> dict:
    rid = _match_rec(engine, question)
    if not rid:
        recs = sorted(engine.rec_scores.values(), key=lambda s: s.score)
        rows = [score_dict(s, engine.store) for s in recs]
        return {"found": True, "recommendations": rows, "confidence": 0.9,
                "explanation": f"{sum(s.zone == 'red' for s in recs)} of {len(recs)} recommendations are untrusted. "
                               f"Lowest: {engine.store.name_of(recs[0].entity_id)} ({recs[0].score:.0f}).",
                "citations": [s.entity_id for s in recs], "facts": {"recommendations": rows}}
    ts = engine.rec_scores[rid]
    sd = score_dict(ts, engine.store)
    r = engine.store.recommendations[rid]
    return {"found": True, "recommendation_id": rid, "score": sd, "model_confidence": r.raw_confidence,
            "confidence": 0.95, "explanation": ts.explanation, "citations": [rid, *r.evidence], "facts": sd}
