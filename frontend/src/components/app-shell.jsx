import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { getWorkspace, storeWorkspace, useWorkspace, WorkspaceContext } from "@/lib/workspace";
import { UserButton, useAuth } from "@clerk/react";
import { Building2, ChevronDown, Coins, CreditCard, FolderLock, Lock, ReceiptText, Sparkles } from "lucide-react";
import { setTokenGetter } from "@/lib/api";
import { CreditsProvider, useCredits } from "@/components/credits";
import { useWaitlist } from "@/components/waitlist-dialog";
import { Dropdown, MenuItem } from "@/components/dropdown";
import { Hint } from "@/components/dt-ui";
import { TooltipProvider } from "@/components/ui/tooltip";
import { TourHost, replayTour } from "@/components/tour";

const UNLOCK = {
    ask: "Get a plain-English answer about your own metrics: which number to trust, why, and who owns it.",
    compare: "See exactly why two of your own numbers differ, broken down step by step.",
    add: "Bring your own Power BI, Tableau or spreadsheet data into a workspace that is saved for you.",
};

const NAV = [
    { group: "Investigate", items: [
            { href: "/ask", label: "Ask", testId: "nav-ask", paid: UNLOCK.ask },
            { href: "/reconcile", label: "Compare two numbers", testId: "nav-compare", paid: UNLOCK.compare },
        ] },
    { group: "Fix", items: [{ href: "/conflicts", label: "Issues to fix", testId: "nav-issues" }] },
    { group: "Explore", items: [
            { href: "/metrics", label: "Metrics", testId: "nav-metrics" },
            { href: "/graph", label: "Trust Graph", testId: "nav-trust-graph" },
        ] },
    { group: "Admin", muted: true, items: [
            { href: "/recommendations", label: "Recommendations", testId: "nav-recommendations" },
            { href: "/calibration", label: "Calibration", testId: "nav-calibration" },
            { href: "/ingest", label: "Add data", testId: "nav-add-data", paid: UNLOCK.add },
        ] },
    { group: "Account", items: [{ href: "/billing", label: "Plan & billing", testId: "nav-plan-billing" }] },
];

function CreditsMenu() {
    const { credits, openBuy, openPremium } = useCredits();
    const joined = useWaitlist();
    const navigate = useNavigate();
    return (<Dropdown testId="credits-menu" trigger={({ toggle }) => (<button data-testid="credit-balance" onClick={toggle} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-white px-3 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted">
          <Coins className="h-3.5 w-3.5 text-muted-foreground"/>
          {credits ?? "…"} credit{credits === 1 ? "" : "s"}
          <ChevronDown className="h-3 w-3 text-muted-foreground"/>
        </button>)}>
      {({ close }) => (<>
          <div className="border-b border-border px-3 pb-2 pt-1">
            <p className="text-sm font-semibold" data-testid="credits-menu-balance">{credits ?? "…"} credits left</p>
            <p className="text-xs text-muted-foreground">Each Ask, comparison, upload or publish in My workspace uses 1 credit. The Acme demo is free.</p>
          </div>
          <MenuItem icon={CreditCard} testId="buy-credits-btn" label="Buy credits" description="Credit packs from ₹850, paid once." onClick={() => { close(); openBuy(); }}/>
          <MenuItem icon={Sparkles} testId="join-waitlist-btn" label={joined ? "On the premium waitlist" : "Join premium waitlist"} description="Team workspaces, live connectors and volume pricing." onClick={() => { close(); openPremium(); }}/>
          <MenuItem icon={ReceiptText} testId="menu-plan-billing" label="Plan & billing" description="Purchases and credit history." onClick={() => { close(); navigate("/billing"); }}/>
        </>)}
    </Dropdown>);
}

function TopBar() {
    return (<div className="mb-6 flex items-center justify-end gap-3" data-testid="top-bar">
      <CreditsMenu />
      <div data-testid="user-menu"><UserButton /></div>
    </div>);
}

