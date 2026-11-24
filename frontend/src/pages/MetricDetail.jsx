import { Link, useParams } from "react-router-dom";
import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { Button, Card, CardTitle, CertBadge, ComponentBars, ErrorNote, Hint, Input, Notice, ScoreRing } from "@/components/dt-ui";
import { MoreActions, PrimaryAction, PublishCard } from "@/components/metric-actions";
import { issueType, plainError } from "@/lib/format";

function ConfirmPanel({ title, body, confirmLabel, onConfirm, onCancel, busy, testId }) {
    return (<Card data-testid={testId} className="space-y-3 border-primary/30">
      <p className="font-semibold">{title}</p>
      <p className="text-sm text-muted-foreground">{body}</p>
      <div className="flex gap-2">
        <Button data-testid={`${testId}-confirm`} disabled={busy} onClick={onConfirm}>{confirmLabel}</Button>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </Card>);
}

function OwnerPanel({ current, onSave, onCancel, busy }) {
    const [owner, setOwner] = useState(current ?? "");
    return (<Card data-testid="owner-panel" className="space-y-3 border-primary/30">
      <p className="font-semibold">{current ? "Change owner" : "Assign an owner"}</p>
      <p className="text-sm text-muted-foreground">The owner answers questions about this number and approves changes to it. Metrics with an owner score higher on the ownership check.</p>
      <div className="flex gap-2">
        <Input data-testid="owner-input" className="h-10 max-w-sm" type="email" placeholder="name@company.com" value={owner} onChange={(e) => setOwner(e.target.value)}/>
        <Button data-testid="owner-save" disabled={busy || !owner.includes("@")} onClick={() => onSave(owner)}>Save owner</Button>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </Card>);
}

function Header({ m, s, actions }) {
    const penalties = s.penalties.reduce((n, p) => n + p.points, 0);
    return (<Card className="flex items-start justify-between gap-6">
      <div className="space-y-3">
        <CertBadge certification={m.certification}/>
        <h1 className="text-2xl font-semibold">{m.name}</h1>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Owner</dt><dd data-testid="metric-owner">{m.owner_email ?? "Nobody yet"}</dd>
          <dt className="text-muted-foreground">Team</dt><dd>{m.team ?? "Not set"}</dd>
          <dt className="text-muted-foreground">Business term</dt><dd>{m.glossary_term ?? "Not linked to the glossary"}</dd>
          {m.data_product && (<><dt className="text-muted-foreground">Comes from</dt><dd>{m.data_product}</dd></>)}
        </dl>
        <p className="max-w-2xl text-sm text-muted-foreground">{s.explanation}</p>
        <div className="flex flex-wrap gap-2 pt-1">{actions}</div>
      </div>
      <ScoreRing score={s.score} zone={s.zone} hint={`Weighted average of the ${s.components.length} checks below${penalties ? `, minus ${Math.abs(penalties)} points for open issues` : ""}. 80+ is trusted, 50 to 79 needs caution, under 50 should not be trusted.`}/>
    </Card>);
}

function Penalties({ penalties }) {
    if (!penalties.length)
        return null;
    return (<div className="mt-5 border-t border-border pt-3 text-sm">
      <p className="font-medium">Points taken off for open issues</p>
      {penalties.map((p, i) => (<p key={i} className="text-muted-foreground">
          <Hint text="Each open issue involving this metric lowers its score until the issue is fixed.">{issueType(p.code)}: {p.points} points</Hint>
          {p.note ? ` (${p.note})` : ""} · <Link className="text-primary" to="/conflicts">See issue</Link>
        </p>))}
    </div>);
}

function Lineage({ paths }) {
    return (<Card>
      <CardTitle className="mb-2">Where the data comes from</CardTitle>
      {paths.map((p, i) => (<div key={i} className="mb-3 text-xs">
          {p.path.map((n, j) => (<span key={j}>{j > 0 && <span className="text-muted-foreground"> {p.documented[j - 1] ? "→" : "⇢ (undocumented)"} </span>}{n}</span>))}
          <Hint text="Share of the steps from the source system to this metric that are documented in the lineage you loaded." className="block text-muted-foreground">{Math.round(p.coverage * 100)}% of steps documented</Hint>
        </div>))}
      {paths.length === 0 && <p className="text-xs text-muted-foreground">No documented path to a source system yet.</p>}
    </Card>);
}

