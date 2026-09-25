import type { ReactNode } from "react";

interface FieldProps {
  label: ReactNode;
  htmlFor?: string;
  hint?: ReactNode;
  children: ReactNode;
}

/** Shared label / control / hint stack for form fields. */
export default function Field({ label, htmlFor, hint, children }: FieldProps) {
  return (
    <div className="form-field">
      {htmlFor ? (
        <label className="form-label" htmlFor={htmlFor}>
          {label}
        </label>
      ) : (
        <span className="form-label">{label}</span>
      )}
      {children}
      {hint && <div className="form-hint">{hint}</div>}
    </div>
  );
}