function TokenBridge() {
    const { getToken } = useAuth();
    useEffect(() => { setTokenGetter(() => getToken()); }, [getToken]);
    return null;
}

const WORKSPACES = [
    { id: "demo", label: "Workspace: Acme (demo)", note: "Sample company. Everything is free.", icon: Building2 },
    { id: "mine", label: "Workspace: Mine", note: "Your own data, saved. Uses credits.", icon: FolderLock },
];

function WorkspaceSwitcher() {
    const { ws, setWs } = useWorkspace();
    return (<div className="mt-8 space-y-1 border-t border-border pt-5" data-testid="workspace-switcher">
      {WORKSPACES.map((w) => (<button key={w.id} data-testid={`workspace-${w.id}`} onClick={() => setWs(w.id)} className={`flex w-full items-start gap-2 rounded-md border px-2 py-2 text-left transition-colors ${ws === w.id ? "border-primary/40 bg-white" : "border-transparent hover:bg-white/70"}`}>
          <w.icon className={`mt-0.5 h-4 w-4 shrink-0 ${ws === w.id ? "text-primary" : "text-muted-foreground"}`}/>
          <span>
            <span className="block text-sm font-medium">{w.label}</span>
            <span className="block text-[11px] text-muted-foreground">{w.note}</span>
          </span>
        </button>))}
    </div>);
}

function NavItem({ item, muted }) {
    const { ws } = useWorkspace();
    return (<NavLink to={item.href} data-testid={item.testId} className={({ isActive }) => `flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-white hover:text-foreground ${muted ? "text-[13px]" : "text-sm"} ${isActive ? "bg-white text-foreground" : "text-muted-foreground"}`}>
      {item.label}
      {item.paid && (<Hint testId={`${item.testId}-lock`} className="no-underline" text={`${item.paid} Uses 1 credit each time in your own workspace${ws === "demo" ? "; free here in the Acme demo" : ""}.`}>
          <Lock className="h-3 w-3 opacity-50" aria-label="Uses credits in your own workspace"/>
        </Hint>)}
    </NavLink>);
}

function Sidebar() {
    const { ws, setWs } = useWorkspace();
    return (<aside className="w-60 shrink-0 border-r border-border bg-muted/60 px-4 py-6">
      <Link to="/" className="mb-8 block px-2 text-base font-semibold" data-testid="brand-link" title="Overview">
        Decision Trust
      </Link>
      <nav className="space-y-5">
        {NAV.map((g) => (<div key={g.group} className={g.muted ? "opacity-80" : ""}>
            <p className={`px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide ${g.muted ? "text-muted-foreground/70" : "text-muted-foreground"}`}>{g.group}</p>
            <div className="flex flex-col gap-0.5">{g.items.map((i) => <NavItem key={i.href} item={i} muted={g.muted}/>)}</div>
          </div>))}
      </nav>
      <WorkspaceSwitcher />
      <button data-testid="replay-tour" onClick={() => { replayTour(); if (ws !== "demo") setWs("demo"); }} className="mt-4 px-2 text-xs text-muted-foreground hover:text-foreground hover:underline">
        Replay tour (Acme demo)
      </button>
    </aside>);
}

export default function AppShell() {
    const navigate = useNavigate();
    const [ws, setWsState] = useState(getWorkspace());
    const setWs = (next) => {
        if (next === ws)
            return;
        storeWorkspace(next);
        setWsState(next);
        navigate("/");
    };
    return (<WorkspaceContext.Provider value={{ ws, setWs }}>
    <TooltipProvider>
    <CreditsProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 px-8 py-6">
          <TopBar />
          <Outlet key={ws}/>
          <TourHost />
        </main>
      </div>
    </CreditsProvider>
    </TooltipProvider>
    </WorkspaceContext.Provider>);
}

export function AuthedShell() {
    return (<>
      <TokenBridge />
      <AppShell />
    </>);
}
