import { Link, NavLink, Outlet } from "react-router-dom";
import { useEffect } from "react";
import { UserButton, useAuth } from "@clerk/react";
import { Coins, Lock, Sparkles } from "lucide-react";
import { setTokenGetter } from "@/lib/api";
import { CreditsProvider, useCredits } from "@/components/credits";
import { useWaitlist } from "@/components/waitlist-dialog";

const nav = [
    { href: "/", label: "Home" },
    { href: "/ask", label: "Ask", paid: true },
    { href: "/reconcile", label: "Reconcile", paid: true },
    { href: "/metrics", label: "Metrics" },
    { href: "/conflicts", label: "Conflicts" },
    { href: "/recommendations", label: "Recommendations" },
    { href: "/graph", label: "Trust Graph" },
    { href: "/calibration", label: "Calibration" },
    { href: "/ingest", label: "Ingest", paid: true },
    { href: "/billing", label: "Plan & billing" },
];

function TopBar() {
    const { credits, openBuy, openPremium } = useCredits();
    const low = credits != null && credits <= 1;
    const joined = useWaitlist();
    return (<div className="mb-6 flex items-center justify-end gap-3" data-testid="top-bar">
      <button data-testid="join-waitlist-btn" onClick={openPremium} className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/5">
        <Sparkles className="h-3.5 w-3.5"/>{joined ? "On premium waitlist" : "Join premium waitlist"}
      </button>
      <Link to="/billing" data-testid="plan-badge" className="rounded-full border border-border bg-white px-3 py-1 text-xs text-muted-foreground hover:bg-muted">
        Basic plan · free
      </Link>
      <button data-testid="credit-balance" onClick={() => openBuy()} className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${low ? "border-red-300 bg-red-50 text-red-800" : "border-primary/30 bg-primary/5 text-primary"}`}>
        <Coins className="h-3.5 w-3.5"/>
        {credits ?? "…"} credit{credits === 1 ? "" : "s"}
      </button>
      <button data-testid="buy-credits-btn" onClick={() => openBuy()} className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90">
        Buy credits
      </button>
      <div data-testid="user-menu"><UserButton /></div>
    </div>);
}

function TokenBridge() {
    const { getToken } = useAuth();
    useEffect(() => { setTokenGetter(() => getToken()); }, [getToken]);
    return null;
}

export default function AppShell() {
    return (<CreditsProvider>
      <div className="flex min-h-screen">
        <aside className="w-56 shrink-0 border-r border-border bg-muted/60 px-4 py-6">
          <Link to="/" className="mb-8 block px-2 text-base font-semibold" data-testid="brand-link">
            Decision Trust
          </Link>
          <nav className="flex flex-col gap-1">
            {nav.map((n) => (<NavLink key={n.href} to={n.href} end={n.href === "/"} data-testid={`nav-${n.label.toLowerCase().replace(/[^a-z]+/g, "-")}`} className={({ isActive }) => `flex items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-white hover:text-foreground ${isActive ? "bg-white text-foreground" : "text-muted-foreground"}`}>
                {n.label}
                {n.paid && <Lock className="h-3 w-3 opacity-50" aria-label="Uses credits"/>}
              </NavLink>))}
          </nav>
          <p className="mt-10 px-2 text-xs text-muted-foreground">Workspace: Acme Consumer Goods (demo)</p>
          <p className="mt-2 px-2 text-[11px] text-muted-foreground"><Lock className="mr-1 inline h-3 w-3"/>uses credits</p>
        </aside>
        <main className="flex-1 px-8 py-6">
          <TopBar />
          <Outlet />
        </main>
      </div>
    </CreditsProvider>);
}

export function AuthedShell() {
    return (<>
      <TokenBridge />
      <AppShell />
    </>);
}
