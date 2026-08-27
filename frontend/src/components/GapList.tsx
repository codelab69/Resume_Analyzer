/**
 * Skills a job wants that the resume does not show, ranked and bucketed.
 *
 * Grouped by severity rather than listed flat, because "you are missing 14
 * skills" is discouraging and useless, while "three of these are critical, the
 * rest are optional" is a plan. Severity comes from how central each skill is
 * to that specific posting, not from any global notion of importance.
 */

import { motion, useReducedMotion } from "motion/react";

import { severityColor, severityLabel } from "@/lib/format";
import type { Severity, SkillGap } from "@/lib/types";

interface Props {
  gaps: SkillGap[];
}

const ORDER: Severity[] = ["critical", "important", "nice_to_have"];

const GUIDANCE: Record<Severity, string> = {
  critical:
    "This posting leans on these. Without them the application is unlikely to progress.",
  important: "Worth naming explicitly if you have used them, even in coursework.",
  nice_to_have: "Mentioned in passing. Do not rewrite your resume for these.",
};

export function GapList({ gaps }: Props) {
  const reduceMotion = useReducedMotion();

  if (gaps.length === 0) {
    return (
      <p className="border-l-2 border-good bg-surface-2 px-4 py-3 text-sm">
        Your resume covers every skill this posting names. Focus on the wording
        of your bullets rather than adding anything.
      </p>
    );
  }

  const grouped = ORDER.map((severity) => ({
    severity,
    items: gaps.filter((gap) => gap.severity === severity),
  })).filter((group) => group.items.length > 0);

  let animationIndex = 0;

  return (
    <div className="flex flex-col gap-6">
      {grouped.map((group) => (
        <section key={group.severity}>
          <header className="mb-2 flex items-baseline gap-2">
            <span
              aria-hidden
              className="h-2.5 w-2.5"
              style={{ backgroundColor: severityColor[group.severity] }}
            />
            <h3
              className="text-sm font-bold"
              style={{ color: severityColor[group.severity] }}
            >
              {severityLabel[group.severity]}
            </h3>
            <span className="font-mono text-xs text-muted tabular-nums">
              {group.items.length}
            </span>
          </header>

          <p className="mb-3 max-w-[62ch] text-[13px] text-muted">
            {GUIDANCE[group.severity]}
          </p>

          <ul className="flex flex-wrap gap-2">
            {group.items.map((gap) => {
              const delay = reduceMotion ? 0 : animationIndex * 0.03;
              animationIndex += 1;

              return (
                <motion.li
                  key={gap.name}
                  initial={reduceMotion ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay }}
                  className="card px-3 py-1.5"
                  style={{
                    borderLeftWidth: 2,
                    borderLeftColor: severityColor[group.severity],
                  }}
                  // The weight is the reason this skill is in this bucket.
                  // Exposing it makes the ranking auditable instead of magic.
                  title={`Importance in this posting: ${Math.round(gap.weight * 100)}%`}
                >
                  <span className="text-sm font-medium">{gap.name}</span>
                  <span className="ml-2 font-mono text-[11px] text-muted tabular-nums">
                    {Math.round(gap.weight * 100)}%
                  </span>
                </motion.li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
