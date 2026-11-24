import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { Card, CardTitle, Hint } from "@/components/dt-ui";

// Reason colours are categories, not trust levels: deliberately no green or red. Amber only for "Not yet explained".
export const CAUSE_COLOR = {
    definition: "#1d4ed8", filters: "#7c3aed", time_logic: "#0e7490", source: "#4338ca",
    refresh: "#475569", mapping: "#a21caf", late_adjustments: "#0369a1", unexplained: "#b45309",
};
const CAUSE_ORDER = ["definition", "filters", "time_logic", "source", "refresh", "mapping", "late_adjustments", "unexplained"];
const CAUSE_HELP = {
    definition: "The two numbers are calculated from different things or deduct different items.",
    filters: "One number quietly leaves out part of the data. The tile label doesn't tell you.",
    time_logic: "The same sale can land in a different month depending on which date or calendar is used.",
    source: "Each system records the transaction at a different moment, so totals drift.",
    refresh: "One number was updated more recently than the other.",
    mapping: "Customers or products are mapped to regions differently, or the currency differs.",
    late_adjustments: "Returns, rebates and credit notes are booked weeks later; some views never see them.",
    unexplained: "Left over after every known difference. Usually a mapping or timing difference worth checking.",
};

const fmt = (x) => x.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const words = (s) => (s ? s.replace(/_/g, " ") : "not recorded");

