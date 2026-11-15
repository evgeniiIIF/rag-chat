import { forwardRef, type InputHTMLAttributes } from "react";

export type UIInputProps = InputHTMLAttributes<HTMLInputElement>;

export const UIInput = forwardRef<HTMLInputElement, UIInputProps>(
  function UIInput(props, ref) {
    return (
      <input
        {...props}
        ref={ref}
        style={{
          padding: "8px 12px",
          borderRadius: 8,
          border: "1px solid #333",
          minWidth: 320,
        }}
      />
    );
  },
);
