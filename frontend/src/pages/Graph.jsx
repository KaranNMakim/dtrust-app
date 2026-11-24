import { Link } from "react-router-dom";
import { Suspense, useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { zoneColor, zoneLabel } from "@/lib/utils";
import { Card, CardTitle, ErrorNote } from "@/components/dt-ui";
import { TrustGraph } from "@/components/trust-graph";
const CENTERS = [
    { id: "g_revenue", label: "Revenue" },
    { id: "g_gm", label: "Gross Margin" },
    { id: "g_otif", label: "OTIF" },
    { id: "g_churn", label: "Churn" },
    { id: "dp_supply", label: "Supply Mart (cycle)" },
    { id: "", label: "Whole graph" },
];
function GraphInner() {
    const [params] = useSearchParams();
    const { ws } = useWorkspace();
    const [center, setCenter] = useState(params.get("center") ?? (ws === "demo" ? "g_revenue" : ""));
    const [depth, setDepth] = useState(2);
    const path = center ? `/graph/neighbourhood/${center}?depth=${depth}` : "/graph";
    const { data, error } = useApi(path);
    const [sel, setSel] = useState(null);
    const onSelect = useCallback((n) => setSel(n), []);
    return (<div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-4 text-2xl font-semibold">Trust Graph</h1>
        {CENTERS.filter((c) => ws === "demo" || !c.id).map((c) => (<button key={c.id || "all"} onClick={() => setCenter(c.id)} className={`rounded-full border px-3 py-1 text-xs ${center === c.id ? "border-primary bg-primary/10" : "border-border bg-white"}`}>
            {c.label}
          </button>))}
        {center && (<select value={depth} onChange={(e) => setDepth(Number(e.target.value))} className="ml-2 rounded border border-border px-2 py-1 text-xs">
            {[1, 2, 3].map((d) => <option key={d} value={d}>depth {d}</option>)}
          </select>)}
      </div>
      <ErrorNote error={error}/>
      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        {data && data.nodes.length === 0 && (<Card data-testid="graph-empty" className="flex h-64 flex-col items-center justify-center text-center">
            <p className="font-semibold">Nothing to draw yet</p>
            <p className="mt-1 text-sm text-muted-foreground">Add metrics, dashboards and lineage to see how trust flows through your data.</p>
            <Link to="/ingest" className="mt-3 text-sm text-primary">Add your data →</Link>
          </Card>)}
        {data && data.nodes.length > 0 && <TrustGraph nodes={data.nodes} edges={data.edges} onSelect={onSelect} focus={center}/>}
        <div className="space-y-4">
          <Card>
            <CardTitle className="mb-2">Legend</CardTitle>
            {["green", "yellow", "red"].map((z) => (<p key={z} className="flex items-center gap-2 text-xs">
                <span className="inline-block h-3 w-3 rounded-full" style={{ background: zoneColor[z] }}/>
                {zoneLabel[z]} {z === "green" ? "80+" : z === "yellow" ? "50–79" : "under 50"}
              </p>))}
            <p className="mt-2 text-xs text-muted-foreground">Dashed edge = undocumented lineage · thick border = certified</p>
          </Card>
          {sel && (<Card>
              <p className="text-xs text-muted-foreground">{sel.label}</p>
              <p className="font-semibold">{sel.name}</p>
              {sel.trust_score != null && sel.zone && (<p className="mt-2 text-sm" style={{ color: zoneColor[sel.zone] }}>
                  Trust score {Math.round(sel.trust_score)} · {zoneLabel[sel.zone]}
                </p>)}
              {sel.label === "Metric" && (<Link to={`/metrics/${sel.id}`} className="mt-3 inline-block text-sm text-primary">Open metric →</Link>)}
              <button onClick={() => setCenter(sel.id)} className="mt-2 block text-sm text-primary">Centre graph here</button>
            </Card>)}
        </div>
      </div>
    </div>);
}
export default function GraphPage() {
    return (<Suspense>
      <GraphInner />
    </Suspense>);
}
