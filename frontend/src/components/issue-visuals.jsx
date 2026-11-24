// Human-readable views for each kind of issue. Never renders raw data structures or internal ids.
import { Link } from "react-router-dom";
import { ArrowRight, CornerDownLeft } from "lucide-react";
import { Badge, Hint, ScorePill } from "@/components/dt-ui";
import { zoneOf } from "@/lib/utils";

export function SourcesTable({ rows }) {
    if (!rows?.length)
        return null;
    return (<div className="overflow-x-auto" data-testid="issue-sources">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th className="pb-2 pr-3 font-medium">Metric</th>
            <th className="pb-2 pr-3 font-medium">How it's calculated</th>
            <th className="pb-2 pr-3 font-medium">Owner</th>
            <th className="pb-2 pr-3 font-medium">Source system</th>
            <th className="pb-2 font-medium">Shown on</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (<tr key={r.metric_id} className="border-t border-border align-top">
              <td className="py-2 pr-3">
                <div className="flex items-center gap-2">
                  <Hint text={`Trust score ${Math.round(r.trust_score)} out of 100. Open the metric to see how it's scored.`}>
                    <ScorePill score={r.trust_score} zone={zoneOf(r.trust_score)}/>
                  </Hint>
                  <Link to={`/metrics/${r.metric_id}`} className="font-medium hover:underline">{r.name}</Link>
                </div>
                {r.recommended && <Badge className="mt-1 border-blue-300 bg-blue-50 text-blue-800">Recommended</Badge>}
              </td>
              <td className="py-2 pr-3 text-muted-foreground">{r.formula_plain}</td>
              <td className="py-2 pr-3">{r.owner ? <span>{r.owner}</span> : <span className="font-medium text-red-700">No owner</span>}</td>
              <td className="py-2 pr-3 text-muted-foreground">{r.source_systems?.join(", ") || "Not documented"}</td>
              <td className="py-2 text-muted-foreground">{r.dashboards?.join(", ") || "No dashboards"}</td>
            </tr>))}
        </tbody>
      </table>
    </div>);
}

export function LoopDiagram({ visual }) {
    return (<div data-testid="loop-diagram" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {visual.nodes.map((n, i) => {
            const e = visual.edges[i];
            return (<div key={n} className="flex items-center gap-2">
              <span className="rounded-md border border-border bg-white px-3 py-1.5 text-sm font-medium">{n}</span>
              <span className={`flex items-center gap-1 text-xs ${e.documented ? "text-muted-foreground" : "font-medium text-amber-800"}`}>
                {e.documented ? <ArrowRight className="h-4 w-4"/> : (<Hint text="This link isn't documented anywhere. It's the most likely one to remove to break the loop.">
                    <span className="flex items-center gap-1 rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5"><ArrowRight className="h-4 w-4"/>undocumented link</span>
                  </Hint>)}
              </span>
            </div>);
        })}
        <span className="flex items-center gap-1 text-xs text-muted-foreground"><CornerDownLeft className="h-4 w-4"/>back to {visual.nodes[0]}</span>
      </div>
      {visual.edges.some((e) => !e.documented) && (<p className="text-xs text-amber-800">Undocumented link: likely the one to remove.</p>)}
      {visual.affected?.length > 0 && (<div className="flex flex-wrap gap-1.5">
          <span className="text-xs text-muted-foreground">Metrics affected:</span>
          {visual.affected.map((a) => <span key={a} className="rounded-full border border-border bg-muted px-2 py-0.5 text-xs">{a}</span>)}
        </div>)}
    </div>);
}

export function OverridesTable({ visual }) {
    return (<table className="w-full text-sm" data-testid="overrides-table">
      <thead className="text-left text-xs text-muted-foreground">
        <tr><th className="pb-2 pr-3 font-medium">Dashboard</th><th className="pb-2 font-medium">What it changes</th></tr>
      </thead>
      <tbody>
        {visual.rows.map((r) => (<tr key={r.dashboard} className="border-t border-border">
            <td className="py-2 pr-3 font-medium">{r.dashboard}</td>
            <td className="py-2 text-muted-foreground">{r.change}</td>
          </tr>))}
      </tbody>
    </table>);
}

export function OrphanCard({ visual }) {
    return (<dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm" data-testid="orphan-detail">
      <dt className="text-muted-foreground">Team on record</dt><dd>{visual.team || "None"}</dd>
      <dt className="text-muted-foreground">Used on</dt><dd>{visual.dashboards?.join(", ") || "No dashboards"}</dd>
      <dt className="text-muted-foreground">Suggested owner</dt><dd>{visual.suggested_owner || "Ask the team lead to nominate someone"}</dd>
    </dl>);
}

export function DriftCard({ visual }) {
    return (<div className="grid gap-3 md:grid-cols-2" data-testid="drift-detail">
      <div className="rounded-md border border-border bg-muted/40 p-3">
        <p className="text-xs font-semibold text-muted-foreground">Official definition of {visual.term}</p>
        <p className="mt-1 text-sm">{visual.official}</p>
      </div>
      <div className="rounded-md border border-border p-3">
        <p className="text-xs font-semibold text-muted-foreground">How {visual.metric} is calculated</p>
        <p className="mt-1 text-sm">{visual.formula_plain}</p>
        {visual.missing?.length > 0 && (<p className="mt-2 text-sm">
            <span className="font-medium text-amber-800">Missing: </span>{visual.missing.join(", ")}
          </p>)}
      </div>
    </div>);
}

export function IssueVisual({ visual }) {
    if (!visual)
        return null;
    if (visual.kind === "loop")
        return <LoopDiagram visual={visual}/>;
    if (visual.kind === "overrides")
        return <OverridesTable visual={visual}/>;
    if (visual.kind === "orphan")
        return <OrphanCard visual={visual}/>;
    if (visual.kind === "drift")
        return <DriftCard visual={visual}/>;
    return null;
}

export function IndexChange({ before, after, label = "Trust Index" }) {
    if (before == null || after == null)
        return null;
    const up = after > before;
    return (<span className="inline-flex items-center gap-1.5 text-sm">
      <Hint text="Average trust score of all metrics, weighted by how many people view them. 0 to 100.">{label}</Hint>
      <span className="font-semibold">{Math.round(before)}</span>
      <ArrowRight className="h-3.5 w-3.5 text-muted-foreground"/>
      <span className={`font-semibold ${up ? "text-blue-700" : ""}`}>{Math.round(after)}</span>
    </span>);
}
