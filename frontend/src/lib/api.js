import { useCallback, useEffect, useState } from "react";
import { getWorkspace } from "@/lib/workspace";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api/v1`;
export const BILLING = `${BACKEND_URL}/api/billing`;

let tokenGetter = async () => null;
export function setTokenGetter(fn) {
    tokenGetter = fn;
}

export async function authHeaders() {
    const token = await tokenGetter();
    return { "X-Workspace": getWorkspace(), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

export function notifyCreditsChanged() {
    window.dispatchEvent(new Event("dt:credits-changed"));
}

export async function handleResponse(res, paid) {
    if (!res.ok) {
        let detail = res.statusText;
        try {
            const body = await res.json();
            detail = body.detail ?? body.title ?? detail;
        }
        catch { }
        if (res.status === 402)
            window.dispatchEvent(new Event("dt:out-of-credits"));
        const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
        err.status = res.status;
        throw err;
    }
    if (paid)
        notifyCreditsChanged();
    return res.json();
}

export async function api(path, init, { base = API, paid = false } = {}) {
    const res = await fetch(`${base}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", ...(await authHeaders()), ...(init?.headers ?? {}) },
        cache: "no-store",
    });
    return handleResponse(res, paid);
}

export function useApi(path, base = API) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(false);
    const reload = useCallback(async () => {
        if (!path)
            return;
        setLoading(true);
        try {
            setData(await api(path, undefined, { base }));
            setError(null);
        }
        catch (e) {
            setError(e.message);
        }
        finally {
            setLoading(false);
        }
    }, [path, base]);
    useEffect(() => {
        reload();
    }, [reload]);
    return { data, error, loading, reload };
}
