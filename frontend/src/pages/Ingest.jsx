import { useState } from "react";
import { API, authHeaders, notifyCreditsChanged } from "@/lib/api";
import { Button, Card, CardTitle } from "@/components/dt-ui";
const TYPES = [
    { key: "glossary", label: "Business glossary", cols: "term_id, term, definition, steward_email, required_components, synonyms" },
    { key: "metric", label: "Metrics (dashboard KPIs)", cols: "metric_id, name, formula, grain, owner_email, team, glossary_term, data_product, certification, refresh_sla_h, last_refreshed" },
    { key: "dashboard", label: "Dashboards", cols: "dashboard_id, name, tool, audience, owner_email, monthly_viewers, metrics, local_overrides" },
    { key: "lineage", label: "Data product lineage", cols: "from_type, from_id, from_name, relation, to_type, to_id, to_name, documented" },
    { key: "recommendation", label: "AI recommendations", cols: "rec_id, model, version, title, raw_confidence, input_features, evidence, rationale, accepted_90d, success_90d, rule_violations" },
];
function BiExtract() {
    const [tool, setTool] = useState("powerbi");
    const [file, setFile] = useState(null);
    const [res, setRes] = useState(null);
    const [err, setErr] = useState(null);
    async function send(commit) {
        if (!file)
            return;
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch(`${API}/extract/${tool}?commit=${commit}`, { method: "POST", body: fd, headers: await authHeaders() });
        const body = await r.json();
        if (r.status === 402)
            window.dispatchEvent(new Event("dt:out-of-credits"));
        if (commit && r.ok)
            notifyCreditsChanged();
        if (!r.ok) {
            setErr(body.detail ?? "Extraction failed");
            return;
        }
        setErr(null);
        setRes(body);
    }
    return (<Card className="space-y-3 border-primary/40">
      <CardTitle className="text-foreground">Read definitions straight from your BI files</CardTitle>
      <p className="text-xs text-muted-foreground">
        Power BI: a .tmdl file or model.bim from a project folder. Tableau: a .twb or .twbx workbook. Measures, calculated
        fields and worksheet filters become governed metrics. Try the samples in backend/data/samples.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <select className="h-9 rounded-md border border-border px-2 text-sm" value={tool} onChange={(e) => setTool(e.target.value)}>
          <option value="powerbi">Power BI (.tmdl / .bim)</option>
          <option value="tableau">Tableau (.twb / .twbx)</option>
        </select>
        <input type="file" accept=".tmdl,.bim,.json,.twb,.twbx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm"/>
        <Button data-testid="extract-preview" variant="outline" onClick={() => send(false)} disabled={!file}>Preview · free</Button>
        <Button data-testid="extract-commit" onClick={() => send(true)} disabled={!file}>Add to workspace · 1 credit</Button>
      </div>
      {err && <p className="text-xs text-red-700">{err}</p>}
      {res && (<div className="space-y-2 text-xs">
          <p className="font-medium">{res.metrics.length} metric(s), {res.dashboards.length} dashboard(s) from {res.source_name}</p>
          <table className="w-full">
            <tbody>
              {res.metrics.map((m) => (<tr key={m.metric_id} className="border-t border-border align-top">
                  <td className="py-1.5 pr-2 font-medium">{m.name}</td>
                  <td className="py-1.5 pr-2 font-mono text-muted-foreground">{m.source_expression}</td>
                  <td className="py-1.5 pr-2 font-mono">{m.formula}</td>
                  <td className="py-1.5 text-muted-foreground">{m.glossary_term || "no term"}</td>
                </tr>))}
            </tbody>
          </table>
          {res.dashboards.map((d) => (<p key={d.name}>Dashboard <b>{d.name}</b>{d.local_overrides ? ` · filters: ${d.local_overrides.replaceAll("|", "; ")}` : ""}</p>))}
          {res.warnings.map((w) => <p key={w} className="text-amber-700">⚠ {w}</p>)}
          {res.new_conflicts && <p className="text-red-700">{res.new_conflicts.length} conflict(s) now open on these metrics. See the conflict queue.</p>}
        </div>)}
    </Card>);
}
export default function IngestPage() {
    const [result, setResult] = useState({});
    async function upload(type, file, mode) {
        if (!file)
            return;
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch(`${API}/ingest/${type}?mode=${mode}`, { method: "POST", body: fd, headers: await authHeaders() });
        const body = await res.json();
        if (res.status === 402)
            window.dispatchEvent(new Event("dt:out-of-credits"));
        if (res.ok)
            notifyCreditsChanged();
        setResult((r) => ({
            ...r,
            [type]: res.ok ? `${body.rows_ingested} rows ingested, ${body.errors.length} errors · ${body.conflicts_open} open conflicts` : body.detail ?? "Upload failed",
        }));
    }
    return (<div className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-2xl font-semibold">Ingest metadata</h1>
      <p className="text-sm text-muted-foreground">Metadata only: no row-level data ever leaves your systems. Scores recompute after every upload. Each upload uses 1 credit.</p>
      <BiExtract />
      {TYPES.map((t) => (<Card key={t.key} className="space-y-2">
          <CardTitle className="text-foreground">{t.label}</CardTitle>
          <p className="font-mono text-xs text-muted-foreground">{t.cols}</p>
          <div className="flex items-center gap-3">
            <input type="file" accept=".csv" id={`f-${t.key}`} className="text-sm"/>
            <Button data-testid={`ingest-upsert-${t.key}`} variant="outline" title="Uses 1 credit" onClick={() => upload(t.key, document.getElementById(`f-${t.key}`).files?.[0], "upsert")}>Upsert</Button>
            <Button data-testid={`ingest-replace-${t.key}`} variant="ghost" title="Uses 1 credit" onClick={() => upload(t.key, document.getElementById(`f-${t.key}`).files?.[0], "replace")}>Replace all</Button>
          </div>
          {result[t.key] && <p className="text-xs">{result[t.key]}</p>}
        </Card>))}
    </div>);
}
