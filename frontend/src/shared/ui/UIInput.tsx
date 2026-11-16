import { forwardRef, type InputHTMLAttributes } from "react";

export type UIInputProps = InputHTMLAttributes<HTMLInputElement>;

export const UIInput = forwardRef<HTMLInputElement, UIInputProps>(
  function UIInput({ className = "", ...props }, ref) {
    return (
      <input
        {...props}
        ref={ref}
        className={[
          "min-h-[44px] w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-sm text-slate-100",
          "placeholder:text-slate-500 outline-none focus:border-accent focus:ring-2 focus:ring-accent/30",
          className,
        ].join(" ")}
      />
    );
  },
);
