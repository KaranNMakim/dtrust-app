import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

// Small accessible dropdown: closes on outside click or Escape.
export function Dropdown({ trigger, children, align = "right", className, testId }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);
    useEffect(() => {
        if (!open)
            return;
        const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
        document.addEventListener("mousedown", onDown);
        document.addEventListener("keydown", onKey);
        return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
    }, [open]);
    return (<div ref={ref} className="relative inline-block">
      {trigger({ open, toggle: () => setOpen((o) => !o) })}
      {open && (<div data-testid={testId} role="menu" className={cn("absolute z-40 mt-2 min-w-[16rem] rounded-lg border border-border bg-white p-1.5 shadow-lg", align === "right" ? "right-0" : "left-0", className)}>
          {typeof children === "function" ? children({ close: () => setOpen(false) }) : children}
        </div>)}
    </div>);
}

export function MenuItem({ icon: Icon, label, description, onClick, testId, disabled }) {
    return (<button role="menuitem" data-testid={testId} disabled={disabled} onClick={onClick} className="flex w-full items-start gap-3 rounded-md px-3 py-2 text-left transition-colors hover:bg-muted disabled:opacity-50">
      {Icon && <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"/>}
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {description && <span className="block text-xs text-muted-foreground">{description}</span>}
      </span>
    </button>);
}
