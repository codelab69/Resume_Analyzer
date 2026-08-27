/**
 * Small shared pieces used across screens.
 *
 * Kept in one file because each is under thirty lines and splitting them into
 * ten files makes them harder to find, not easier. Anything that grows past
 * this size should move out into its own module.
 */

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";

// ---------------------------------------------------------------------------

export function Pill({
  children,
  color,
  title,
}: {
  children: ReactNode;
  color?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1.5 border px-2 py-0.5 font-mono text-[11px]"
      style={color ? { borderColor: color, color } : undefined}
    >
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------

export function Spinner({ label = "Loading" }: { label?: string }) {
  const reduceMotion = useReducedMotion();
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-muted" role="status">
      <motion.span
        aria-hidden
        className="block h-3.5 w-3.5 border-2 border-rule-strong border-t-marker"
        style={{ borderRadius: "50%" }}
        animate={reduceMotion ? undefined : { rotate: 360 }}
        transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }}
      />
      {label}
    </div>
  );
}

// ---------------------------------------------------------------------------

/**
 * An error the user can act on.
 *
 * `message` comes straight from the API - the backend writes error text for
 * people, so replacing it with a generic string here would throw away the
 * only useful part.
 */
export function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="card border-l-2 px-4 py-3"
      style={{ borderLeftColor: "var(--color-bad)" }}
    >
      <p className="label mb-1" style={{ color: "var(--color-bad)" }}>
        Something needs fixing
      </p>
      <p className="text-sm">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 border border-rule-strong px-3 py-1 text-xs font-medium transition-colors hover:bg-surface-2"
        >
          Try again
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-14 text-center">
      <h3 className="font-display text-lg font-bold">{title}</h3>
      <p className="max-w-[46ch] text-sm text-muted">{body}</p>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------------------

/** Section heading with an optional right-hand slot. */
export function SectionHeader({
  eyebrow,
  title,
  aside,
}: {
  eyebrow?: string;
  title: string;
  aside?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-rule pb-2">
      <div>
        {eyebrow && <p className="label mb-1">{eyebrow}</p>}
        <h2 className="font-display text-xl font-bold">{title}</h2>
      </div>
      {aside}
    </div>
  );
}

// ---------------------------------------------------------------------------

/** A labelled number. Used for the dashboard tiles and report facts. */
export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="card px-4 py-3">
      <p className="label mb-1.5">{label}</p>
      <p className="font-display text-2xl font-bold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------

/** A non-blocking notice. Used for degraded-mode and parser warnings. */
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="card border-l-2 border-l-marker px-4 py-2.5 text-[13px] text-ink-soft">
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------

export function PrimaryButton({
  children,
  disabled,
  onClick,
  type = "button",
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className="bg-ink px-5 py-2.5 text-sm font-semibold text-paper transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}
