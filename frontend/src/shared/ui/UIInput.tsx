import { forwardRef, type InputHTMLAttributes } from "react";

export type UIInputProps = InputHTMLAttributes<HTMLInputElement>;

export const UIInput = forwardRef<HTMLInputElement, UIInputProps>(
  function UIInput({ className = "", style, ...props }, ref) {
    return (
      <input
        {...props}
        ref={ref}
        style={{
          backgroundColor: "#1e293b",
          color: "#f1f5f9",
          border: "1px solid #334155",
          borderRadius: "12px",
          padding: "16px",
          width: "100%",
          fontSize: "14px",
          outline: "none",
          ...style,
        }}
        className={className}
      />
    );
  },
);
