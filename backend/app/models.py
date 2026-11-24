"""Domain objects. Plain dataclasses so the scoring core has no web or DB dependency."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GlossaryTerm:
    id: str
    term: str
    definition: str
    steward_email: str | None
    required_components: list[str]
    synonyms: list[str]


@dataclass
class Metric:
    id: str
    name: str
    formula: str
    grain: str
    owner_email: str | None
    team: str | None
    glossary_term_id: str | None
    data_product_id: str | None
    certification: str  # none | pending | certified | deprecated
    refresh_sla_hours: float
    last_refreshed: datetime | None
    formula_hash: str = ""
    formula_tokens: set[str] = field(default_factory=set)
    time_basis: str | None = None      # invoice_date, order_date, close_date ...
    calendar: str | None = None        # fiscal | calendar
    currency: str | None = None
    hierarchy_version: str | None = None


@dataclass
class Dashboard:
    id: str
    name: str
    tool: str
    audience: str  # exec | department | team | personal
    owner_email: str | None
    monthly_viewers: int
    metric_ids: list[str]
    local_overrides: dict[str, str]  # metric_id -> override expression


@dataclass
class LineageEdge:
    from_type: str
    from_id: str
    from_name: str
    relation: str
    to_type: str
    to_id: str
    to_name: str
    documented: bool


@dataclass
class Recommendation:
    id: str
    model: str
    version: str
    title: str
    raw_confidence: float
    input_features: dict[str, float]  # metric_id -> attribution weight
    evidence: list[str]
    rationale: str
    accepted_90d: int
    success_90d: int
    rule_violations: list[str]


@dataclass
class Incident:
    date: str
    metric_id: str
    type: str  # restated | exec_dispute | wrong_decision
    severity: str
    note: str


@dataclass
class BusinessRule:
    id: str
    name: str
    description: str
    severity: str


@dataclass
class Component:
    key: str
    label: str
    weight: float
    raw: float
    evidence: list[str]
    fix: str | None = None

    @property
    def weighted(self) -> float:
        return self.weight * self.raw


@dataclass
class Conflict:
    id: str
    code: str  # C1..C5
    severity: str  # critical | warning
    title: str
    entity_ids: list[str]
    blast_radius: int
    detail: dict
    status: str = "open"
    resolution_note: str | None = None


@dataclass
class TrustScore:
    entity_type: str
    entity_id: str
    score: float
    zone: str
    components: list[Component]
    penalties: list[dict]
    scoring_version: str
    cap: dict | None = None
    explanation: str | None = None


def zone_for(score: float) -> str:
    if score >= 80:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"
