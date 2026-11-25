import { Link } from "react-router-dom";
import { plainError } from "@/lib/format";
import { useState } from "react";
import { API, authHeaders, notifyCreditsChanged } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { Button, Card, CardTitle, Notice } from "@/components/dt-ui";
const TYPES = [
    { key: "glossary", label: "Business glossary", cols: "term_id, term, definition, steward_email, required_components, synonyms" },
    { key: "metric", label: "Metrics (dashboard KPIs)", cols: "metric_id, name, formula, grain, owner_email, team, glossary_term, data_product, certification, refresh_sla_h, last_refreshed" },
    { key: "dashboard", label: "Dashboards", cols: "dashboard_id, name, tool, audience, owner_email, monthly_viewers, metrics, local_overrides" },
    { key: "lineage", label: "Data product lineage", cols: "from_type, from_id, from_name, relation, to_type, to_id, to_name, documented" },
    { key: "recommendation", label: "AI recommendations", cols: "rec_id, model, version, title, raw_confidence, input_features, evidence, rationale, accepted_90d, success_90d, rule_violations" },
];
function BiExtract() {
    const { ws } = useWorkspace();
    const [tool, setTool] = useState("powerbi");
    const [file, setFile] = useState(null);
    const [file2, setFile2] = useState(null);
    const [res, setRes] = useState(null);
    const [err, setErr] = useState(null);
    async function send(commit) {
        if (!file)
            return;
        const fd = new FormData();
        fd.append("file", file);
        if (tool === "dbt" && file2)
            fd.append("file2", file2);
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
      <CardTitle className="text-foreground">Read definitions straight from Power BI, Tableau or dbt</CardTitle>
      <p className="text-xs text-muted-foreground">
        Power BI: a .tmdl file or model.bim from a project folder. Tableau: a .twb or .twbx workbook. dbt: the
        manifest.json and semantic_manifest.json files from your project's target folder (created by dbt parse).
        Measures, calculated fields, dbt metrics, filters and lineage become governed metrics. Try a sample:{" "}
        <a data-testid="sample-powerbi" className="text-primary underline" href="/samples/acme_finance.tmdl" download>Power BI model</a>{" · "}
        <a data-testid="sample-tableau" className="text-primary underline" href="/samples/acme_sales.twb" download>Tableau workbook</a>{" · "}
        dbt <a data-testid="sample-dbt-manifest" className="text-primary underline" href="/samples/acme_dbt_manifest.json" download>manifest</a>{" + "}
        <a data-testid="sample-dbt-semantic" className="text-primary underline" href="/samples/acme_dbt_semantic_manifest.json" download>semantic manifest</a>.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <select data-testid="extract-tool" className="h-9 rounded-md border border-border px-2 text-sm" value={tool} onChange={(e) => { setTool(e.target.value); setRes(null); setErr(null); }}>
          <option value="powerbi">Power BI (.tmdl / .bim)</option>
          <option value="tableau">Tableau (.twb / .twbx)</option>
          <option value="dbt">dbt (manifest.json + semantic_manifest.json)</option>
        </select>
        {tool === "dbt" ? (<>
            <label className="text-xs text-muted-foreground">manifest.json
              <input data-testid="extract-file" type="file" accept=".json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="ml-2 text-sm"/>
            </label>
            <label className="text-xs text-muted-foreground">semantic_manifest.json (optional)
              <input data-testid="extract-file2" type="file" accept=".json" onChange={(e) => setFile2(e.target.files?.[0] ?? null)} className="ml-2 text-sm"/>
            </label>
          </>) : (<input data-testid="extract-file" type="file" accept=".tmdl,.bim,.json,.twb,.twbx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm"/>)}
        <Button data-testid="extract-preview" variant="outline" onClick={() => send(false)} disabled={!file}>Preview · free</Button>
        <Button data-testid="extract-commit" onClick={() => send(true)} disabled={!file || ws === "demo"}>Add to my workspace · 1 credit</Button>
      </div>
      {err && <Notice tone="error" data-testid="extract-error">{plainError(err)}</Notice>}
      {res && (<div className="space-y-2 text-xs">
          <p className="font-medium">
            {res.metrics.length} metric(s), {res.dashboards.length} dashboard(s)
            {res.lineage?.length ? `, ${res.lineage.length} data links showing where the data comes from` : ""} from {res.source_name}
          </p>
          <table className="w-full">
            <tbody>
              {res.metrics.map((m) => (<tr key={m.metric_id} className="border-t border-border align-top">
                  <td className="py-1.5 pr-2 font-medium">{m.name}</td>
                  {res.tool !== "dbt" && <td className="py-1.5 pr-2 font-mono text-muted-foreground">{m.source_expression}</td>}
                  <td className="py-1.5 pr-2 font-mono">{m.formula}</td>
                  <td className="py-1.5 text-muted-foreground">{m.glossary_term || "no term"}</td>
                </tr>))}
            </tbody>
          </table>
          {res.dashboards.map((d) => (<p key={d.name}>Dashboard <b>{d.name}</b>{d.local_overrides ? ` · filters: ${d.local_overrides.replaceAll("|", "; ")}` : ""}</p>))}
          {res.warnings.map((w) => <Notice key={w}>{w}</Notice>)}
          {res.new_conflicts && <Notice>{res.new_conflicts.length} issue(s) now open on these metrics. <Link className="text-primary underline" to="/conflicts">See Issues to fix</Link>.</Notice>}
        </div>)}
    </Card>);
}
function DemoNotice() {
    const { ws, setWs } = useWorkspace();
    if (ws !== "demo")
        return null;
    return (<div data-testid="ingest-demo-notice" className="flex items-center justify-between gap-4 rounded-md border border-primary/30 bg-primary/5 px-4 py-3 text-sm">
      <span>You&apos;re in the Acme demo, which is read-only for new data. Your own data goes in <b>My workspace</b>, where it&apos;s saved. Previewing a BI file stays free.</span>
      <Button data-testid="ingest-switch-mine" className="shrink-0" onClick={() => setWs("mine")}>Switch to My workspace</Button>
    </div>);
}

