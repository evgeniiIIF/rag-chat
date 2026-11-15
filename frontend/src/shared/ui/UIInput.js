import { jsx as _jsx } from "react/jsx-runtime";
import { forwardRef } from "react";
export const UIInput = forwardRef(function UIInput({ className = "", ...props }, ref) {
    return (_jsx("input", { ...props, ref: ref, className: [
            "flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm",
            "placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-accent/40",
            "dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500",
            "disabled:opacity-60",
            className,
        ].join(" ") }));
});
