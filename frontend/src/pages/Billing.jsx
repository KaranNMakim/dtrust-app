import { AlertCircle, Check, Clock, Coins, Lock, Sparkles } from "lucide-react";
import { BILLING, useApi } from "@/lib/api";
import { Button, Card, CardTitle, ErrorNote, Notice } from "@/components/dt-ui";
import { useCredits } from "@/components/credits";
import { useWaitlist } from "@/components/waitlist-dialog";
import { inr, PackCard, useCheckout } from "@/components/buy-credits-dialog";

const FREE_FEATURES = [
    "The full Acme demo company: every page and every action",
    "Ask trust questions and reconcile dashboard numbers",
    "Trust scores with evidence, conflicts and migration plans",
    "Trust Graph, calibration and dbt / Databricks export",
    "Preview what we read from your Power BI or Tableau files",
];

function PaymentStatus({ status }) {
    if (status === "paid")
        return <span className="inline-flex items-center gap-1 font-semibold text-blue-800"><Check className="h-3.5 w-3.5"/>Paid</span>;
    if (status === "failed")
        return <span className="inline-flex items-center gap-1 font-semibold text-red-700"><AlertCircle className="h-3.5 w-3.5"/>Failed</span>;
    return <span className="inline-flex items-center gap-1 text-muted-foreground"><Clock className="h-3.5 w-3.5"/>Not completed</span>;
}

const when = (iso) => new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });

function Plans({ me, onPremium }) {
    const joined = useWaitlist();
    return (<div className="grid gap-5 md:grid-cols-3">
      <Card data-testid="plan-basic" className="border-primary/40">
        <div className="flex items-center justify-between">
          <p className="text-lg font-semibold">Basic</p>
          <span className="rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold text-primary-foreground">YOUR PLAN</span>
        </div>
        <p className="text-sm text-muted-foreground">Free forever. Test-drive everything on the Acme demo company.</p>
        <ul className="mt-4 space-y-1.5 text-sm">
          {FREE_FEATURES.map((f) => <li key={f} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary"/>{f}</li>)}
        </ul>
      </Card>
      <Card data-testid="plan-credits">
        <p className="text-lg font-semibold">My workspace</p>
        <p className="text-sm text-muted-foreground">Your own metrics, saved permanently. Prepaid credits, no subscription: 1 credit per action. New accounts get {me?.free_credits ?? 3} free. Browsing and steward actions stay free.</p>
        <ul className="mt-4 space-y-1.5 text-sm">
          {Object.values(me?.paid_actions ?? {}).map((a) => <li key={a} className="flex gap-2"><Lock className="mt-0.5 h-4 w-4 shrink-0 text-primary"/>{a}</li>)}
        </ul>
      </Card>
      <Card data-testid="plan-premium" className="flex flex-col">
        <div className="flex items-center justify-between">
          <p className="flex items-center gap-2 text-lg font-semibold"><Sparkles className="h-4 w-4 text-primary"/>Premium</p>
          <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">COMING SOON</span>
        </div>
        <p className="text-sm text-muted-foreground">For teams that need more: volume credits, shared workspaces, live BI connectors and onboarding help.</p>
        <span className="flex-1"/>
        <Button data-testid="billing-join-waitlist" className="mt-4" variant={joined ? "outline" : "default"} onClick={onPremium}>{joined ? "You're on the waitlist" : "Join waitlist"}</Button>
      </Card>
    </div>);
}

export default function BillingPage() {
    const { me, refresh, openPremium } = useCredits();
    const hist = useApi("/history", BILLING);
    const { buy, busy, msg } = useCheckout(() => { refresh(); hist.reload(); });
    const packs = me?.packs ?? [];
    return (<div className="mx-auto max-w-5xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Plan & billing</h1>
        <p className="text-sm text-muted-foreground">The Acme demo is free. Credits are only used when you work on your own data.</p>
      </header>
      <Card className="flex items-center gap-4">
        <Coins className="h-8 w-8 text-primary"/>
        <div>
          <p className="text-3xl font-semibold" data-testid="billing-credit-balance">{me?.credits ?? "…"}</p>
          <p className="text-xs text-muted-foreground">credits available</p>
        </div>
      </Card>
      <Plans me={me} onPremium={openPremium}/>
      <div>
        <CardTitle className="mb-3">Credit packs</CardTitle>
        {me && !me.payments_enabled && (<Notice className="mb-3" data-testid="payments-off-notice">Payments aren't switched on yet. Credit packs can be bought once the owner adds the payment keys.</Notice>)}
        <div className="grid gap-4 sm:grid-cols-3">
          {packs.map((p, i) => <PackCard key={p.id} pack={p} best={i === packs.length - 1} busy={busy === p.id} disabled={!me?.payments_enabled || !!busy} onBuy={buy}/>)}
        </div>
        {msg && <Notice className="mt-3" tone={msg.ok ? "info" : "error"} data-testid="billing-message">{msg.text}</Notice>}
      </div>
      <ErrorNote error={hist.error}/>
      <div className="grid gap-5 md:grid-cols-2">
        <Card>
          <CardTitle className="mb-3">Purchases</CardTitle>
          {(hist.data?.purchases ?? []).length === 0 && <p className="text-sm text-muted-foreground">No purchases yet.</p>}
          <table className="w-full text-sm" data-testid="purchases-table">
            <tbody>
              {(hist.data?.purchases ?? []).map((p) => (<tr key={p.order_id} className="border-t border-border first:border-0">
                  <td className="py-2">{p.pack_name} · {p.credits} credits<p className="text-xs text-muted-foreground">{when(p.created_at)}</p></td>
                  <td className="py-2 text-right">{inr(p.amount)}</td>
                  <td className="py-2 pl-3 text-right text-xs"><PaymentStatus status={p.payment_status}/></td>
                </tr>))}
            </tbody>
          </table>
        </Card>
        <Card>
          <CardTitle className="mb-3">Credit activity</CardTitle>
          <table className="w-full text-sm" data-testid="usage-table">
            <tbody>
              {(hist.data?.ledger ?? []).map((u, i) => (<tr key={i} className="border-t border-border first:border-0">
                  <td className="py-2">{u.label ?? u.detail}<p className="max-w-xs truncate text-xs text-muted-foreground">{u.label ? u.detail : ""} {when(u.created_at)}</p></td>
                  <td className="py-2 text-right font-semibold text-foreground">{u.credits > 0 ? `+${u.credits}` : u.credits}</td>
                </tr>))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>);
}
