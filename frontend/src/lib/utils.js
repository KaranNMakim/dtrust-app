import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs) {
    return twMerge(clsx(inputs));
}
export const zoneColor = {
    green: "#15803d",
    yellow: "#b45309",
    red: "#b91c1c",
};
export const zoneLabel = {
    green: "Trusted",
    yellow: "Use with caution",
    red: "Untrusted",
};
export function zoneOf(score) {
    if (score == null)
        return null;
    return score >= 80 ? "green" : score >= 50 ? "yellow" : "red";
}
