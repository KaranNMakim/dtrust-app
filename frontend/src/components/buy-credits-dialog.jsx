import { useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { api, BILLING } from "@/lib/api";
import { Button } from "@/components/dt-ui";

export const inr = (n) => `₹${Number(n).toLocaleString("en-IN")}`;

function loadRazorpay() {
    return new Promise((resolve) => {
        if (window.Razorpay)
            return resolve(true);
        const s = document.createElement("script");
        s.src = "https://checkout.razorpay.com/v1/checkout.js";
        s.onload = () => resolve(true);
        s.onerror = () => resolve(false);
        document.body.appendChild(s);
    });
}

export function PackCard({ pack, best, busy, disabled, onBuy }) {
    const per = pack.amount / pack.credits;
    return (<div data-testid={`pack-${pack.id}`} className={`relative flex flex-col rounded-lg border p-4 transition-colors ${best ? "border-primary bg-primary/5" : "border-border bg-white"}`}>
      {best && <span className="absolute -top-2.5 left-4 rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold text-primary-foreground">BEST VALUE</span>}
      <p className="text-sm font-semibold">{pack.name}</p>
      <p className="mt-2 text-3xl font-semibold">{pack.credits}<span className="ml-1 text-sm font-normal text-muted-foreground">credits</span></p>
      <p className="mt-1 text-sm">{inr(pack.amount)}</p>
      <p className="text-xs text-muted-foreground">{inr(per.toFixed(0))} per credit</p>
      <Button data-testid={`buy-${pack.id}`} className="mt-4" disabled={disabled || busy} onClick={() => onBuy(pack)}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin"/> : "Buy"}
      </Button>
    </div>);
}

export function useCheckout(onPaid) {
    const [busy, setBusy] = useState(null);
    const [msg, setMsg] = useState(null);
    async function buy(pack) {
        setBusy(pack.id);
        setMsg(null);
        try {
            if (!(await loadRazorpay()))
                throw new Error("Couldn't load the payment window. Check your connection and try again.");
            const order = await api("/orders", { method: "POST", body: JSON.stringify({ pack_id: pack.id }) }, { base: BILLING });
            const rzp = new window.Razorpay({
                key: order.key_id,
                amount: order.amount,
                currency: order.currency,
                order_id: order.order_id,
                name: "Decision Trust",
                description: order.description,
                prefill: { email: order.email ?? "" },
                theme: { color: "#2259c3" },
                handler: async (resp) => {
                    try {
                        const out = await api("/verify", { method: "POST", body: JSON.stringify(resp) }, { base: BILLING, paid: true });
                        setMsg({ ok: true, text: `Payment received. You now have ${out.credits} credits.` });
                        onPaid?.();
                    }
                    catch (e) {
                        setMsg({ ok: false, text: e.message });
                    }
                    setBusy(null);
                },
                modal: { ondismiss: () => setBusy(null) },
            });
            rzp.on("payment.failed", (resp) => {
                api("/failed", { method: "POST", body: JSON.stringify({ order_id: order.order_id, reason: resp.error?.description }) }, { base: BILLING });
                setMsg({ ok: false, text: resp.error?.description ?? "Payment failed. No credits were charged." });
                setBusy(null);
            });
            rzp.open();
        }
        catch (e) {
            setMsg({ ok: false, text: e.message });
            setBusy(null);
        }
    }
    return { buy, busy, msg };
}

export function BuyCreditsDialog({ open, reason, me, onClose, onPaid, onPremium }) {
    const { buy, busy, msg } = useCheckout(onPaid);
    if (!open)
        return null;
    const packs = me?.packs ?? [];
    return (<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" data-testid="buy-credits-dialog">
      <div className="w-full max-w-2xl rounded-lg border border-border bg-background p-6 shadow-xl">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">Buy credits</h2>
            <p className="text-sm text-muted-foreground">{reason ?? "1 credit = 1 action in your own workspace. The Acme demo stays free."}</p>
          </div>
          <button data-testid="buy-credits-close" onClick={onClose} className="rounded-md p-1 hover:bg-muted"><X className="h-4 w-4"/></button>
        </div>
        <p className="mt-3 text-sm">Balance: <b data-testid="dialog-credit-balance">{me?.credits ?? "…"}</b> credits</p>
        {me && !me.payments_enabled && (<p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">Payments aren't switched on yet. Credit packs can be bought once the owner adds the payment keys.</p>)}
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          {packs.map((p, i) => (<PackCard key={p.id} pack={p} best={i === packs.length - 1} busy={busy === p.id} disabled={!me?.payments_enabled || !!busy} onBuy={buy}/>))}
        </div>
        {msg && (<p data-testid="buy-credits-message" className={`mt-4 flex items-center gap-2 text-sm ${msg.ok ? "text-green-700" : "text-red-700"}`}>
            {msg.ok && <Check className="h-4 w-4"/>}{msg.text}
          </p>)}
        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">Secure checkout by Razorpay: cards, UPI and netbanking. Prices in Indian rupees.</p>
          <button data-testid="dialog-join-waitlist" onClick={onPremium} className="shrink-0 text-xs font-medium text-primary hover:underline">Need more? Join the premium waitlist →</button>
        </div>
      </div>
    </div>);
}
