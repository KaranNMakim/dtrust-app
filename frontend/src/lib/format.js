// Single place that turns internal codes and ids into plain business language.

export const ISSUE_TYPE = {
    C1: "Same name, different formulas",
    C2: "Calculated differently on some dashboards",
    C3: "Nobody owns this metric",
    C4: "Data loops back on itself",
    C5: "Doesn't match the official definition",
};

export const APPROVAL = {
    certified: "Approved",
    pending: "Awaiting approval",
    deprecated: "Retired",
    none: "Not approved",
};

export function issueType(code) {
    return ISSUE_TYPE[code] ?? "Data issue";
}

const looksLikeId = (s) => /^[A-Za-z0-9._:-]+$/.test(s) && /[_:]/.test(s);

// Turn any API error text into something a business reader can act on.
export function plainError(message) {
    if (!message)
        return message;
    const m = String(message).trim().replace(/^'|'$/g, "");
    if (looksLikeId(m))
        return "We couldn't find that item in this workspace. It may have been removed or renamed.";
    if (/failed to fetch|networkerror/i.test(m))
        return "We couldn't reach Decision Trust. Check your connection and try again.";
    if (/not signed in|invalid or expired session/i.test(m))
        return "Your session has ended. Please sign in again.";
    return m;
}

// Replace any ids the backend left in a sentence with names we know about.
export function withNames(text, names) {
    if (!text || !names)
        return text;
    return String(text).replace(/\b[a-z]{1,4}_[a-z0-9_]+\b/g, (id) => names[id] ?? id);
}
