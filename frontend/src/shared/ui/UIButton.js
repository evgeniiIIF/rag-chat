import { jsx as _jsx } from "react/jsx-runtime";
export function UIButton({ children, className = "", ...rest }) {
    return (_jsx("button", { ...rest, className: [
            "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium",
            "transition-colors focus:outline-none focus:ring-2 focus:ring-accent/40",
            rest.disabled
                ? "bg-slate-200 text-slate-500 cursor-not-allowed dark:bg-slate-800 dark:text-slate-500"
                : "bg-accent text-white hover:bg-accent-hover",
            className,
        ].join(" "), children: children }));
}