export default function IngestPage() {
    const { ws } = useWorkspace();
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
      <h1 className="text-2xl font-semibold">Add data</h1>
      <p className="text-sm text-muted-foreground">Bring in metric definitions from Power BI, Tableau or spreadsheets. Only definitions are read, never your actual data. Each upload uses 1 credit and is saved to your workspace.</p>
      <DemoNotice />
      <BiExtract />
      {TYPES.map((t) => (<Card key={t.key} className="space-y-2">
          <CardTitle className="text-foreground">{t.label}</CardTitle>
          <p className="font-mono text-xs text-muted-foreground">{t.cols}</p>
          <a data-testid={`sample-csv-${t.key}`} className="text-xs text-primary underline" href={`/samples/${{ glossary: "glossary", metric: "metrics", dashboard: "dashboards", lineage: "lineage", recommendation: "recommendations" }[t.key]}.csv`} download>Download example CSV</a>
          <div className="flex items-center gap-3">
            <input type="file" accept=".csv" id={`f-${t.key}`} className="text-sm"/>
            <Button data-testid={`ingest-upsert-${t.key}`} variant="outline" disabled={ws === "demo"} title="Uses 1 credit" onClick={() => upload(t.key, document.getElementById(`f-${t.key}`).files?.[0], "upsert")}>Upsert</Button>
            <Button data-testid={`ingest-replace-${t.key}`} variant="ghost" disabled={ws === "demo"} title="Uses 1 credit" onClick={() => upload(t.key, document.getElementById(`f-${t.key}`).files?.[0], "replace")}>Replace all</Button>
          </div>
          {result[t.key] && <p className="text-xs">{result[t.key]}</p>}
        </Card>))}
    </div>);
}
