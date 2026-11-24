import { Suspense, useEffect, useMemo, useState } from "react";
import { CostTag, useWorkspace } from "@/lib/workspace";
import { useSearchParams } from "react-router-dom";
import { api, useApi } from "@/lib/api";
import { Button, Card, ErrorNote } from "@/components/dt-ui";
import { ReconcileView } from "@/components/reconcile-view";
const PRESETS = [
    { label: "Sales QBR vs Board Pack (revenue)", a: "m_rev_sales", da: "d_sales_qbr", b: "m_net_rev_fin", db: "d_board" },
    { label: "CEO Pulse: bookings vs revenue", a: "m_rev_sales", da: "d_ceo", b: "m_net_rev_fin", db: "d_ceo" },
    { label: "eCom net sales vs Finance revenue", a: "m_net_sales_ecom", da: "", b: "m_net_rev_fin", db: "" },
    { label: "OTIF: Customer Service vs Supply Chain", a: "m_otif_cs", da: "", b: "m_otif_sc", db: "" },
    { label: "Gross margin: Supply vs Finance", a: "m_gm_supply", da: "", b: "m_gm_fin", db: "" },
];
function Picker({ label, metric, dash, metrics, dashes, onMetric, onDash }) {
    const showing = dashes.filter((d) => d.metric_ids.includes(metric));
    return (<div className="flex-1 space-y-2">
      <p className="text-xs font-semibold text-muted-foreground">{label}</p>
      <select className="h-10 w-full rounded-md border border-border bg-white px-3 text-sm" value={metric} onChange={(e) => { onMetric(e.target.value); onDash(""); }}>
        {metrics.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
      </select>
      <select className="h-9 w-full rounded-md border border-border bg-white px-3 text-xs" value={dash} onChange={(e) => onDash(e.target.value)}>
        <option value="">As defined (any dashboard)</option>
        {showing.map((d) => <option key={d.id} value={d.id}>As shown on {d.name}</option>)}
      </select>
    </div>);
}
function ReconcileInner() {
    const [params] = useSearchParams();
    const metrics = useApi("/metrics");
    const dashes = useApi("/dashboards");
    const [a, setA] = useState(params.get("a") ?? PRESETS[0].a);
    const fromLink = params.has("a");
    const [da, setDa] = useState(params.get("dashboard_a") ?? (fromLink ? "" : PRESETS[0].da));
    const [b, setB] = useState(params.get("b") ?? (params.get("a") === PRESETS[0].b ? PRESETS[0].a : PRESETS[0].b));
    const [db, setDb] = useState(params.get("dashboard_b") ?? (fromLink ? "" : PRESETS[0].db));
    const [rec, setRec] = useState(null);
    const [err, setErr] = useState(null);
    const { ws } = useWorkspace();
    const sorted = useMemo(() => [...(metrics.data ?? [])].sort((x, y) => x.name.localeCompare(y.name)), [metrics.data]);
    useEffect(() => {
        if (!sorted.length)
            return;
        const known = new Set((dashes.data ?? []).map((d) => d.id));
        if (!known.has(da)) setDa("");
        if (!known.has(db)) setDb("");
        if (sorted.some((m) => m.id === a))
            return;
        setA(sorted[0].id);
        setB((sorted[1] ?? sorted[0]).id);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [sorted, dashes.data]);
    // In the free demo, run straight away (from a link, the tour, or the first preset). Never auto-spend credits.
    const [auto, setAuto] = useState(false);
    useEffect(() => {
        if (auto || ws !== "demo" || !sorted.length)
            return;
        setAuto(true);
        run(a, da, b, db);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [sorted, ws]);
    async function run(pa = a, pda = da, pb = b, pdb = db) {
        setErr(null);
        const q = new URLSearchParams({ a: pa, b: pb, ...(pda ? { dashboard_a: pda } : {}), ...(pdb ? { dashboard_b: pdb } : {}) });
        try {
            setRec(await api(`/reconcile?${q}`, undefined, { paid: true }));
        }
        catch (e) {
            setErr(e.message);
        }
    }
    
    return (<div className="mx-auto max-w-5xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Compare two numbers</h1>
        <p className="text-sm text-muted-foreground">Pick two numbers that should match. You'll see every reason they differ and how to get from one to the other, step by step.</p>
      </header>
      <div className="flex flex-wrap items-center gap-2">
        {ws === "demo" && <span className="text-xs text-muted-foreground">Try:</span>}
        {ws === "demo" && PRESETS.map((p) => (<button key={p.label} data-testid="reconcile-preset" className="rounded-full border border-border bg-white px-3 py-1 text-xs hover:bg-muted" onClick={() => { setA(p.a); setDa(p.da); setB(p.b); setDb(p.db); run(p.a, p.da, p.b, p.db); }}>
            {p.label}
          </button>))}
      </div>
      <Card className="flex flex-col gap-4 md:flex-row md:items-end">
        <Picker label="Number A" metric={a} dash={da} metrics={sorted} dashes={dashes.data ?? []} onMetric={setA} onDash={setDa}/>
        <Picker label="Number B" metric={b} dash={db} metrics={sorted} dashes={dashes.data ?? []} onMetric={setB} onDash={setDb}/>
        <Button data-testid="reconcile-submit" className="h-10 whitespace-nowrap" onClick={() => run()}>Compare <CostTag/></Button>
      </Card>
      <ErrorNote error={err ?? metrics.error}/>
      {rec && <ReconcileView rec={rec}/>}
    </div>);
}
export default function ReconcilePage() {
    return <Suspense><ReconcileInner /></Suspense>;
}
