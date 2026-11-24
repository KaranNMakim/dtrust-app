import { useState } from "react";
import { useApi } from "@/lib/api";
import { Card, ComponentBars, ErrorNote, ScorePill } from "@/components/dt-ui";
export default function RecommendationsPage() {
    const { data, error } = useApi("/recommendations");
    const [sel, setSel] = useState(null);
    const detail = useApi(sel ? `/recommendations/${sel}/score` : null);
    return (<div className="mx-auto max-w-6xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">AI recommendations</h1>
        <p className="text-sm text-muted-foreground">A model being confident isn't the same as being trustworthy. Each recommendation is scored on whether it explains itself, the quality of the data it uses, its track record and company rules.</p>
      </header>
      <ErrorNote error={error}/>
      <div className="grid gap-5 md:grid-cols-[3fr_2fr]">
        <Card className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-muted/60 text-left text-xs text-muted-foreground">
              <tr><th className="px-4 py-2">Trust</th><th className="px-4 py-2">Recommendation</th><th className="px-4 py-2">Model</th><th className="px-4 py-2 text-right">Model conf.</th></tr>
            </thead>
            <tbody>
              {(data ?? []).map((r) => (<tr key={r.id} onClick={() => setSel(r.id)} className={`cursor-pointer border-t border-border hover:bg-muted/40 ${sel === r.id ? "bg-muted/60" : ""}`}>
                  <td className="px-4 py-2"><ScorePill score={r.trust_score} zone={r.zone}/></td>
                  <td className="px-4 py-2">{r.title}</td>
                  <td className="px-4 py-2 text-muted-foreground">{r.model}</td>
                  <td className="px-4 py-2 text-right text-muted-foreground">{r.model_confidence.toFixed(2)}</td>
                </tr>))}
            </tbody>
          </table>
        </Card>
        {detail.data && (<Card>
            <h2 className="mb-1 font-semibold">{detail.data.name}</h2>
            <p className="mb-4 text-sm text-muted-foreground">{detail.data.explanation}</p>
            <ComponentBars components={detail.data.components}/>
          </Card>)}
      </div>
    </div>);
}
