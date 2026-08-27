/**
 * The four sub-scores behind a match score.
 *
 * This component exists because a single number is not actionable. "You
 * scored 62" tells a student nothing; "81 on semantic fit but 34 on skill
 * overlap" tells them to add the missing skills rather than rewrite their
 * bullets. Never render the total without these.
 *
 * The weight of each signal is shown next to it, so the student can see why a
 * strong showing on one bar moved the total less than they expected.
 */

import { motion, useReducedMotion } from "motion/react";

import { percent, scoreColor } from "@/lib/format";
import type { SubScores } from "@/lib/types";

interface Props {
  subScores: SubScores;
  weights: Record<string, number>;
}

/** Order is fixed and matches the weights, heaviest signal first. */
const SIGNALS: {
  key: keyof SubScores;
  title: string;
  explain: string;
}[] = [
  {
    key: "semantic",
    title: "Meaning",
    explain:
      "How well your described experience covers what the job asks for, even when the wording differs.",
  },
  {
    key: "skill",
    title: "Skill overlap",
    explain:
      "How many of the job's skills you show, weighted by how central each one is to that posting.",
  },
  {
    key: "lexical",
    title: "Keywords",
    explain:
      "Literal word overlap. This is what most automated screening software actually measures.",
  },
  {
    key: "fit",
    title: "Eligibility",
    explain: "Years of experience and degree level against what the posting requires.",
  },
];

export function MatchBars({ subScores, weights }: Props) {
  const reduceMotion = useReducedMotion();

  return (
    <ul className="flex flex-col gap-5">
      {SIGNALS.map((signal, index) => {
        const value = subScores[signal.key];
        const value100 = percent(value);
        const weight = weights[signal.key] ?? 0;

        return (
          <li key={signal.key}>
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <span className="font-display text-[15px] font-bold">
                {signal.title}
              </span>
              <span className="font-mono text-xs text-muted tabular-nums">
                {Math.round(weight * 100)}% of total
              </span>
            </div>

            <div className="flex items-center gap-3">
              <div
                className="h-2 flex-1 overflow-hidden bg-surface-2"
                role="meter"
                aria-valuenow={value100}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={signal.title}
              >
                <motion.div
                  className="h-full"
                  style={{ backgroundColor: scoreColor(value100) }}
                  initial={{ width: reduceMotion ? `${value100}%` : 0 }}
                  animate={{ width: `${value100}%` }}
                  transition={
                    reduceMotion
                      ? { duration: 0 }
                      : {
                          duration: 0.7,
                          // Stagger so the four bars read as a sequence
                          // rather than one block moving.
                          delay: 0.12 * index,
                          ease: [0.2, 0.7, 0.3, 1],
                        }
                  }
                />
              </div>
              <span className="w-9 text-right font-mono text-sm font-bold tabular-nums">
                {value100}
              </span>
            </div>

            <p className="mt-1.5 max-w-[62ch] text-[13px] leading-relaxed text-muted">
              {signal.explain}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
