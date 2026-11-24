import { Card, CardTitle } from "@/components/dt-ui";
const CAUSE_COLOR = {
    definition: "#1d4ed8", filters: "#7c3aed", time_logic: "#0e7490", source: "#0f766e",
    refresh: "#4d7c0f", mapping: "#a16207", late_adjustments: "#be185d", unexplained: "#b45309",
};
const fmt = (x) => x.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 });
export function Waterfall({ bridge, labelA, labelB }) {
    const bars = [
        { label: labelA, from: 0, to: bridge.start, kind: "total" },
    ];
    let prev = bridge.start;
    for (const s of bridge.steps) {
        bars.push({ label: s.label, from: prev, to: s.running, kind: "step", cause: s.cause, delta: s.delta });
        prev = s.running;
    }
    bars.push({ label: labelB, from: 0, to: bridge.end, kind: "total" });
    const values = bars.flatMap((b) => [b.from, b.to]);
    const lo = Math.min(0, ...values), hi = Math.max(...values);
    // Zoom the axis so the steps are visible when totals dwarf them.
    const floor = Math.max(lo, Math.min(...values.filter((v) => v > 0)) * 0.85);
    const W = 760, rowH = 34, left = 250, right = 90, top = 16;
    const H = top + bars.length * rowH + 28;
    const X = (v) => left + ((Math.max(v, floor) - floor) / (hi - floor || 1)) * (W - left - right);
    return (<svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Bridge from ${labelA} to ${labelB}`}>
      {bars.map((b, i) => {
            const y = top + i * rowH;
            const x0 = X(Math.min(b.from, b.to)), x1 = X(Math.max(b.from, b.to));
            const color = b.kind === "total" ? "#334155" : CAUSE_COLOR[b.cause ?? "definition"];
            return (<g key={i}>
            <text x={left - 10} y={y + rowH / 2 + 4} textAnchor="end" fontSize="12" fill="#1f2937" fontWeight={b.kind === "total" ? 600 : 400}>
              {b.label.length > 38 ? b.label.slice(0, 36) + "…" : b.label}
            </text>
            <rect x={x0} y={y + 6} width={Math.max(2, x1 - x0)} height={rowH - 12} rx={3} fill={color} fillOpacity={b.kind === "total" ? 0.85 : b.cause === "unexplained" ? 0.35 : 0.7} stroke={b.cause === "unexplained" ? color : "none"} strokeDasharray={b.cause === "unexplained" ? "3 2" : undefined}/>
            <text x={x1 + 6} y={y + rowH / 2 + 4} fontSize="12" fill="#475569">
              {b.kind === "total" ? fmt(b.to) : `${(b.delta ?? 0) > 0 ? "+" : ""}${fmt(b.delta ?? 0)}`}
            </text>
            {i < bars.length - 1 && (<line x1={X(b.to)} x2={X(b.to)} y1={y + rowH - 6} y2={y + rowH + 6} stroke="#94a3b8" strokeDasharray="2 2"/>)}
          </g>);
        })}
      <text x={left} y={H - 6} fontSize="11" fill="#64748b">
        {bridge.unit} · {bridge.period} · axis starts at {fmt(floor)} to make the steps visible
      </text>
    </svg>);
}
export function ReconcileView({ rec }) {
    const la = rec.a.name + (rec.a.dashboard ? ` · ${rec.a.dashboard}` : "");
    const lb = rec.b.name + (rec.b.dashboard ? ` · ${rec.b.dashboard}` : "");
    return (<div className="space-y-4">
      <Card className="bg-muted/50">
        <p className="text-sm leading-relaxed">{rec.summary}</p>
        {rec.bridge && (<p className="mt-2 text-xs text-muted-foreground">
            {Math.round(rec.bridge.explained_share * 100)}% explained by structural differences ·
            start {rec.bridge.start_source}, end {rec.bridge.end_source} values
          </p>)}
      </Card>

      {rec.bridge ? (<Card>
          <CardTitle className="mb-2">Bridge from A to B</CardTitle>
          <Waterfall bridge={rec.bridge} labelA={la} labelB={lb}/>
        </Card>) : (<Card className="text-sm text-muted-foreground">
          No numeric bridge: the metrics are ratios, use different units, or component values aren&apos;t loaded for them.
          The structural causes below still explain where they diverge.
        </Card>)}

      <Card>
        <CardTitle className="mb-3">Why they differ ({rec.causes.length})</CardTitle>
        <table className="w-full text-sm">
          <tbody>
            {rec.causes.map((c, i) => (<tr key={i} className="border-t border-border first:border-0 align-top">
                <td className="py-2 pr-3">
                  <span className="inline-block whitespace-nowrap rounded px-2 py-0.5 text-xs font-medium text-white" style={{ background: CAUSE_COLOR[c.cause] }}>{c.label}</span>
                </td>
                <td className="py-2 pr-3">
                  <p>{c.finding}</p>
                  {c.detail && <p className="text-xs text-muted-foreground">{c.detail}</p>}
                </td>
                <td className="py-2 text-right font-mono text-xs">{c.impact != null ? `${c.impact > 0 ? "+" : ""}${fmt(c.impact)}` : ""}</td>
              </tr>))}
          </tbody>
        </table>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {[rec.a, rec.b].map((s, i) => (<Card key={i} className="space-y-1 text-sm">
            <CardTitle>{i === 0 ? "A" : "B"}: {s.name}{s.dashboard ? ` on ${s.dashboard}` : ""}</CardTitle>
            <p className="font-mono text-xs">{s.formula}</p>
            {s.filters.length > 0 && <p className="text-xs text-purple-700">Filters: {s.filters.join(" AND ")}</p>}
            <p className="text-xs text-muted-foreground">
              Dated by {s.time_basis ?? "?"} · {s.calendar ?? "?"} calendar · {s.currency ?? "no currency"} · hierarchy {s.hierarchy_version ?? "?"}
            </p>
          </Card>))}
      </div>
    </div>);
}
