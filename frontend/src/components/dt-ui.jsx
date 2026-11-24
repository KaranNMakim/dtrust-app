// Minimal shadcn/ui-style primitives. Swap for `npx shadcn add card badge button input` if preferred.
import * as React from "react";
import { AlertCircle, Info } from "lucide-react";
import { cn, zoneColor, zoneLabel } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { APPROVAL, plainError } from "@/lib/format";

// Explains where a number or label comes from. Dotted underline signals there is more to read.
export function Hint({ text, children, className, testId }) {
    return (<Tooltip delayDuration={150}>
      <TooltipTrigger asChild>
        <span data-testid={testId} tabIndex={0} className={cn("cursor-help underline decoration-dotted decoration-muted-foreground/60 underline-offset-4", className)}>{children}</span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs bg-foreground text-white leading-relaxed">{text}</TooltipContent>
    </Tooltip>);
}

// Neutral system message: blue for info and success, red only for real errors. Always icon + text.
export function Notice({ tone = "info", children, className, ...p }) {
    const Icon = tone === "error" ? AlertCircle : Info;
    const styles = tone === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-blue-200 bg-blue-50 text-blue-900";
    return (<div role={tone === "error" ? "alert" : "status"} className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-sm", styles, className)} {...p}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0"/><div>{children}</div>
    </div>);
}
export function Card({ className, ...p }) {
    return <div className={cn("rounded-lg border border-border bg-white p-5 shadow-sm", className)} {...p}/>;
}
export function CardTitle({ className, ...p }) {
    return <h2 className={cn("text-sm font-semibold text-muted-foreground", className)} {...p}/>;
}
export function Button({ className, variant = "default", ...p }) {
    const styles = {
        default: "bg-primary text-primary-foreground hover:opacity-90",
        outline: "border border-border bg-white hover:bg-muted",
        ghost: "hover:bg-muted",
        danger: "border border-red-200 bg-red-50 text-red-800 hover:bg-red-100",
    }[variant];
    return (<button className={cn("inline-flex h-9 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition disabled:opacity-50", styles, className)} {...p}/>);
}
export function Input({ className, ...p }) {
    return (<input className={cn("h-11 w-full rounded-md border border-border bg-white px-4 text-sm outline-none focus:ring-2 focus:ring-primary/40", className)} {...p}/>);
}
export function Badge({ className, ...p }) {
    return (<span className={cn("inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold", className)} {...p}/>);
}
export function ScorePill({ score, zone }) {
    return (<span className="inline-flex min-w-[2.75rem] justify-center rounded-full border px-2 py-0.5 text-xs font-semibold" style={{ color: zoneColor[zone], borderColor: zoneColor[zone], background: `${zoneColor[zone]}14` }} title={zoneLabel[zone]}>
      {Math.round(score)}
    </span>);
}
export function ScoreRing({ score, zone, size = 112, hint }) {
    const r = size / 2 - 8;
    const c = 2 * Math.PI * r;
    return (<div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} role="img" aria-label={`Trust score ${Math.round(score)}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e7e5e0" strokeWidth={8}/>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={zoneColor[zone]} strokeWidth={8} strokeDasharray={`${(score / 100) * c} ${c}`} strokeLinecap="round" transform={`rotate(-90 ${size / 2} ${size / 2})`}/>
        <text x="50%" y="54%" textAnchor="middle" fontSize={size / 3.5} fontWeight={600} fill="#1f2937">
          {Math.round(score)}
        </text>
      </svg>
      {hint ? <Hint text={hint} className="text-xs text-muted-foreground" testId="score-ring-hint">{zoneLabel[zone]} · how is this scored?</Hint>
            : <span className="text-xs text-muted-foreground">{zoneLabel[zone]}</span>}
    </div>);
}
export function CertBadge({ certification }) {
    if (certification === "certified")
        return <Badge className="border-blue-300 bg-blue-50 text-blue-800">Official definition</Badge>;
    if (certification === "deprecated" || certification === "pending")
        return <Badge className="border-gray-300 bg-gray-50 text-gray-600">{APPROVAL[certification]}</Badge>;
    return null;
}
export function SeverityBadge({ severity }) {
    return severity === "critical" ? (<Badge className="border-red-300 bg-red-50 text-red-800">Critical</Badge>) : (<Badge className="border-amber-300 bg-amber-50 text-amber-800">Warning</Badge>);
}
export function ErrorNote({ error }) {
    if (!error)
        return null;
    return <Notice tone="error" data-testid="error-note">{plainError(error)}</Notice>;
}
export function ComponentBars({ components }) {
    return (<div className="space-y-4">
      {components.map((c) => {
            const z = c.raw >= 80 ? "green" : c.raw >= 50 ? "yellow" : "red";
            return (<div key={c.key}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span className="font-medium">
                {c.label}{" "}
                <Hint text={`This check counts for ${Math.round(c.weight * 100)}% of the overall trust score. The weights are set on the Calibration page.`} className="text-muted-foreground">
                  · counts {Math.round(c.weight * 100)}%
                </Hint>
              </span>
              <Hint text={`Scored 0 to 100 from the evidence listed below. 80+ is trusted, 50 to 79 needs caution, under 50 should not be trusted.`} className="font-semibold">
                <span style={{ color: zoneColor[z] }}>{Math.round(c.raw)}</span>
              </Hint>
            </div>
            <div className="h-2 w-full rounded-full bg-muted">
              <div className="h-2 rounded-full" style={{ width: `${c.raw}%`, background: zoneColor[z] }}/>
            </div>
            <ul className="mt-1 text-xs text-muted-foreground">
              {c.evidence.map((e) => (<li key={e}>• {e}</li>))}
            </ul>
            {c.fix && <p className="mt-1 text-xs font-medium text-primary">Fix: {c.fix}</p>}
          </div>);
        })}
    </div>);
}
