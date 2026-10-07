import type { ReactNode } from "react";

interface StatusMessageProps {
  variant: "loading" | "error";
  title: string;
  children?: ReactNode;
}

/** One place for the loading banner and the error banner. */
export function StatusMessage({ variant, title, children }: StatusMessageProps) {
  const isError = variant === "error";
  return (
    <div
      className={`status status--${variant}`}
      role={isError ? "alert" : "status"}
      aria-live={isError ? "assertive" : "polite"}
    >
      {variant === "loading" && <span className="spinner" aria-hidden="true" />}
      <div>
        <p className="status__title">{title}</p>
        {children && <p className="status__text">{children}</p>}
      </div>
    </div>
  );
}
