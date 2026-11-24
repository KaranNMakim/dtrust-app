"""In-memory metadata store, loaded from CSV.

This is the demo-mode repository. The Postgres schema in infra/postgres/schema.sql
mirrors these structures one-to-one; a SQL-backed store implements the same
public attributes (see docs/ROADMAP.md).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import formula as fx
from .models import BusinessRule, Dashboard, GlossaryTerm, Incident, LineageEdge, Metric, Recommendation


def _blank(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _dt(v: str | None) -> datetime | None:
    v = _blank(v)
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@dataclass
class Store:
    glossary: dict[str, GlossaryTerm] = field(default_factory=dict)
    metrics: dict[str, Metric] = field(default_factory=dict)
    dashboards: dict[str, Dashboard] = field(default_factory=dict)
    lineage: list[LineageEdge] = field(default_factory=list)
    recommendations: dict[str, Recommendation] = field(default_factory=dict)
    rules: dict[str, BusinessRule] = field(default_factory=dict)
    node_names: dict[str, tuple[str, str]] = field(default_factory=dict)  # id -> (label, name)
    audit: list[dict] = field(default_factory=list)
    # Optional numeric context for reconciliation bridges (period -> column -> value)
    component_values: dict[str, dict[str, float]] = field(default_factory=dict)
    component_units: dict[str, str] = field(default_factory=dict)
    filter_impacts: list[dict] = field(default_factory=list)
    reported_values: list[dict] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)

    # ---------- loading ----------
    @classmethod
    def from_dir(cls, data_dir: Path) -> "Store":
        s = cls()
        for r in _read(data_dir / "glossary.csv"):
            s.add_glossary(r)
        for r in _read(data_dir / "metrics.csv"):
            s.add_metric(r)
        for r in _read(data_dir / "dashboards.csv"):
            s.add_dashboard(r)
        for r in _read(data_dir / "lineage.csv"):
            s.add_lineage(r)
        for r in _read(data_dir / "recommendations.csv"):
            s.add_recommendation(r)
        rules = data_dir / "business_rules.csv"
        if rules.exists():
            for r in _read(rules):
                s.rules[r["rule_id"]] = BusinessRule(r["rule_id"], r["name"], r["description"], r["severity"])
        if (data_dir / "component_values.csv").exists():
            for r in _read(data_dir / "component_values.csv"):
                s.component_values.setdefault(r["period"], {})[r["column"].lower()] = float(r["value"])
                s.component_units[r["period"]] = r.get("unit") or ""
        if (data_dir / "filter_impacts.csv").exists():
            for r in _read(data_dir / "filter_impacts.csv"):
                s.filter_impacts.append({**r, "excluded_value": float(r["excluded_value"])})
        if (data_dir / "reported_values.csv").exists():
            for r in _read(data_dir / "reported_values.csv"):
                s.reported_values.append({**r, "value": float(r["value"])})
        if (data_dir / "incidents.csv").exists():
            for r in _read(data_dir / "incidents.csv"):
                s.incidents.append(Incident(r["date"], r["metric_id"], r["type"], r.get("severity") or "medium",
                                            r.get("note") or ""))
        return s

    def add_glossary(self, r: dict[str, str]) -> None:
        g = GlossaryTerm(
            id=r["term_id"],
            term=r["term"],
            definition=r["definition"],
            steward_email=_blank(r.get("steward_email")),
            required_components=[c for c in (r.get("required_components") or "").split("|") if c],
            synonyms=[c.strip().lower() for c in (r.get("synonyms") or "").split("|") if c.strip()],
        )
        self.glossary[g.id] = g
        self.node_names[g.id] = ("GlossaryTerm", g.term)

    def add_metric(self, r: dict[str, str]) -> None:
        m = Metric(
            id=r["metric_id"],
            name=r["name"],
            formula=r["formula"],
            grain=r.get("grain") or "daily",
            owner_email=_blank(r.get("owner_email")),
            team=_blank(r.get("team")),
            glossary_term_id=_blank(r.get("glossary_term")),
            data_product_id=_blank(r.get("data_product")),
            certification=_blank(r.get("certification")) or "none",
            refresh_sla_hours=float(r.get("refresh_sla_h") or 24),
            last_refreshed=_dt(r.get("last_refreshed")),
            time_basis=_blank(r.get("time_basis")),
            calendar=_blank(r.get("calendar")),
            currency=_blank(r.get("currency")),
            hierarchy_version=_blank(r.get("hierarchy_version")),
        )
        m.formula_hash = fx.formula_hash(m.formula)
        m.formula_tokens = fx.data_tokens(m.formula)
        self.metrics[m.id] = m
        self.node_names[m.id] = ("Metric", m.name)
        if m.team:
            self.node_names[_team_id(m.team)] = ("Team", m.team)
        if m.data_product_id and m.data_product_id not in self.node_names:
            self.node_names[m.data_product_id] = ("DataProduct", m.data_product_id)

    def add_dashboard(self, r: dict[str, str]) -> None:
        overrides: dict[str, str] = {}
        for part in (r.get("local_overrides") or "").split("|"):
            if ":" in part:
                mid, expr = part.split(":", 1)
                overrides[mid.strip()] = expr.strip()
        d = Dashboard(
            id=r["dashboard_id"],
            name=r["name"],
            tool=r.get("tool") or "",
            audience=r.get("audience") or "team",
            owner_email=_blank(r.get("owner_email")),
            monthly_viewers=int(r.get("monthly_viewers") or 0),
            metric_ids=[m for m in (r.get("metrics") or "").split("|") if m],
            local_overrides=overrides,
        )
        self.dashboards[d.id] = d
        self.node_names[d.id] = ("Dashboard", d.name)

    def add_lineage(self, r: dict[str, str]) -> None:
        e = LineageEdge(
            from_type=r["from_type"], from_id=r["from_id"], from_name=r["from_name"],
            relation=r["relation"], to_type=r["to_type"], to_id=r["to_id"], to_name=r["to_name"],
            documented=(r.get("documented") or "true").strip().lower() == "true",
        )
        self.lineage.append(e)
        self.node_names[e.from_id] = (e.from_type, e.from_name)
        self.node_names[e.to_id] = (e.to_type, e.to_name)

    def add_recommendation(self, r: dict[str, str]) -> None:
        feats: dict[str, float] = {}
        for part in (r.get("input_features") or "").split("|"):
            if ":" in part:
                k, w = part.split(":", 1)
                feats[k.strip()] = float(w)
        rec = Recommendation(
            id=r["rec_id"], model=r["model"], version=r.get("version") or "",
            title=r["title"], raw_confidence=float(r.get("raw_confidence") or 0),
            input_features=feats,
            evidence=[e for e in (r.get("evidence") or "").split("|") if e],
            rationale=(r.get("rationale") or "").strip(),
            accepted_90d=int(r.get("accepted_90d") or 0),
            success_90d=int(r.get("success_90d") or 0),
            rule_violations=[v for v in (r.get("rule_violations") or "").split("|") if v],
        )
        self.recommendations[rec.id] = rec
        self.node_names[rec.id] = ("Recommendation", rec.title)
        model_id = model_node_id(rec.model, rec.version)
        self.node_names[model_id] = ("Model", f"{rec.model} {rec.version}".strip())

    # ---------- derived lookups ----------
    def consumers(self, metric_id: str) -> list[Dashboard]:
        return [d for d in self.dashboards.values() if metric_id in d.metric_ids]

    def metrics_for_term(self, term_id: str) -> list[Metric]:
        return [m for m in self.metrics.values() if m.glossary_term_id == term_id]

    def upstream_edges(self) -> dict[str, list[LineageEdge]]:
        out: dict[str, list[LineageEdge]] = defaultdict(list)
        for e in self.lineage:
            if e.relation == "DEPENDS_ON":
                out[e.from_id].append(e)
        return out

    def exists(self, node_id: str) -> bool:
        return node_id in self.node_names

    def name_of(self, node_id: str) -> str:
        return self.node_names.get(node_id, ("", node_id))[1]

    def label_of(self, node_id: str) -> str:
        return self.node_names.get(node_id, ("Unknown", node_id))[0]


def _team_id(team: str) -> str:
    return "team_" + "".join(ch.lower() if ch.isalnum() else "_" for ch in team).strip("_")


def team_id(team: str) -> str:
    return _team_id(team)


def model_node_id(model: str, version: str) -> str:
    return "model_" + "".join(ch.lower() if ch.isalnum() else "_" for ch in f"{model}_{version}").strip("_")
