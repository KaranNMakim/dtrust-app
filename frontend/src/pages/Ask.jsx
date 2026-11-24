import { Link } from "react-router-dom";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { CostTag, useWorkspace } from "@/lib/workspace";
import { Button, Card, CardTitle, CertBadge, ComponentBars, ErrorNote, Input, ScorePill, ScoreRing } from "@/components/dt-ui";
import { ReconcileView } from "@/components/reconcile-view";
const SUGGESTIONS = [
    "Which revenue metric should I trust?",
    "Why does Sales QBR revenue differ from the Board Pack?",
    "Which gross margin should go in the board pack?",
    "Why is Revenue (Sales) so low?",
    "Can we trust recommendation r2?",
    "Show me conflicts on churn",
];
function AskInner() {
    const [params, setParams] = useSearchParams();
    const { ws } = useWorkspace();
    const [q, setQ] = useState(params.get("q") ?? SUGGESTIONS[0]);
    const [res, setRes] = useState(null);
    const [err, setErr] = useState(null);
    const [busy, setBusy] = useState(false);
    async function run(question) {
        setBusy(true);
        setErr(null);
        try {
            setRes(await api("/ask", { method: "POST", body: JSON.stringify({ question }) }, { paid: true }));
        }
        catch (e) {
            setErr(e.message);
        }
        finally {
            setBusy(false);
        }
    }
    const started = useRef(false);
    useEffect(() => {
        if (started.current)
            return;
        started.current = true;
        if (params.get("q")) {
            run(params.get("q"));
            setParams({}, { replace: true });
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (<div className="mx-auto max-w-4xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Ask</h1>
        <p className="text-sm text-muted-foreground">Ask in plain English which number to trust, why two numbers differ, or who owns a metric. Answers come only from your metadata, with sources.</p>
      </header>
      <form className="flex gap-3" onSubmit={(e) => { e.preventDefault(); run(q); }}>
        <Input data-testid="ask-input" value={q} onChange={(e) => setQ(e.target.value)}/>
        <Button data-testid="ask-submit" type="submit" className="h-11 whitespace-nowrap" disabled={busy}>{busy ? "Thinking…" : <>Ask <CostTag/></>}</Button>
      </form>
      <div className="flex flex-wrap gap-2">
        {ws === "demo" && SUGGESTIONS.map((s) => (<button key={s} data-testid="ask-suggestion" onClick={() => { setQ(s); run(s); }} className="rounded-full border border-border bg-white px-3 py-1 text-xs hover:bg-muted">
            {s}
          </button>))}
      </div>
      <ErrorNote error={err}/>
      {res && <Answer res={res}/>}
    </div>);
}
function Answer({ res }) {
    const cm = res.certified_metric;
    return (<div className="space-y-4">
      {cm && (<Card className="flex items-start justify-between gap-6">
          <div className="space-y-2">
            <CertBadge certification={cm.certification}/>
            <Link to={`/metrics/${cm.id}`} className="block text-xl font-semibold hover:underline">{cm.name}</Link>
            <p className="text-sm text-muted-foreground">Calculated as: {cm.formula_plain ?? cm.formula}</p>
            <p className="text-sm">Owner: {cm.owner.name ?? "none"} · {cm.owner.team ?? "no team"}</p>
            {res.lineage && <p className="text-xs text-muted-foreground">Where the data comes from: {res.lineage.join(" → ")}</p>}
          </div>
          <ScoreRing score={cm.trust_score} zone={cm.zone}/>
        </Card>)}

      <Card className="bg-muted/50">
        <p className="text-sm leading-relaxed">{res.explanation}</p>
        <p className="mt-2 text-xs text-muted-foreground">
          Answer confidence {res.confidence.toFixed(2)} · cites {res.citations.length} graph node(s) · {res.latency_ms} ms ·{" "}
          {res.explanation_source === "claude" ? "written by Claude from graph facts" : "template (no LLM configured)"}
        </p>
      </Card>

      {res.conflicts && res.conflicts.length > 0 && (<Card>
          <CardTitle className="mb-3">Conflicting definitions ({res.conflicts.length})</CardTitle>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr><th className="pb-2">Metric</th><th className="pb-2">Score</th><th className="pb-2">Why it differs</th><th className="pb-2 text-right">Used in</th></tr>
            </thead>
            <tbody>
              {res.conflicts.map((r) => (<tr key={r.metric_id} className="border-t border-border">
                  <td className="py-2"><Link className="hover:underline" to={`/metrics/${r.metric_id}`}>{r.name}</Link></td>
                  <td className="py-2"><ScorePill score={r.trust_score} zone={r.zone}/></td>
                  <td className="py-2 text-muted-foreground">{r.difference}</td>
                  <td className="py-2 text-right text-muted-foreground">{r.used_in} dashboard(s)</td>
                </tr>))}
            </tbody>
          </table>
        </Card>)}

      {res.reconciliation && <ReconcileView rec={res.reconciliation}/>}

      {res.score && (<Card>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">{res.score.name}</h3>
            <ScoreRing score={res.score.score} zone={res.score.zone} size={88}/>
          </div>
          <ComponentBars components={res.score.components}/>
        </Card>)}

      {res.conflicts_found && (<Card>
          {res.conflicts_found.map((c) => (<p key={c.id} className="border-t border-border py-2 text-sm first:border-0">{c.title} · {c.blast_radius} dashboards</p>))}
        </Card>)}

      {res.recommendations && (<Card>
          {res.recommendations.map((r) => (<p key={r.entity_id} className="flex justify-between border-t border-border py-2 text-sm first:border-0">
              <span>{r.name}</span><ScorePill score={r.score} zone={r.zone}/>
            </p>))}
        </Card>)}
    </div>);
}
export default function AskPage() {
    return (<Suspense>
      <AskInner />
    </Suspense>);
}
