import { createContext, useContext } from "react";

const KEY = "dt-workspace";

export function getWorkspace() {
    return localStorage.getItem(KEY) === "mine" ? "mine" : "demo";
}

export function storeWorkspace(ws) {
    localStorage.setItem(KEY, ws);
}

export const WorkspaceContext = createContext({ ws: "demo", setWs: () => { } });

export function useWorkspace() {
    return useContext(WorkspaceContext);
}

export function CostTag() {
    const { ws } = useWorkspace();
    return <span className="text-xs font-normal opacity-80">· {ws === "mine" ? "1 credit" : "free in demo"}</span>;
}
