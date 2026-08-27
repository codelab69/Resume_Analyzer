/**
 * Presentation helpers.
 *
 * Anything that turns a number or an enum into something a person reads lives
 * here, so the same score never gets two different colours in two components.
 */

import type { AtsBand, AtsStatus, Severity, Verdict } from "./types";

/**
 * Colour for a 0-100 score.
 *
 * Bands are wide on purpose. Narrow bands make the colour flicker between
 * green and amber on a one-point change, which reads as instability rather
 * than as feedback.
 */
export function scoreColor(score: number): string {
  if (score >= 75) return "var(--color-good)";
  if (score >= 50) return "var(--color-warn)";
  return "var(--color-bad)";
}

export const bandLabel: Record<AtsBand, string> = {
  excellent: "Excellent",
  good: "Good",
  needs_work: "Needs work",
  poor: "Needs a rewrite",
};

export const verdictLabel: Record<Verdict, string> = {
  strong: "Strong match",
  promising: "Promising",
  stretch: "A stretch",
  weak: "Weak match",
};

export const severityLabel: Record<Severity, string> = {
  critical: "Critical",
  important: "Important",
  nice_to_have: "Nice to have",
};

export const severityColor: Record<Severity, string> = {
  critical: "var(--color-bad)",
  important: "var(--color-warn)",
  nice_to_have: "var(--color-muted)",
};

export const statusColor: Record<AtsStatus, string> = {
  pass: "var(--color-good)",
  warn: "var(--color-warn)",
  fail: "var(--color-bad)",
};

export const statusLabel: Record<AtsStatus, string> = {
  pass: "Pass",
  warn: "Partial",
  fail: "Fix this",
};

/** Human category names. The API returns the internal key. */
export const categoryLabel: Record<string, string> = {
  language: "Languages",
  framework: "Frameworks",
  database: "Databases",
  cloud: "Cloud",
  devops: "DevOps",
  data: "Data",
  ml: "Machine learning",
  tool: "Tools",
  practice: "Practices",
  soft: "Working skills",
};

export function prettyCategory(key: string): string {
  return categoryLabel[key] ?? key;
}

/** "2 years 3 months", "7 months", "None recorded". */
export function formatExperience(months: number): string {
  if (months <= 0) return "None recorded";
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const parts: string[] = [];
  if (years) parts.push(`${years} year${years > 1 ? "s" : ""}`);
  if (rest) parts.push(`${rest} month${rest > 1 ? "s" : ""}`);
  return parts.join(" ");
}

/** "26 Aug 2026" - unambiguous, and short enough for a table cell. */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** "1.2 s" or "340 ms" - whichever reads better at that magnitude. */
export function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

export function percent(fraction: number): number {
  return Math.round(Math.max(0, Math.min(1, fraction)) * 100);
}
