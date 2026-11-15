import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface UIButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
}

export function UIButton({ children, ...rest }: UIButtonProps): JSX.Element {
  return (
    <button
      {...rest}
      style={{
        padding: "8px 14px",
        borderRadius: 8,
        border: "1px solid #333",
        background: rest.disabled ? "#ddd" : "#1e293b",
        color: rest.disabled ? "#666" : "white",
        cursor: rest.disabled ? "not-allowed" : "pointer",
      }}
    >
      {children}
    </button>
  );
}
