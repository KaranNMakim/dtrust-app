import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, CheckCircle2, XCircle } from "lucide-react";
import { api, useApi } from "@/lib/api";
import { issueType, plainError } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";
import { Badge, Button, Card, ErrorNote, Hint, Notice } from "@/components/dt-ui";
import { IndexChange, IssueVisual, SourcesTable } from "@/components/issue-visuals";
import { FixDrawer } from "@/components/fix-flow";

const CODES = ["", "C1", "C2", "C3", "C4", "C5"];

function SeverityPill({ issue }) {
    const urgent = issue.severity === "critical";
    const reason = issue.code === "C4" ? "A data loop can quietly corrupt every number that depends on it."
        : urgent ? (issue.impact?.exec_dashboards ? "Shown on executive dashboards, so leaders may be acting on it." : "Used on many dashboards, so the risk spreads widely.")
            : "Not on executive dashboards yet, but it erodes trust over time.";
    return (<Hint text={reason} className="no-underline">
      <Badge className={urgent ? "border-foreground bg-foreground text-white" : "border-border bg-white text-foreground"}>{urgent ? "Urgent" : "Should fix"}</Badge>
    </Hint>);
}

function ImpactLine({ impact }) {
    if (!impact)
        return null;
    return (<span className="text-xs text-muted-foreground">
      Shown on {impact.dashboards} dashboard{impact.dashboards === 1 ? "" : "s"}
      {impact.exec_dashboards ? ` (${impact.exec_dashboards} executive)` : ""} · {impact.viewers.toLocaleString()} viewers a month
    </span>);
}

function Section({ n, title, children }) {
    return (<section className="space-y-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[11px] text-primary">{n}</span>{title}
      </h3>
      <div className="pl-7">{children}</div>
    </section>);
}

function IssueDetail({ x }) {
    const g = x.gap;
    return (<div className="mt-4 space-y-5 border-t border-border pt-4" data-testid="issue-detail">
      <Section n={1} title="What's wrong"><p className="text-sm">{x.what}</p></Section>
      <Section n={2} title="Where it comes from">
        <div className="space-y-3">
          <IssueVisual visual={x.visual}/>
          <SourcesTable rows={x.sources}/>
        </div>
      </Section>
      <Section n={3} title="Why it matters">
        <p className="text-sm">{x.why}</p>
        {g && (<Link className="mt-1 inline-block text-sm text-primary" to={`/reconcile?a=${g.metric_a}&dashboard_a=${g.dashboard_a ?? ""}&b=${g.metric_b}&dashboard_b=${g.dashboard_b ?? ""}`}>
            See exactly why {g.a_label} and {g.b_label} differ →
          </Link>)}
      </Section>
      <Section n={4} title="What happens if you fix it">
        {x.effect ? (<div className="space-y-1 text-sm">
            <div className="flex flex-wrap items-center gap-4">
              <IndexChange before={x.effect.index_before} after={x.effect.index_after}/>
              <span className="text-muted-foreground">Open issues {x.effect.issues_before} → {x.effect.issues_after}</span>
            </div>
            <ul className="space-y-0.5">{x.effect.changes.map((c) => <li key={c.metric_id + c.action}>• <span className="font-medium">{c.name}</span>: {c.detail}</li>)}</ul>
            {x.fix?.kind === "choose_definition" && <p className="text-xs text-muted-foreground">This is the recommended fix. You can change any choice in the next step.</p>}
          </div>) : (<p className="text-sm text-muted-foreground">
            This needs a change by your data team outside Decision Trust. "Fix this" walks you through it and records it once it's done.
          </p>)}
      </Section>
    </div>);
}

function DismissInline({ issue, onDone }) {
    const [open, setOpen] = useState(false);
    const [reason, setReason] = useState("");
    const [err, setErr] = useState(null);
    if (!open)
        return <button className="text-xs text-muted-foreground hover:underline" data-testid="not-an-issue" onClick={() => setOpen(true)}>Not a real issue</button>;
    return (<div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/40 p-3">
      <input className="h-9 flex-1 rounded-md border border-border px-3 text-sm" placeholder="Why isn't this a real issue? (saved as a decision)" value={reason} onChange={(e) => setReason(e.target.value)}/>
      <Button variant="outline" className="h-9" disabled={reason.trim().length < 3} onClick={async () => {
            try {
                await api(`/conflicts/${issue.id}/dismiss`, { method: "POST", body: JSON.stringify({ reason }) });
                onDone();
            }
            catch (e) {
                setErr(plainError(e.message));
            }
        }}>Dismiss</Button>
      <Button variant="ghost" className="h-9" onClick={() => setOpen(false)}>Cancel</Button>
      {err && <p className="w-full text-xs text-red-700">{err}</p>}
    </div>);
}