export function Waterfall({ bridge, labelA, labelB }) {
    const bars = [{ label: labelA, from: 0, to: bridge.start, kind: "total" }];
    let prev = bridge.start;
    for (const s of bridge.steps) {
        bars.push({ label: s.label, from: prev, to: s.running, kind: "step", cause: s.cause, delta: s.delta, note: s.note });
        prev = s.running;
    }
    bars.push({ label: labelB, from: 0, to: bridge.end, kind: "total" });
    const values = bars.flatMap((b) => [b.from, b.to]);
    const lo = Math.min(0, ...values), hi = Math.max(...values);
    // Zoom the axis so the steps are visible when totals dwarf them.
    const floor = Math.max(lo, Math.min(...values.filter((v) => v > 0)) * 0.85);
    const W = 760, rowH = 34, left = 290, right = 80, top = 16;
    const H = top + bars.length * rowH + 28;
    const X = (v) => left + ((Math.max(v, floor) - floor) / (hi - floor || 1)) * (W - left - right);
    return (<svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Bridge from ${labelA} to ${labelB}`} data-testid="waterfall">
      {bars.map((b, i) => {
            const y = top + i * rowH;
            const x0 = X(Math.min(b.from, b.to)), x1 = X(Math.max(b.from, b.to));
            const color = b.kind === "total" ? "#334155" : CAUSE_COLOR[b.cause ?? "definition"];
            const label = b.label.length > 44 ? b.label.slice(0, 42) + "…" : b.label;
            return (<g key={i}>
            <title>{b.note ? `${b.label}. ${b.note}` : b.label}</title>
            <text x={left - 10} y={y + rowH / 2 + 4} textAnchor="end" fontSize="12" fill="#1f2937" fontWeight={b.kind === "total" ? 600 : 400}>{label}</text>
            <rect x={x0} y={y + 6} width={Math.max(2, x1 - x0)} height={rowH - 12} rx={3} fill={color} fillOpacity={b.kind === "total" ? 0.85 : b.cause === "unexplained" ? 0.3 : 0.75} stroke={b.cause === "unexplained" ? color : "none"} strokeDasharray={b.cause === "unexplained" ? "4 3" : undefined}/>
            <text x={x1 + 6} y={y + rowH / 2 + 4} fontSize="12" fill="#475569">
              {b.kind === "total" ? fmt(b.to) : `${(b.delta ?? 0) > 0 ? "+" : ""}${fmt(b.delta ?? 0)}`}
            </text>
            {i < bars.length - 1 && (<line x1={X(b.to)} x2={X(b.to)} y1={y + rowH - 6} y2={y + rowH + 6} stroke="#94a3b8" strokeDasharray="2 2"/>)}
          </g>);
        })}
      <text x={left} y={H - 6} fontSize="11" fill="#64748b">
        {bridge.unit} · {bridge.period} · the axis starts at {fmt(floor)} so the smaller steps are visible
      </text>
    </svg>);
}

function Legend({ causes }) {
    return (<div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs" data-testid="waterfall-legend">
      {causes.map((c) => (<span key={c.cause} className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: CAUSE_COLOR[c.cause], opacity: c.cause === "unexplained" ? 0.5 : 1 }}/>
          {c.label}
        </span>))}
    </div>);
}

function Headline({ rec, la, lb }) {
    const br = rec.bridge;
    return (<Card className="space-y-4" data-testid="compare-headline">
      <div className="grid items-center gap-4 md:grid-cols-[1fr_auto_1fr]">
        <div>
          <p className="text-xs font-semibold text-muted-foreground">A · {la}</p>
          <p className="text-3xl font-semibold">{br ? fmt(br.start) : "—"}</p>
        </div>
        <div className="text-center">
          {br ? (<><p className="text-xs text-muted-foreground">gap</p><p className="text-lg font-semibold">{br.gap > 0 ? "+" : ""}{fmt(br.gap)}</p><p className="text-xs text-muted-foreground">{br.unit} · {br.period}</p></>)
            : <ArrowRight className="mx-auto h-5 w-5 text-muted-foreground"/>}
        </div>
        <div className="md:text-right">
          <p className="text-xs font-semibold text-muted-foreground">B · {lb}</p>
          <p className="text-3xl font-semibold">{br ? fmt(br.end) : "—"}</p>
        </div>
      </div>
      <p className="border-t border-border pt-3 text-sm leading-relaxed">{rec.summary}</p>
      {br && (<p className="text-xs text-muted-foreground">
          <Hint text="The share of the gap accounted for by known differences in definition, filters, dates, sources and adjustments.">
            {Math.round(br.explained_share * 100)}% explained
          </Hint>{" "}
          · start and end values are what each dashboard {br.start_source === "reported" ? "actually reported" : "would show, modelled from its formula"}
        </p>)}
    </Card>);
}

export function ReconcileView({ rec }) {
    const la = rec.a.name + (rec.a.dashboard ? ` on ${rec.a.dashboard}` : "");
    const lb = rec.b.name + (rec.b.dashboard ? ` on ${rec.b.dashboard}` : "");
    const groups = CAUSE_ORDER.map((k) => ({ cause: k, label: rec.causes.find((c) => c.cause === k)?.label, items: rec.causes.filter((c) => c.cause === k) }))
        .filter((g) => g.items.length);
    const legendCauses = rec.bridge ? CAUSE_ORDER.filter((k) => rec.bridge.steps.some((s) => s.cause === k))
        .map((k) => ({ cause: k, label: rec.causes.find((c) => c.cause === k)?.label ?? (k === "unexplained" ? "Not yet explained" : k) })) : [];
    return (<div className="space-y-4">
      <Headline rec={rec} la={la} lb={lb}/>

      {rec.bridge ? (<Card>
          <CardTitle className="mb-2">How you get from A to B</CardTitle>
          <Waterfall bridge={rec.bridge} labelA={la} labelB={lb}/>
          <Legend causes={legendCauses}/>
        </Card>) : (<Card className="text-sm text-muted-foreground">
          These two can't be bridged with numbers (they're ratios, use different currencies, or the underlying amounts aren't loaded).
          The reasons below still show exactly where they diverge.
        </Card>)}

      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground">Why they differ ({rec.causes.length})</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {groups.map((g) => {
            const total = g.items.reduce((s, c) => s + (c.impact ?? 0), 0);
            const known = g.items.some((c) => c.impact != null);
            return (<Card key={g.cause} className="space-y-2 p-4" data-testid="cause-group">
              <div className="flex items-center justify-between gap-2">
                <Hint text={CAUSE_HELP[g.cause]} className="no-underline">
                  <span className="inline-flex items-center gap-2 text-sm font-semibold">
                    <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: CAUSE_COLOR[g.cause] }}/>
                    <span className="underline decoration-dotted decoration-muted-foreground/60 underline-offset-4">{g.label}</span>
                  </span>
                </Hint>
                {known && <span className="font-mono text-xs">{total > 0 ? "+" : ""}{fmt(total)}</span>}
              </div>
              <ul className="space-y-1.5 text-sm">
                {g.items.map((c, i) => (<li key={i}>
                    {c.finding}
                    {c.detail && <span className="block text-xs text-muted-foreground">{c.detail}</span>}
                  </li>))}
              </ul>
            </Card>);
        })}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {[rec.a, rec.b].map((s, i) => (<Card key={i} className="space-y-1.5 text-sm">
            <CardTitle>{i === 0 ? "A" : "B"}: {s.name}{s.dashboard ? ` on ${s.dashboard}` : ""}</CardTitle>
            <p><span className="text-muted-foreground">Calculated as: </span>{s.formula_plain ?? s.formula}</p>
            {(s.filters_plain ?? s.filters)?.length > 0 && <p><span className="text-muted-foreground">Filters: </span>{(s.filters_plain ?? s.filters).join("; ")}</p>}
            <p className="text-xs text-muted-foreground">
              Dated by {words(s.time_basis)} · {words(s.calendar)} calendar · {s.currency || "no currency set"} · mapping version {s.hierarchy_version || "not recorded"}
            </p>
          </Card>))}
      </div>

      <Card className="flex flex-wrap items-center justify-between gap-3 border-primary/30 bg-primary/5" data-testid="compare-fix-cta">
        <div>
          <p className="font-semibold">Stop this happening again</p>
          <p className="text-sm text-muted-foreground">Agree one definition, rename or retire the others, and record the decision.</p>
        </div>
        <Link to="/conflicts" className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90">Fix this for good →</Link>
      </Card>
    </div>);
}
