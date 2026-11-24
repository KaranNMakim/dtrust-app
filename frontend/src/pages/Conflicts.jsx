import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { Button, Card, ErrorNote, SeverityBadge } from "@/components/dt-ui";
import { MigrationPlan } from "@/components/migration-plan";
const CODES = ["", "C1", "C2", "C3", "C4", "C5"];
const CODE_LABEL = {
    C1: "Multiple definitions", C2: "Different calculation", C3: "Orphan metric", C4: "Circular lineage", C5: "Glossary drift",
};
export default function ConflictsPage() {
    const [code, setCode] = useState("");
    const { data, error, reload } = useApi(`/conflicts${code ? `?code=${code}` : ""}`);
    const [open, setOpen] = useState(null);
    const [planFor, setPlanFor] = useState(null);
    async function patch(id, status) {
        await api(`/conflicts/${id}`, { method: "PATCH", body: JSON.stringify({ status, note: `Marked ${status} in UI` }) });
        reload();
    }
    return (<div className="mx-auto max-w-5xl space-y-5">
      <h1 className="text-2xl font-semibold">Conflict queue</h1>
      <div className="flex gap-2">
        {CODES.map((c) => (<button key={c || "all"} onClick={() => setCode(c)} className={`rounded-full border px-3 py-1 text-xs ${code === c ? "border-primary bg-primary/10" : "border-border bg-white"}`}>
            {c ? `${c} · ${CODE_LABEL[c]}` : "All"}
          </button>))}
      </div>
      <ErrorNote error={error}/>
      <div className="space-y-3">
        {(data ?? []).map((c) => (<Card key={c.id} className="p-4">
            <div className="flex items-center gap-3">
              <SeverityBadge severity={c.severity}/>
              <span className="font-mono text-xs text-muted-foreground">{c.code}</span>
              <button className="flex-1 text-left font-medium hover:underline" onClick={() => setOpen(open === c.id ? null : c.id)}>
                {c.title}
              </button>
              <span className="text-xs text-muted-foreground">{c.blast_radius} dashboards</span>
              <Button className="h-8" onClick={() => setPlanFor(planFor === c.id ? null : c.id)}>{planFor === c.id ? "Hide plan" : "Migration plan"}</Button>
              <Button variant="outline" className="h-8" onClick={() => patch(c.id, "resolved")}>Resolve</Button>
              <Button variant="ghost" className="h-8" onClick={() => patch(c.id, "dismissed")}>Dismiss</Button>
            </div>
            {open === c.id && <ConflictDetail c={c}/>}
            {planFor === c.id && <MigrationPlan conflictId={c.id} onChanged={reload}/>}
          </Card>))}
        {data?.length === 0 && <p className="text-sm text-muted-foreground">No open conflicts.</p>}
      </div>
    </div>);
}
function ConflictDetail({ c }) {
    const variants = c.detail.variants;
    if (variants) {
        return (<table className="mt-3 w-full text-xs">
        <tbody>
          {variants.map((v) => (<tr key={v.metric_id} className="border-t border-border">
              <td className="py-1.5 pr-3 font-medium">{v.name} {v.certification === "certified" && "✓"}</td>
              <td className="py-1.5 font-mono text-muted-foreground">{v.formula}</td>
            </tr>))}
        </tbody>
      </table>);
    }
    return <pre className="mt-3 overflow-x-auto rounded bg-muted p-3 text-xs">{JSON.stringify(c.detail, null, 2)}</pre>;
}
