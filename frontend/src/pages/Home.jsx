import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, GitCompareArrows, MessageSquareText, Wrench } from "lucide-react";
import { issueType } from "@/lib/format";
import { useApi } from "@/lib/api";
import { zoneColor, zoneLabel } from "@/lib/utils";
import { CostTag, useWorkspace } from "@/lib/workspace";
import { Button, Card, CardTitle, ErrorNote, Hint, ScoreRing } from "@/components/dt-ui";

const ZONE_HINT = {
    green: "Score 80 or more: approved definition, clear owner, documented data trail and up to date.",
    yellow: "Score 50 to 79: usable, but check the warnings before quoting it to leadership.",
    red: "Score under 50: missing an owner, a reliable definition or fresh data. Don't act on it yet.",
};

function EmptyWorkspace() {
    return (<Card data-testid="empty-workspace" className="space-y-3 border-primary/30 bg-primary/5">
      <p className="font-semibold">Your workspace is empty</p>
      <p className="text-sm text-muted-foreground">
        Add your first metrics from Power BI, Tableau or CSV, or explore the Acme demo first.
      </p>
      <div className="flex flex-wrap gap-2">
        <Link to="/ingest" data-testid="empty-workspace-ingest"><Button>Add data</Button></Link>
        <span className="self-center text-sm text-muted-foreground">or choose "Workspace: Acme (demo)" in the sidebar</span>
      </div>
    </Card>);
}

function Step({ n, icon: Icon, title, text }) {
    return (<div className="flex gap-3">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary"><Icon className="h-4 w-4"/></span>
      <div>
        <p className="text-sm font-semibold">{n}. {title}</p>
        <p className="text-xs text-muted-foreground">{text}</p>
      </div>
    </div>);
}

export default function Home() {
    const { data, error } = useApi("/index");
    const { ws } = useWorkspace();
    const navigate = useNavigate();
    const empty = ws === "mine" && data && data.metrics === 0;
    return (<div className="mx-auto max-w-5xl space-y-6">
      <header className="space-y-2" data-tour="home-headline">
        <h1 className="text-3xl font-semibold leading-tight">Two dashboards showing different numbers?</h1>
        <p className="text-lg text-muted-foreground">Find out why, and which one to trust.</p>
      </header>
      <ErrorNote error={error}/>

      <Card className="space-y-5 border-primary/30" data-testid="home-primary">
        <div className="flex flex-wrap gap-3">
          <Button data-testid="home-reconcile-link" className="h-11 px-6 text-base" onClick={() => navigate("/reconcile")}>
            <GitCompareArrows className="h-4 w-4"/> Compare two numbers <CostTag/>
          </Button>
          <Button data-testid="home-ask-link" variant="outline" className="h-11 px-6 text-base" onClick={() => navigate(ws === "demo" ? `/ask?q=${encodeURIComponent("Which revenue metric should I trust?")}` : "/ask")}>
            <MessageSquareText className="h-4 w-4"/> Ask a question
          </Button>
        </div>
        <div className="grid gap-4 border-t border-border pt-4 md:grid-cols-3" data-testid="home-steps">
          <Step n={1} icon={GitCompareArrows} title="Pick two numbers" text="Two tiles that should match but don't."/>
          <Step n={2} icon={ArrowRight} title="See every reason" text="Definitions, hidden filters, dates, sources, step by step."/>
          <Step n={3} icon={Wrench} title="Fix it for good" text="Agree one definition and record the decision."/>
        </div>
      </Card>

      {empty && <EmptyWorkspace/>}

      {data && !empty && (<section className="space-y-3" data-testid="home-health">
          <h2 className="text-lg font-semibold">Health of your numbers</h2>
          <div className="grid gap-4 md:grid-cols-3">
            <Card className="flex items-center gap-5">
              <ScoreRing score={data.index} zone={data.zone} size={112} hint="The Trust Index is the average trust score of all your metrics, weighted by how many people view them. Each metric is scored 0–100 on its definition, owner, data trail, consistent use and freshness."/>
              <div className="text-sm">
                <p className="font-semibold"><Hint text="How far leaders can trust the numbers they see, 0 to 100.">Trust Index</Hint></p>
                <p className="text-muted-foreground">How far leaders can trust the numbers they see, 0–100.</p>
                <p className="mt-1 text-xs text-muted-foreground">{data.metrics} metrics · {data.certified} approved</p>
              </div>
            </Card>
            <Card>
              <CardTitle>Metrics by trust level</CardTitle>
              <div className="mt-3 space-y-2">
                {["green", "yellow", "red"].map((z) => (<div key={z} className="flex items-center justify-between text-sm">
                    <Hint text={ZONE_HINT[z]} className="flex items-center gap-2 no-underline">
                      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: zoneColor[z] }}/>
                      <span className="underline decoration-dotted decoration-muted-foreground/60 underline-offset-4">{zoneLabel[z]}</span>
                    </Hint>
                    <span className="font-semibold">{data.zones[z]}</span>
                  </div>))}
              </div>
            </Card>
            <Card>
              <CardTitle>Issues to fix</CardTitle>
              <p className="mt-2 text-3xl font-semibold">{data.conflicts_open}</p>
              <p className="text-sm text-muted-foreground">
                <Hint text="Urgent issues affect executive dashboards or create data loops. Fix these first.">{data.conflicts_critical} urgent</Hint>
              </p>
            </Card>
          </div>

          <Card data-tour="home-issues">
            <div className="mb-2 flex items-center justify-between">
              <CardTitle>Top issues</CardTitle>
              <Link to="/conflicts" className="text-sm text-primary">See all issues</Link>
            </div>
            <ul className="divide-y divide-border">
              {data.top_conflicts.slice(0, 3).map((c) => (<li key={c.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span>
                    <span className="block text-sm font-medium">{c.title}</span>
                    <span className="text-xs text-muted-foreground">{issueType(c.code)} · affects {c.blast_radius} dashboard{c.blast_radius === 1 ? "" : "s"}</span>
                  </span>
                  <Link to="/conflicts" className="text-sm font-medium text-primary">Fix →</Link>
                </li>))}
              {!data.top_conflicts.length && <li className="py-2 text-sm text-muted-foreground">No issues left. Your numbers agree.</li>}
            </ul>
          </Card>
        </section>)}
    </div>);
}
