import { Link } from "react-router-dom";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { Card, CertBadge, ErrorNote, Input, ScorePill } from "@/components/dt-ui";
export default function MetricsPage() {
    const { data, error } = useApi("/metrics");
    const [q, setQ] = useState("");
    const rows = (data ?? []).filter((m) => (m.name + m.formula + (m.team ?? "")).toLowerCase().includes(q.toLowerCase()));
    return (<div className="mx-auto max-w-6xl space-y-5">
      <header><h1 className="text-2xl font-semibold">Metrics</h1><p className="text-sm text-muted-foreground">Every metric in this workspace with its trust score, owner and the dashboards that show it. Open one to see why it scored as it did.</p></header>
      <Input placeholder="Filter by name, formula or team" value={q} onChange={(e) => setQ(e.target.value)}/>
      <ErrorNote error={error}/>
      <Card className="p-0">
        <table className="w-full text-sm">
          <thead className="bg-muted/60 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Score</th><th className="px-4 py-2">Metric</th><th className="px-4 py-2">Term</th>
              <th className="px-4 py-2">Owner</th><th className="px-4 py-2">Team</th><th className="px-4 py-2 text-right">Dashboards</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (<tr key={m.id} className="border-t border-border hover:bg-muted/40">
                <td className="px-4 py-2"><ScorePill score={m.trust_score} zone={m.zone}/></td>
                <td className="px-4 py-2">
                  <Link to={`/metrics/${m.id}`} className="font-medium hover:underline">{m.name}</Link>{" "}
                  <CertBadge certification={m.certification}/>
                </td>
                <td className="px-4 py-2 text-muted-foreground">{m.glossary_term ?? "—"}</td>
                <td className="px-4 py-2 text-muted-foreground">{m.owner_email ?? <span className="text-red-700">none</span>}</td>
                <td className="px-4 py-2 text-muted-foreground">{m.team ?? "—"}</td>
                <td className="px-4 py-2 text-right text-muted-foreground">{m.used_in}</td>
              </tr>))}
          </tbody>
        </table>
      </Card>
    </div>);
}
