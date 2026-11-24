// Guided "Fix this" flow: choose the definition → decide what happens to the others → confirm and record.
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { plainError } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";
import { Button, Input, Notice } from "@/components/dt-ui";
import { IndexChange } from "@/components/issue-visuals";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";

function Steps({ labels, current }) {
    return (<ol className="flex items-center gap-2 text-xs" data-testid="fix-steps">
      {labels.map((l, i) => (<li key={l} className="flex items-center gap-2">
          <span className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] font-semibold ${i < current ? "border-primary bg-primary text-white" : i === current ? "border-primary text-primary" : "border-border text-muted-foreground"}`}>
            {i < current ? <Check className="h-3.5 w-3.5"/> : i + 1}
          </span>
          <span className={i === current ? "font-medium text-foreground" : "text-muted-foreground"}>{l}</span>
          {i < labels.length - 1 && <span className="mx-1 h-px w-6 bg-border"/>}
        </li>))}
    </ol>);
}

function Choice({ selected, onClick, title, children, testId }) {
    return (<button type="button" data-testid={testId} onClick={onClick} className={`w-full rounded-md border p-3 text-left transition-colors ${selected ? "border-primary bg-primary/5 ring-1 ring-primary/40" : "border-border bg-white hover:bg-muted/50"}`}>
      <p className="text-sm font-medium">{title}</p>
      {children && <div className="mt-1 text-xs text-muted-foreground">{children}</div>}
    </button>);
}

function Preview({ preview, loading }) {
    if (loading && !preview)
        return <p className="text-xs text-muted-foreground">Working out what changes…</p>;
    if (!preview)
        return null;
    return (<div className="space-y-2 rounded-md border border-border bg-muted/40 p-3" data-testid="fix-preview">
      <div className="flex flex-wrap items-center gap-4">
        <IndexChange before={preview.index_before} after={preview.index_after}/>
        <span className="text-sm text-muted-foreground">Open issues {preview.issues_before} → {preview.issues_after}</span>
      </div>
      <ul className="space-y-1 text-sm">
        {preview.changes.map((c) => <li key={c.metric_id + c.action}>• <span className="font-medium">{c.name}</span>: {c.detail}</li>)}
      </ul>
      {preview.warnings?.map((w) => <p key={w} className="text-xs text-amber-800">{w}</p>)}
    </div>);
}

export function FixDrawer({ issue, open, onOpenChange, onDone }) {
    const { ws } = useWorkspace();
    const fix = issue?.fix;
    const kind = fix?.kind;
    const labels = kind === "choose_definition" ? ["Choose the definition", "Decide on the others", "Confirm"]
        : kind === "assign_owner" ? ["Choose an owner", "Confirm"] : ["Confirm the fix"];
    const [step, setStep] = useState(0);
    const [canonical, setCanonical] = useState(fix?.recommended_id ?? null);
    const [choices, setChoices] = useState({});
    const [owner, setOwner] = useState(fix?.suggested_owner ?? "");
    const [reason, setReason] = useState("");
    const [preview, setPreview] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [result, setResult] = useState(null);
    const timer = useRef(null);

    // Reset when a different issue opens.
    useEffect(() => {
        if (!issue)
            return;
        setStep(0);
        setCanonical(fix?.recommended_id ?? null);
        setOwner(fix?.suggested_owner ?? "");
        setReason("");
        setResult(null);
        setError(null);
        const init = {};
        for (const v of fix?.variants ?? [])
            init[v.metric_id] = { action: v.action, term: v.term ?? "", definition: v.definition ?? "", new_name: v.new_name ?? "", why: v.why, dashboards: v.dashboards };
        setChoices(init);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [issue?.id]);

    const others = useMemo(() => (fix?.candidates ?? []).filter((c) => c.metric_id !== canonical), [fix, canonical]);

    const body = useMemo(() => {
        if (kind === "choose_definition")
            return {
                canonical_id: canonical,
                variants: others.map((o) => {
                    const ch = choices[o.metric_id] ?? { action: "retire" };
                    return { metric_id: o.metric_id, action: ch.action, term: ch.term || null, definition: ch.definition || null, new_name: ch.new_name || null };
                }),
            };
        if (kind === "assign_owner")
            return { owner_email: owner || null };
        return {};
    }, [kind, canonical, others, choices, owner]);

    useEffect(() => {
        if (!open || !issue || kind === "confirm")
            return;
        if (kind === "assign_owner" && !/^[^@\s]+@[^@\s]+$/.test(owner))
            return setPreview(null);
        clearTimeout(timer.current);
        timer.current = setTimeout(async () => {
            setLoading(true);
            try {
                setPreview(await api(`/conflicts/${issue.id}/preview`, { method: "POST", body: JSON.stringify(body) }));
            }
            catch (e) {
                setError(plainError(e.message));
            }
            finally {
                setLoading(false);
            }
        }, 300);
        return () => clearTimeout(timer.current);
    }, [open, issue, kind, body, owner]);

    async function apply() {
        setError(null);
        setLoading(true);
        try {
            const checklist = (issue.checklist ?? []).map((c) => ({ title: c.title, owner: c.owner, done: false }));
            const out = await api(`/conflicts/${issue.id}/fix`, { method: "POST", body: JSON.stringify({ ...body, reason, checklist }) }, { paid: true });
            setResult(out);
            onDone?.(out);
        }
        catch (e) {
            setError(plainError(e.message));
        }
        finally {
            setLoading(false);
        }
    }

    const setChoice = (id, patch) => setChoices((c) => ({ ...c, [id]: { ...(c[id] ?? { action: "retire" }), ...patch } }));
    const last = labels.length - 1;
    const cost = ws === "mine" ? " · 1 credit" : "";

    return (<Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-2xl" data-testid="fix-drawer">
        <SheetHeader className="space-y-2 pr-6">
          <SheetTitle>Fix: {issue?.title}</SheetTitle>
          <SheetDescription>{issue?.what}</SheetDescription>
          {!result && <Steps labels={labels} current={step}/>}
        </SheetHeader>

        <div className="mt-6 space-y-4">
          {result ? (<div className="space-y-4" data-testid="fix-success">
              <Notice><span className="flex items-center gap-2 font-medium"><CheckCircle2 className="h-4 w-4"/>Fix applied and recorded.</span></Notice>
              <IndexChange before={result.trust_index_before} after={result.trust_index_after}/>
              <ul className="space-y-1 text-sm">{result.changes.map((c) => <li key={c.metric_id + c.action}>• <span className="font-medium">{c.name}</span>: {c.detail}</li>)}</ul>
              <p className="text-sm text-muted-foreground">The decision, the reason and the follow-up checklist are saved under the Decisions tab.</p>
              <Button onClick={() => onOpenChange(false)} data-testid="fix-close">Done</Button>
            </div>) : (<>
            {/* Step: choose the official definition */}
            {kind === "choose_definition" && step === 0 && (<div className="space-y-3">
                <p className="text-sm font-medium">Which definition of this number should everyone use?</p>
                {fix.candidates.map((c) => (<Choice key={c.metric_id} testId="fix-candidate" selected={canonical === c.metric_id} onClick={() => setCanonical(c.metric_id)} title={`${c.name}${c.metric_id === fix.recommended_id ? " · recommended" : ""}`}>
                    Trust score {Math.round(c.trust_score)}{c.approved ? " · already approved" : ""}
                    {c.metric_id === fix.recommended_id && <span className="block">{fix.recommended_reason}</span>}
                  </Choice>))}
              </div>)}

            {/* Step: decide on the others */}
            {kind === "choose_definition" && step === 1 && (<div className="space-y-4">
                <p className="text-sm font-medium">What should happen to the other versions?</p>
                {others.map((o) => {
                    const ch = choices[o.metric_id] ?? { action: "retire" };
                    return (<div key={o.metric_id} className="space-y-2 rounded-md border border-border p-3" data-testid="fix-variant">
                      <p className="text-sm font-semibold">{o.name}</p>
                      {ch.why && <p className="text-xs text-muted-foreground">Suggested because: {ch.why}</p>}
                      <div className="grid gap-2 md:grid-cols-2">
                        <Choice selected={ch.action === "rename"} onClick={() => setChoice(o.metric_id, { action: "rename" })} title="Rename it" testId="fix-rename">
                          It measures something genuinely different, so give it its own name.
                        </Choice>
                        <Choice selected={ch.action === "retire"} onClick={() => setChoice(o.metric_id, { action: "retire" })} title="Retire it" testId="fix-retire">
                          Replace it with the chosen definition on every dashboard{ch.dashboards?.length ? ` (${ch.dashboards.join(", ")})` : ""}.
                        </Choice>
                      </div>
                      {ch.action === "rename" && (<div className="grid gap-2 md:grid-cols-2">
                          <label className="text-xs text-muted-foreground">New name
                            <Input className="mt-1 h-9" value={ch.new_name || ch.term} onChange={(e) => setChoice(o.metric_id, { new_name: e.target.value, term: e.target.value })} placeholder="e.g. Bookings"/>
                          </label>
                          <label className="text-xs text-muted-foreground">What it means
                            <Input className="mt-1 h-9" value={ch.definition} onChange={(e) => setChoice(o.metric_id, { definition: e.target.value })} placeholder="One plain sentence"/>
                          </label>
                        </div>)}
                    </div>);
                })}
                <p className="text-xs font-semibold text-muted-foreground">What will change</p>
                <Preview preview={preview} loading={loading}/>
              </div>)}

            {/* Step: choose an owner */}
            {kind === "assign_owner" && step === 0 && (<div className="space-y-3">
                <p className="text-sm font-medium">Who should own this metric?</p>
                <p className="text-xs text-muted-foreground">The owner decides what the metric means and approves changes to it.</p>
                <Input data-testid="fix-owner" value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="name@company.com"/>
                {fix.suggested_owner && <p className="text-xs text-muted-foreground">Suggested: {fix.suggested_owner} (looks after this business definition).</p>}
                <Preview preview={preview} loading={loading}/>
              </div>)}

            {/* Final step: confirm and record */}
            {step === last && (<div className="space-y-4" data-testid="fix-confirm">
                {kind === "confirm" && (<>
                    <p className="text-sm font-medium">This one needs a change outside Decision Trust. Here's the plan:</p>
                    <ol className="space-y-2 text-sm">
                      {issue.checklist.map((c, i) => (<li key={c.title} className="flex gap-2">
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">{i + 1}</span>
                          <span><span className="font-medium">{c.title}</span>{c.owner ? <span className="text-muted-foreground"> · {c.owner}</span> : null}<span className="block text-xs text-muted-foreground">{c.detail}</span></span>
                        </li>))}
                    </ol>
                    <p className="text-sm">When it's done, record it here: <span className="font-medium">{fix.label}</span>.</p>
                  </>)}
                {kind !== "confirm" && (<>
                    <p className="text-xs font-semibold text-muted-foreground">Summary of changes</p>
                    <Preview preview={preview} loading={loading}/>
                    {issue.checklist?.length > 0 && (<div>
                        <p className="text-xs font-semibold text-muted-foreground">Follow-up checklist (saved with the decision)</p>
                        <ul className="mt-1 space-y-1 text-sm">{issue.checklist.map((c) => <li key={c.title}>☐ {c.title}{c.owner ? <span className="text-muted-foreground"> · {c.owner}</span> : null}</li>)}</ul>
                      </div>)}
                  </>)}
                <label className="block text-sm font-medium">Reason for this decision
                  <textarea data-testid="fix-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3} className="mt-1 w-full rounded-md border border-border p-3 text-sm outline-none focus:ring-2 focus:ring-primary/40" placeholder="e.g. Finance owns recognised revenue; Sales' number is bookings, so it gets its own name."/>
                </label>
              </div>)}

            {error && <Notice tone="error">{error}</Notice>}

            <div className="flex items-center justify-between border-t border-border pt-4">
              <Button variant="ghost" onClick={() => (step === 0 ? onOpenChange(false) : setStep(step - 1))}>{step === 0 ? "Cancel" : "Back"}</Button>
              {step < last ? (<Button data-testid="fix-next" disabled={kind === "assign_owner" && !/^[^@\s]+@[^@\s]+$/.test(owner)} onClick={() => setStep(step + 1)}>Next</Button>)
                : (<Button data-testid="fix-apply" disabled={!reason.trim() || loading} onClick={apply}>{kind === "confirm" ? "Mark as fixed" : "Apply fix"}{cost}</Button>)}
            </div>
          </>)}
        </div>
      </SheetContent>
    </Sheet>);
}
