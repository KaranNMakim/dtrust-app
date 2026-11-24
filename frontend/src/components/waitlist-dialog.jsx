import { useEffect, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { api, BACKEND_URL } from "@/lib/api";
import { Button, Input, Notice } from "@/components/dt-ui";

const PREMIUM = `${BACKEND_URL}/api/premium`;

export function useWaitlist() {
    const [joined, setJoined] = useState(false);
    useEffect(() => {
        const load = () => api("/waitlist", undefined, { base: PREMIUM }).then((d) => setJoined(d.joined)).catch(() => { });
        load();
        window.addEventListener("dt:waitlist-joined", load);
        return () => window.removeEventListener("dt:waitlist-joined", load);
    }, []);
    return joined;
}

export function WaitlistDialog({ open, onClose }) {
    const [subject, setSubject] = useState("Premium for my team");
    const [reason, setReason] = useState("");
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState(null);
    const [editing, setEditing] = useState(false);
    const joined = useWaitlist();
    if (!open)
        return null;
    async function submit(e) {
        e.preventDefault();
        setBusy(true);
        setMsg(null);
        try {
            await api("/waitlist", { method: "POST", body: JSON.stringify({ subject, reason }) }, { base: PREMIUM });
            setMsg({ ok: true, text: "You're on the premium waitlist. We'll email you when your spot opens." });
            window.dispatchEvent(new Event("dt:waitlist-joined"));
            setReason("");
            setEditing(false);
        }
        catch (err) {
            setMsg({ ok: false, text: err.status === 422 ? "Please add a subject and a reason of at least 10 characters." : err.message });
        }
        finally {
            setBusy(false);
        }
    }
    const close = () => { setMsg(null); setReason(""); setEditing(false); onClose(); };
    if (joined && !editing)
        return (<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" data-testid="waitlist-dialog">
        <div className="w-full max-w-lg space-y-4 rounded-lg border border-border bg-background p-6 shadow-xl" data-testid="waitlist-joined">
          <div className="flex items-start justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold"><Check className="h-5 w-5 text-primary"/>You're on the premium waitlist</h2>
            <button type="button" data-testid="waitlist-close" onClick={close} className="rounded-md p-1 hover:bg-muted"><X className="h-4 w-4"/></button>
          </div>
          <p className="text-sm text-muted-foreground">{msg?.ok ? msg.text : "We'll email your account address when your spot opens."}</p>
          <div className="flex justify-end gap-2">
            <Button data-testid="waitlist-add-note" variant="outline" onClick={() => { setMsg(null); setEditing(true); }}>Add a note</Button>
            <Button data-testid="waitlist-done" onClick={close}>Done</Button>
          </div>
        </div>
      </div>);
    return (<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" data-testid="waitlist-dialog">
      <form onSubmit={submit} className="w-full max-w-lg space-y-4 rounded-lg border border-border bg-background p-6 shadow-xl">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">Join the premium waitlist</h2>
            <p className="text-sm text-muted-foreground">Premium brings team workspaces, live BI connectors and volume pricing. Tell us what you need and we'll reach out when your spot opens.</p>
          </div>
          <button type="button" data-testid="waitlist-close" onClick={close} className="rounded-md p-1 hover:bg-muted"><X className="h-4 w-4"/></button>
        </div>
        <label className="block space-y-1 text-sm font-medium">
          <span>Subject</span>
          <Input data-testid="waitlist-subject" value={subject} maxLength={120} onChange={(e) => setSubject(e.target.value)} required/>
        </label>
        <label className="block space-y-1 text-sm font-medium">
          <span>Reason</span>
          <textarea data-testid="waitlist-reason" value={reason} maxLength={2000} rows={5} required onChange={(e) => setReason(e.target.value)} placeholder="e.g. We have 40 analysts and want to reconcile our Power BI and Tableau revenue dashboards every week." className="w-full rounded-md border border-border bg-white px-4 py-3 text-sm font-normal outline-none focus:ring-2 focus:ring-primary/40"/>
        </label>
        {msg && <Notice tone={msg.ok ? "info" : "error"} data-testid="waitlist-message">{msg.text}</Notice>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={close}>Cancel</Button>
          <Button data-testid="waitlist-submit" type="submit" disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin"/> : "Join waitlist"}</Button>
        </div>
      </form>
    </div>);
}
