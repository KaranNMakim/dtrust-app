import { Link } from "react-router-dom";
import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { Button, ScorePill } from "@/components/dt-ui";
import { zoneOf } from "@/lib/utils";
export function MigrationPlan({ conflictId, onChanged }) {
    const { data, error, reload } = useApi(`/conflicts/${conflictId}/plan`);
    const [done, setDone] = useState({});
    async function execute(v) {
        const path = v.action.endpoint.replace(/^POST \/api\/v1/, "");
        try {
            await api(path, { method: "POST", body: JSON.stringify(v.action.body ?? {}) });
            setDone((d) => ({ ...d, [v.metric_id]: "Done" }));
            onChanged();
            reload();
        }
        catch (e) {
            setDone((d) => ({ ...d, [v.metric_id]: e.message }));
        }
    }
    if (error)
        return <p className="mt-3 text-xs text-red-700">{error}</p>;
    if (!data)
        return <p className="mt-3 text-xs text-muted-foreground">Building plan…</p>;
    return (<div className="mt-4 space-y-4 border-t border-border pt-4 text-sm">
      {data.canonical && (<p>
          Keep <Link className="font-semibold hover:underline" to={`/metrics/${data.canonical.metric_id}`}>{data.canonical.name}</Link>{" "}
          as the definition of <b>{data.term}</b>.{" "}
          {data.impact && <span className="text-muted-foreground">Touches {data.impact.dashboards} dashboards ({data.impact.exec_dashboards} executive), {data.impact.monthly_viewers} viewers a month.</span>}
        </p>)}
      {data.variants && (<div className="space-y-2">
          {data.variants.map((v) => (<div key={v.metric_id} className="rounded-md border border-border p-3">
              <div className="flex items-center gap-3">
                <ScorePill score={v.trust_score} zone={zoneOf(v.trust_score)}/>
                <span className="font-medium">{v.name}</span>
                <span className="text-xs text-muted-foreground">{v.used_in} dashboard(s)</span>
                <span className="flex-1"/>
                <Link className="text-xs text-primary" to={`/reconcile?a=${v.metric_id}&b=${data.canonical?.metric_id}`}>Compare</Link>
                <Button variant={v.action.type === "deprecate" ? "danger" : "outline"} className="h-8" disabled={!!done[v.metric_id]} onClick={() => execute(v)}>
                  {done[v.metric_id] ?? v.action.label}
                </Button>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{v.why}</p>
              <p className="mt-1 text-xs">{v.reconciliation}</p>
            </div>))}
        </div>)}
      <ol className="space-y-2">
        {data.steps.map((s) => (<li key={s.step} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{s.step}</span>
            <div>
              <p className="font-medium">{s.title} <span className="font-normal text-muted-foreground">· {s.owner ?? "unassigned"}</span></p>
              <p className="text-xs text-muted-foreground">{s.detail}</p>
            </div>
          </li>))}
      </ol>
    </div>);
}
