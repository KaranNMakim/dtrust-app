import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { zoneColor, zoneOf } from "@/lib/utils";
import { Button, Card, CardTitle, ErrorNote, ScorePill } from "@/components/dt-ui";
const LABEL = {
    definition: "One agreed definition", ownership: "Clear owner", lineage: "Where the data comes from",
    usage: "Used as defined", freshness: "Up to date",
};
export default function CalibrationPage() {
    const cal = useApi("/calibration");
    const inc = useApi("/incidents");
    const [msg, setMsg] = useState(null);
    const c = cal.data;
    async function apply(weights) {
        await api("/calibration/apply", { method: "POST", body: JSON.stringify({ weights }) });
        setMsg(weights ? "Suggested weights applied. Scores recomputed." : "Weights reset to defaults.");
        cal.reload();
    }
    return (<div className="mx-auto max-w-5xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Does the score predict trouble?</h1>
        <p className="text-sm text-muted-foreground">
          Checks whether low trust scores really point to trouble, using past incidents: restated numbers, arguments in leadership meetings and decisions taken on a wrong number.
        </p>
      </header>
      <ErrorNote error={cal.error}/>
      {c && (<>
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardTitle>Predictive power (AUC)</CardTitle>
              <p className="mt-2 text-3xl font-semibold">{c.current_auc?.toFixed(2) ?? "n/a"}</p>
              <p className="text-xs text-muted-foreground">0.5 = coin flip · 1.0 = every incident metric scored lower than every clean one</p>
            </Card>
            <Card>
              <CardTitle>Evidence</CardTitle>
              <p className="mt-2 text-3xl font-semibold">{c.incidents}</p>
              <p className="text-xs text-muted-foreground">incidents across {c.metrics_with_incidents} of {c.metrics} metrics</p>
            </Card>
            <Card>
              <CardTitle>Verdict</CardTitle>
              <p className="mt-2 text-sm">{c.recommendation}</p>
              <p className="mt-2 text-xs text-amber-700">{c.caveat}</p>
            </Card>
          </div>

          <Card>
            <CardTitle className="mb-3">Weights: current vs evidence-suggested</CardTitle>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr><th className="pb-2">Component</th><th className="pb-2">Signal (AUC)</th><th className="pb-2">Current</th><th className="pb-2">Suggested</th></tr>
              </thead>
              <tbody>
                {Object.keys(c.current_weights).map((k) => {
                const a = c.component_auc[k];
                return (<tr key={k} className="border-t border-border">
                      <td className="py-2">{LABEL[k] ?? k}</td>
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-32 rounded bg-muted">
                            <div className="h-2 rounded bg-primary" style={{ width: `${Math.max(0, ((a ?? 0.5) - 0.5) * 200)}%` }}/>
                          </div>
                          <span className="text-xs text-muted-foreground">{a?.toFixed(2) ?? "n/a"}</span>
                        </div>
                      </td>
                      <td className="py-2">{Math.round(c.current_weights[k] * 100)}%</td>
                      <td className="py-2 font-medium">{Math.round(c.suggested_weights[k] * 100)}%</td>
                    </tr>);
            })}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted-foreground">
              Suggested weights would give AUC {c.suggested_auc?.toFixed(2)}. They are shrunk halfway towards the current weights so a small sample can&apos;t swing them.
            </p>
            <div className="mt-3 flex gap-2">
              <Button onClick={() => apply(c.suggested_weights)}>Apply suggested</Button>
              <Button variant="outline" onClick={() => apply(null)}>Reset to defaults</Button>
              {msg && <span className="self-center text-xs text-muted-foreground">{msg}</span>}
            </div>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardTitle className="mb-2">Score vs incidents</CardTitle>
              {c.by_metric.map((m) => (<div key={m.metric_id} className="flex items-center justify-between border-t border-border py-1.5 text-sm first:border-0">
                  <span className="flex items-center gap-2"><ScorePill score={m.score} zone={zoneOf(m.score)}/>{m.name}</span>
                  <span className="text-xs" style={{ color: m.incidents ? zoneColor.red : "#64748b" }}>
                    {m.incidents ? `${m.incidents} incident${m.incidents > 1 ? "s" : ""}` : "clean"}
                  </span>
                </div>))}
            </Card>
            <Card>
              <CardTitle className="mb-2">Incident log</CardTitle>
              {(inc.data ?? []).map((i, k) => (<div key={k} className="border-t border-border py-1.5 text-xs first:border-0">
                  <p><span className="font-medium">{i.date}</span> · {i.metric} · {i.type.replace("_", " ")}</p>
                  <p className="text-muted-foreground">{i.note}</p>
                </div>))}
            </Card>
          </div>
        </>)}
    </div>);
}
