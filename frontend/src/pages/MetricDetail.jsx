import { Link } from "react-router-dom";
import { useParams } from "react-router-dom";
import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { CostTag } from "@/lib/workspace";
import { Button, Card, CardTitle, CertBadge, ComponentBars, ErrorNote, Input, ScoreRing } from "@/components/dt-ui";
export default function MetricDetail() {
    const { id } = useParams();
    const metric = useApi(`/metrics/${id}`);
    const score = useApi(`/metrics/${id}/score`);
    const usage = useApi(`/metrics/${id}/usage`);
    const lineage = useApi(`/metrics/${id}/lineage`);
    const [msg, setMsg] = useState(null);
    const [owner, setOwner] = useState("");
    const [exported, setExported] = useState(null);
    const [exportMsg, setExportMsg] = useState(null);
    async function doExport(format) {
        setExportMsg(null);
        try {
            setExported(await api(`/metrics/${id}/export?format=${format}`, undefined, { paid: true }));
        }
        catch (e) {
            setExportMsg(e.message);
        }
    }
    async function act(path, body = {}) {
        setMsg(null);
        try {
            await api(path, { method: "POST", body: JSON.stringify(body) });
            setMsg("Done. Scores recomputed.");
            metric.reload();
            score.reload();
        }
        catch (e) {
            setMsg(e.message);
        }
    }
    const m = metric.data;
    const s = score.data;
    return (<div className="mx-auto max-w-5xl space-y-5">
      <ErrorNote error={metric.error}/>
      {m && s && (<>
          <Card className="flex items-start justify-between gap-6">
            <div className="space-y-2">
              <CertBadge certification={m.certification}/>
              <h1 className="text-2xl font-semibold">{m.name}</h1>
              <p className="font-mono text-xs text-muted-foreground">{m.formula}</p>
              <p className="text-sm">
                Owner: {m.owner_email ?? <span className="text-red-700">none</span>} · Team: {m.team ?? "—"} · Term: {m.glossary_term ?? "—"}
              </p>
              <p className="max-w-2xl text-sm text-muted-foreground">{s.explanation}</p>
            </div>
            <ScoreRing score={s.score} zone={s.zone}/>
          </Card>

          <div className="grid gap-5 md:grid-cols-[2fr_1fr]">
            <Card>
              <CardTitle className="mb-4">Why this score ({s.scoring_version})</CardTitle>
              <ComponentBars components={s.components}/>
              {s.penalties.length > 0 && (<div className="mt-5 border-t border-border pt-3 text-sm">
                  <p className="font-medium">Conflict penalties</p>
                  {s.penalties.map((p, i) => (<p key={i} className="text-muted-foreground">
                      {p.code} {p.conflict_id ?? ""}: {p.points} {p.note ? `(${p.note})` : ""}
                    </p>))}
                </div>)}
            </Card>
            <div className="space-y-5">
              <Card className="space-y-2">
                <CardTitle>Steward actions</CardTitle>
                <Button className="w-full" onClick={() => act(`/metrics/${id}/certify`, { reason: "Reviewed in UI" })}>Certify</Button>
                <Button className="w-full" variant="danger" onClick={() => act(`/metrics/${id}/deprecate`, { reason: "Superseded" })}>Deprecate</Button>
                <div className="flex gap-2 pt-2">
                  <Input className="h-9" placeholder="owner@acme.com" value={owner} onChange={(e) => setOwner(e.target.value)}/>
                  <Button variant="outline" onClick={() => act(`/metrics/${id}/owner`, { owner_email: owner })}>Assign</Button>
                </div>
                {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
              </Card>
              <Card className="space-y-2">
                <CardTitle>Publish to the semantic layer <CostTag/></CardTitle>
                <div className="flex gap-2">
                  <Button variant="outline" className="flex-1" data-testid="export-dbt" onClick={() => doExport("dbt")}>dbt MetricFlow</Button>
                  <Button variant="outline" className="flex-1" data-testid="export-databricks" onClick={() => doExport("databricks")}>Databricks</Button>
                </div>
                {exportMsg && <p data-testid="export-message" className="text-xs text-red-700">{exportMsg}</p>}
                <Link className="block text-xs text-primary" to={`/reconcile?a=${id}`}>Reconcile with another metric →</Link>
              </Card>
              <Card>
                <CardTitle className="mb-2">Lineage</CardTitle>
                {(lineage.data ?? []).map((p, i) => (<div key={i} className="mb-2 text-xs">
                    {p.path.map((n, j) => (<span key={j}>
                        {j > 0 && <span className={p.documented[j - 1] ? "text-muted-foreground" : "text-red-700"}> {p.documented[j - 1] ? "→" : "⇢"} </span>}
                        {n}
                      </span>))}
                    <p className="text-muted-foreground">{Math.round(p.coverage * 100)}% documented</p>
                  </div>))}
                {lineage.data?.length === 0 && <p className="text-xs text-red-700">No path to a source system</p>}
              </Card>
            </div>
          </div>

          {exported && (<Card>
              <div className="mb-2 flex items-center justify-between">
                <CardTitle>{exported.filename}</CardTitle>
                <div className="flex gap-2">
                  <Button variant="outline" className="h-8" onClick={() => navigator.clipboard.writeText(exported.content)}>Copy</Button>
                  <a className="inline-flex h-8 items-center rounded-md border border-border px-3 text-sm" download={exported.filename} href={`data:text/plain;charset=utf-8,${encodeURIComponent(exported.content)}`}>Download</a>
                  <Button variant="ghost" className="h-8" onClick={() => setExported(null)}>Close</Button>
                </div>
              </div>
              <pre className="max-h-96 overflow-auto rounded bg-muted p-3 text-xs">{exported.content}</pre>
            </Card>)}

          <Card>
            <CardTitle className="mb-3">Where it is used</CardTitle>
            <table className="w-full text-sm">
              <tbody>
                {(usage.data ?? []).map((u) => (<tr key={u.dashboard_id} className="border-t border-border first:border-0">
                    <td className="py-2">{u.name}</td>
                    <td className="py-2 text-muted-foreground">{u.tool}</td>
                    <td className="py-2 text-muted-foreground">{u.audience}</td>
                    <td className="py-2 text-muted-foreground">{u.monthly_viewers} viewers/month</td>
                    <td className="py-2 text-amber-700">{u.local_override ? `override: ${u.local_override}` : ""}</td>
                  </tr>))}
              </tbody>
            </table>
          </Card>
        </>)}
    </div>);
}