function IssueCard({ issue, onFix, onChanged }) {
    const [open, setOpen] = useState(false);
    const [x, setX] = useState(null);
    const [err, setErr] = useState(null);
    async function load() {
        if (x)
            return x;
        try {
            const data = await api(`/conflicts/${issue.id}/explain`);
            setX(data);
            return data;
        }
        catch (e) {
            setErr(plainError(e.message));
            return null;
        }
    }
    return (<Card className="p-4" data-testid="issue-card">
      <div className="flex flex-wrap items-center gap-3">
        <button className="flex flex-1 items-center gap-3 text-left" onClick={async () => { setOpen(!open); if (!open) await load(); }} data-testid="issue-toggle">
          {open ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground"/> : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground"/>}
          <span className="space-y-0.5">
            <span className="flex flex-wrap items-center gap-2">
              <SeverityPill issue={issue}/>
              <span className="text-xs text-muted-foreground">{issueType(issue.code)}</span>
            </span>
            <span className="block font-medium">{issue.title}</span>
            <ImpactLine impact={issue.impact}/>
          </span>
        </button>
        <Button data-testid="fix-this" onClick={async () => { const d = await load(); if (d) onFix(d); }}>Fix this</Button>
      </div>
      {err && <Notice tone="error" className="mt-3">{err}</Notice>}
      {open && x && <IssueDetail x={x}/>}
      {open && !x && !err && <p className="mt-3 text-sm text-muted-foreground">Loading the explanation…</p>}
      {open && <div className="mt-4 border-t border-border pt-3"><DismissInline issue={issue} onDone={onChanged}/></div>}
    </Card>);
}

function Decisions() {
    const { data, error, reload } = useApi("/decisions");
    async function toggle(d, i, done) {
        await api(`/decisions/${d.id}/checklist/${i}`, { method: "PATCH", body: JSON.stringify({ done }) });
        reload();
    }
    if (error)
        return <ErrorNote error={error}/>;
    if (data && !data.length)
        return (<Card className="text-sm text-muted-foreground" data-testid="decisions-empty">
        No decisions yet. Every fix or dismissal you make is recorded here, with who decided, why, and what changed.
      </Card>);
    return (<div className="space-y-3" data-testid="decisions-list">
      {(data ?? []).map((d) => (<Card key={d.id} className="space-y-3 p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold">
                {d.kind === "fix" ? <CheckCircle2 className="h-4 w-4 text-blue-700"/> : <XCircle className="h-4 w-4 text-muted-foreground"/>}
                {d.kind === "fix" ? "Fixed" : "Dismissed"}: {d.issue_title}
              </p>
              <p className="text-xs text-muted-foreground">By {d.decided_by} on {new Date(d.decided_at).toLocaleString()}</p>
            </div>
            {d.kind === "fix" && <IndexChange before={d.trust_index_before} after={d.trust_index_after}/>}
          </div>
          <p className="text-sm"><span className="text-muted-foreground">Reason: </span>{d.reason}</p>
          {d.official_definition && <p className="text-sm"><span className="text-muted-foreground">Official definition: </span>{d.official_definition.name}</p>}
          {d.changes.length > 0 && (<ul className="space-y-0.5 text-sm">{d.changes.map((c) => <li key={c.metric_id + c.action}>• <span className="font-medium">{c.name}</span>: {c.detail}</li>)}</ul>)}
          {d.checklist.length > 0 && (<div>
              <p className="text-xs font-semibold text-muted-foreground">Follow-up checklist</p>
              <ul className="mt-1 space-y-1">
                {d.checklist.map((c, i) => (<li key={c.title}>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={c.done} onChange={(e) => toggle(d, i, e.target.checked)}/>
                      <span className={c.done ? "text-muted-foreground line-through" : ""}>{c.title}</span>
                      {c.owner && <span className="text-xs text-muted-foreground">· {c.owner}</span>}
                    </label>
                  </li>))}
              </ul>
            </div>)}
        </Card>))}
    </div>);
}

export default function ConflictsPage() {
    const { ws } = useWorkspace();
    const [tab, setTab] = useState("issues");
    const [code, setCode] = useState("");
    const { data, error, reload } = useApi(`/conflicts${code ? `?code=${code}` : ""}`);
    const [fixing, setFixing] = useState(null);
    return (<div className="mx-auto max-w-5xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Issues to fix</h1>
        <p className="text-sm text-muted-foreground">Problems that make your numbers disagree or hard to trust, most urgent first. Open one to see where it comes from, then press "Fix this".</p>
      </header>
      <div className="flex gap-1 border-b border-border">
        {[["issues", "Open issues"], ["decisions", "Decisions"]].map(([k, l]) => (<button key={k} data-testid={`tab-${k}`} onClick={() => setTab(k)} className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === k ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>{l}</button>))}
      </div>

      {tab === "decisions" ? <Decisions/> : (<>
          <div className="flex flex-wrap gap-2">
            {CODES.map((c) => (<button key={c || "all"} onClick={() => setCode(c)} className={`rounded-full border px-3 py-1 text-xs ${code === c ? "border-primary bg-primary/10" : "border-border bg-white"}`}>
                {c ? issueType(c) : "All issues"}
              </button>))}
          </div>
          <ErrorNote error={error}/>
          <div className="space-y-3">
            {(data ?? []).map((c) => <IssueCard key={c.id} issue={c} onFix={setFixing} onChanged={reload}/>)}
            {data?.length === 0 && (ws === "mine" && !code ? (<Card className="space-y-2 text-sm" data-testid="issues-empty-mine">
                  <p className="font-medium">No issues found yet.</p>
                  <p className="text-muted-foreground">Add more dashboards so Decision Trust can compare definitions.</p>
                  <p><Link to="/ingest" className="text-primary">Add data</Link> · <span className="text-muted-foreground">or switch to the Acme demo in the sidebar to see how it works</span></p>
                </Card>) : (<Card className="text-sm text-muted-foreground" data-testid="issues-empty">No issues left here. Your numbers agree.</Card>))}
          </div>
        </>)}

      <FixDrawer issue={fixing} open={!!fixing} onOpenChange={(o) => { if (!o) { setFixing(null); reload(); } }} onDone={() => reload()}/>
    </div>);
}
