import { useState } from "react";
import { ChevronDown, Code2, Download, FileCode, MoreHorizontal, Send, Archive, UserPlus } from "lucide-react";
import { api } from "@/lib/api";
import { CostTag, useWorkspace } from "@/lib/workspace";
import { Button, Card, CardTitle, Notice } from "@/components/dt-ui";
import { Dropdown, MenuItem } from "@/components/dropdown";
import { plainError } from "@/lib/format";

const TARGETS = { dbt: "dbt", databricks: "Databricks" };

function downloadFile(filename, content) {
    const a = document.createElement("a");
    a.href = `data:text/plain;charset=utf-8,${encodeURIComponent(content)}`;
    a.download = filename;
    a.click();
}

export function PublishCard({ metricId, onClose }) {
    const { ws } = useWorkspace();
    const [files, setFiles] = useState({});
    const [preview, setPreview] = useState(null);
    const [busy, setBusy] = useState(null);
    const [error, setError] = useState(null);
    async function get(format) {
        if (files[format])
            return files[format];
        const out = await api(`/metrics/${metricId}/export?format=${format}`, undefined, { paid: true });
        setFiles((f) => ({ ...f, [format]: out }));
        return out;
    }
    async function run(format, then) {
        setBusy(format + then);
        setError(null);
        try {
            const out = await get(format);
            if (then === "download")
                downloadFile(out.filename, out.content);
            else
                setPreview(format);
        }
        catch (e) {
            setError(plainError(e.message));
        }
        finally {
            setBusy(null);
        }
    }
    const shown = preview && files[preview];
    return (<Card data-testid="publish-card" className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <CardTitle className="text-base text-foreground">Publish this definition <CostTag/></CardTitle>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Hand this definition to your data engineer – it creates the metric in dbt or Databricks so every tool uses the same formula.
          </p>
          {ws === "mine" && <p className="mt-1 text-xs text-muted-foreground">Uses 1 credit per format, the first time you download or preview it.</p>}
        </div>
        {onClose && <Button variant="ghost" className="h-8" data-testid="publish-close" onClick={onClose}>Close</Button>}
      </div>
      <div className="flex flex-wrap gap-2">
        {Object.entries(TARGETS).map(([k, label]) => (<Button key={k} variant="outline" data-testid={`download-${k}`} disabled={!!busy} onClick={() => run(k, "download")}>
            <Download className="h-4 w-4"/>Download for {label}
          </Button>))}
        <Dropdown testId="preview-code-menu" align="left" trigger={({ toggle }) => (<Button variant="ghost" data-testid="preview-code" disabled={!!busy} onClick={toggle}>
              <Code2 className="h-4 w-4"/>Preview code<ChevronDown className="h-3.5 w-3.5"/>
            </Button>)}>
          {({ close }) => Object.entries(TARGETS).map(([k, label]) => (<MenuItem key={k} icon={FileCode} label={`${label} version`} testId={`preview-${k}`} onClick={() => { close(); run(k, "preview"); }}/>))}
        </Dropdown>
      </div>
      {error && <Notice tone="error" data-testid="publish-error">{error}</Notice>}
      {shown && (<details open data-testid="code-panel" className="rounded-md border border-border">
          <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium">For your data engineer · {TARGETS[preview]} file</summary>
          <div className="space-y-2 border-t border-border p-3">
            <div className="flex gap-2">
              <Button variant="outline" className="h-8" onClick={() => navigator.clipboard.writeText(shown.content)}>Copy</Button>
              <Button variant="outline" className="h-8" onClick={() => downloadFile(shown.filename, shown.content)}>Download</Button>
            </div>
            <pre className="max-h-96 overflow-auto rounded bg-muted p-3 text-xs">{shown.content}</pre>
          </div>
        </details>)}
    </Card>);
}

export function PrimaryAction({ metric, score, onApprove, onAssign, busy }) {
    if (metric.certification !== "certified" && metric.certification !== "deprecated" && score >= 80)
        return (<Button data-testid="primary-approve" disabled={busy} onClick={onApprove}>
          <Send className="h-4 w-4"/>Approve as official definition
        </Button>);
    if (!metric.owner_email)
        return (<Button data-testid="primary-assign-owner" disabled={busy} onClick={onAssign}>
          <UserPlus className="h-4 w-4"/>Assign an owner
        </Button>);
    return null;
}

export function MoreActions({ metric, onRetire, onPublish, onChangeOwner }) {
    return (<Dropdown testId="more-actions-menu" trigger={({ toggle }) => (<Button variant="outline" data-testid="more-actions" onClick={toggle}>
          <MoreHorizontal className="h-4 w-4"/>More actions
        </Button>)}>
      {({ close }) => (<>
          <MenuItem icon={FileCode} testId="action-publish" label="Publish to dbt or Databricks" description="Give your data engineer this definition so every tool uses the same formula." onClick={() => { close(); onPublish(); }}/>
          {metric.owner_email && <MenuItem icon={UserPlus} testId="action-change-owner" label="Change owner" description="Hand responsibility for this metric to someone else." onClick={() => { close(); onChangeOwner(); }}/>}
          {metric.certification !== "deprecated" && <MenuItem icon={Archive} testId="action-retire" label="Retire this definition" description="Stop treating it as a valid definition. It stays visible for history." onClick={() => { close(); onRetire(); }}/>}
        </>)}
    </Dropdown>);
}