function Usage({ rows }) {
    return (<Card>
      <CardTitle className="mb-3">Where it is used</CardTitle>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((u) => (<tr key={u.dashboard_id} className="border-t border-border first:border-0">
              <td className="py-2">{u.name}</td>
              <td className="py-2 text-muted-foreground">{u.tool}</td>
              <td className="py-2 text-muted-foreground">{u.audience}</td>
              <td className="py-2 text-muted-foreground"><Hint text="Monthly viewers of this dashboard, from the usage data loaded into this workspace.">{u.monthly_viewers} viewers a month</Hint></td>
              <td className="py-2 text-muted-foreground">{u.local_override ? `Changed on this dashboard: ${u.local_override}` : ""}</td>
            </tr>))}
        </tbody>
      </table>
    </Card>);
}

export default function MetricDetail() {
    const { id } = useParams();
    const metric = useApi(`/metrics/${id}`);
    const score = useApi(`/metrics/${id}/score`);
    const usage = useApi(`/metrics/${id}/usage`);
    const lineage = useApi(`/metrics/${id}/lineage`);
    const [panel, setPanel] = useState(null);
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState(null);
    async function act(path, body, done) {
        setBusy(true);
        setMsg(null);
        try {
            await api(path, { method: "POST", body: JSON.stringify(body) });
            setMsg({ tone: "info", text: `${done} Trust scores have been recalculated.` });
            setPanel(null);
            metric.reload();
            score.reload();
        }
        catch (e) {
            setMsg({ tone: "error", text: plainError(e.message) });
        }
        finally {
            setBusy(false);
        }
    }
    const m = metric.data;
    const s = score.data;
    const term = m?.glossary_term ?? "this term";
    return (<div className="mx-auto max-w-5xl space-y-5">
      <ErrorNote error={metric.error}/>
      {m && s && (<>
          <Header m={m} s={s} actions={<>
              <PrimaryAction metric={m} score={s.score} busy={busy} onApprove={() => setPanel("approve")} onAssign={() => setPanel("owner")}/>
              <MoreActions metric={m} onRetire={() => setPanel("retire")} onPublish={() => setPanel("publish")} onChangeOwner={() => setPanel("owner")}/>
            </>}/>
          {msg && <Notice tone={msg.tone} data-testid="action-message">{msg.text}</Notice>}
          {panel === "approve" && <ConfirmPanel testId="approve-panel" busy={busy} title="Approve as the official definition?" body={`This marks ${m.name} as the company's official definition of ${term}. Other definitions of ${term} will be compared against it, and trust scores will be recalculated.`} confirmLabel="Approve" onConfirm={() => act(`/metrics/${id}/certify`, { reason: "Approved in Decision Trust" }, "Approved as the official definition.")} onCancel={() => setPanel(null)}/>}
          {panel === "retire" && <ConfirmPanel testId="retire-panel" busy={busy} title="Retire this definition?" body={`${m.name} will no longer be treated as a valid definition. It stays visible for history, and trust scores will be recalculated.`} confirmLabel="Retire" onConfirm={() => act(`/metrics/${id}/deprecate`, { reason: "Retired in Decision Trust" }, "Definition retired.")} onCancel={() => setPanel(null)}/>}
          {panel === "owner" && <OwnerPanel current={m.owner_email} busy={busy} onSave={(owner) => act(`/metrics/${id}/owner`, { owner_email: owner }, `Owner set to ${owner}.`)} onCancel={() => setPanel(null)}/>}
          {panel === "publish" && <PublishCard metricId={id} onClose={() => setPanel(null)}/>}

          <div className="grid gap-5 md:grid-cols-[2fr_1fr]">
            <Card>
              <CardTitle className="mb-4">Why this score</CardTitle>
              <ComponentBars components={s.components}/>
              <Penalties penalties={s.penalties}/>
            </Card>
            <div className="space-y-5">
              <Lineage paths={lineage.data ?? []}/>
              <Card className="space-y-2 text-sm">
                <CardTitle>Not matching another number?</CardTitle>
                <Link data-testid="compare-link" className="text-primary" to={`/reconcile?a=${id}`}>Compare it with another metric →</Link>
              </Card>
            </div>
          </div>

          <Usage rows={usage.data ?? []}/>
          <details className="rounded-lg border border-border bg-white px-5 py-3 text-sm" data-testid="technical-definition">
            <summary className="cursor-pointer select-none font-medium text-muted-foreground">Technical definition (for your data engineer)</summary>
            <p className="mt-2 font-mono text-xs">{m.formula}</p>
            <p className="mt-1 text-xs text-muted-foreground">Refreshed {m.grain ?? ""} · expected every {m.refresh_sla_hours} hours</p>
          </details>
        </>)}
    </div>);
}
