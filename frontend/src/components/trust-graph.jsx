import cytoscape from "cytoscape";
import { useEffect, useRef } from "react";
import { zoneColor } from "@/lib/utils";
// Layered layout: sources → data products → metrics → dashboards, so trust flows left to right.
const LAYER = {
    SourceSystem: 0, DataProduct: 1, GlossaryTerm: 2, Team: 2, Metric: 3, Model: 4, Dashboard: 4, Report: 4, Recommendation: 5,
};
const SHAPE = {
    Metric: "round-rectangle", Dashboard: "rectangle", Report: "rectangle", DataProduct: "barrel",
    SourceSystem: "hexagon", Model: "diamond", Recommendation: "tag", Team: "ellipse", GlossaryTerm: "octagon",
};
export function TrustGraph({ nodes, edges, onSelect, focus, }) {
    const ref = useRef(null);
    const cy = useRef(null);
    useEffect(() => {
        if (!ref.current)
            return;
        const byLayer = {};
        const elements = [
            ...nodes.map((n) => {
                const layer = LAYER[n.label] ?? 2;
                const i = (byLayer[layer] = (byLayer[layer] ?? 0) + 1);
                return {
                    data: { ...n, color: n.zone ? zoneColor[n.zone] : "#9ca3af", shape: SHAPE[n.label] ?? "ellipse",
                        display: n.trust_score != null ? `${n.name} · ${Math.round(n.trust_score)}` : n.name },
                    position: { x: layer * 230, y: i * 70 },
                };
            }),
            ...edges.map((e, i) => ({ data: { id: `e${i}`, ...e, dashed: e.documented === false ? "dashed" : "solid" } })),
        ];
        cy.current?.destroy();
        cy.current = cytoscape({
            container: ref.current,
            elements,
            layout: { name: "preset", fit: true, padding: 30 },
            wheelSensitivity: 0.2,
            style: [
                {
                    selector: "node",
                    style: {
                        label: "data(display)", shape: "data(shape)", "background-color": "data(color)",
                        "background-opacity": 0.18, "border-color": "data(color)", "border-width": 1.5,
                        "font-size": 10, "text-valign": "center", "text-halign": "center", color: "#1f2937",
                        width: 150, height: 30, "text-wrap": "ellipsis", "text-max-width": "140px",
                    },
                },
                { selector: "node[?certified]", style: { "border-width": 3 } },
                { selector: "node:selected", style: { "border-width": 4, "border-color": "#1d4ed8" } },
                {
                    selector: "edge",
                    style: {
                        width: 1.2, "line-color": "#c4c0b6", "target-arrow-color": "#c4c0b6", "target-arrow-shape": "triangle",
                        "curve-style": "bezier", "arrow-scale": 0.7, "line-style": "data(dashed)",
                    },
                },
                { selector: "edge[type = 'DEPENDS_ON'][?documented]", style: { "line-color": "#a8a29e" } },
            ],
        });
        cy.current.on("tap", "node", (evt) => onSelect(evt.target.data()));
        cy.current.on("tap", (evt) => { if (evt.target === cy.current)
            onSelect(null); });
        if (focus)
            cy.current.$id(focus).select();
        return () => { cy.current?.destroy(); cy.current = null; };
    }, [nodes, edges, onSelect, focus]);
    return <div ref={ref} className="h-[640px] w-full rounded-lg border border-border bg-white"/>;
}
