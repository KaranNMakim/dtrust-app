// First-visit guided tour of the Acme demo. Lives in the app shell so it follows the user across pages.
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import { Button } from "@/components/dt-ui";
import { useWorkspace } from "@/lib/workspace";

const KEY = "dt-tour-step"; // number while running, "done" when finished or skipped
const COMPARE = "/reconcile?a=m_rev_sales&dashboard_a=d_sales_qbr&b=m_net_rev_fin&dashboard_b=d_board";

const STEPS = [
    { path: "/", title: "The argument",
        text: "Acme's quarterly sales review turned into a 20-minute argument: Sales said revenue was ₹1,258 crore, the Board Pack said ₹1,128 crore. Who is right?" },
    { path: COMPARE, title: "Every reason, step by step",
        text: "Here are the two numbers side by side, with every reason they differ: different definition, hidden filter, different dates and source systems." },
    { path: COMPARE, title: "The bridge",
        text: "Bookings counted instead of invoices, a hidden Exports filter, and returns, discounts and rebates not deducted. 95% of the gap is explained; the rest is flagged, not hidden." },
    { path: "/conflicts", title: "Fix it once",
        text: "Pick one definition, rename or retire the others, and record the decision, so the argument doesn't happen again. Press \"Fix this\" on the revenue issue to try it." },
];

export function replayTour() {
    localStorage.setItem(KEY, "0");
    window.dispatchEvent(new Event("dt:tour"));
}

function read() {
    const v = localStorage.getItem(KEY);
    if (v === null)
        return 0;
    if (v === "done")
        return null;
    const n = Number(v);
    return Number.isInteger(n) && n >= 0 && n < STEPS.length ? n : null;
}

export function TourHost() {
    const { ws } = useWorkspace();
    const navigate = useNavigate();
    const loc = useLocation();
    const [step, setStep] = useState(read());

    useEffect(() => {
        const on = () => setStep(read());
        window.addEventListener("dt:tour", on);
        return () => window.removeEventListener("dt:tour", on);
    }, []);

    useEffect(() => {
        if (step === null || ws !== "demo")
            return;
        const want = STEPS[step].path;
        if (loc.pathname + loc.search !== want && loc.pathname !== want.split("?")[0])
            navigate(want);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [step, ws]);

    if (step === null || ws !== "demo")
        return null;
    const go = (n) => {
        if (n >= STEPS.length || n < 0) {
            localStorage.setItem(KEY, "done");
            setStep(null);
            return;
        }
        localStorage.setItem(KEY, String(n));
        setStep(n);
    };
    const s = STEPS[step];
    return (<div role="dialog" aria-label="Product tour" data-testid="tour" className="fixed bottom-6 right-6 z-50 w-[22rem] rounded-lg border border-primary/30 bg-white p-4 shadow-xl">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">Tour · {step + 1} of {STEPS.length}</p>
        <button aria-label="Close tour" data-testid="tour-skip" onClick={() => go(STEPS.length)} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4"/></button>
      </div>
      <p className="mt-1 font-semibold">{s.title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{s.text}</p>
      <div className="mt-4 flex items-center justify-between">
        <button className="text-xs text-muted-foreground hover:underline" onClick={() => go(STEPS.length)}>Skip tour</button>
        <div className="flex gap-2">
          {step > 0 && <Button variant="ghost" className="h-8" onClick={() => go(step - 1)}>Back</Button>}
          <Button className="h-8" data-testid="tour-next" onClick={() => go(step + 1)}>{step === STEPS.length - 1 ? "Finish" : "Next"}</Button>
        </div>
      </div>
    </div>);
}
