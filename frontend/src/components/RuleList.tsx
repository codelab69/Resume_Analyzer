/**
 * The ten ATS rules, each with what it measured and what to do about it.
 *
 * Rules are shown in "needs attention first" order rather than in the order
 * they run. A student reading top to bottom should hit the thing costing them
 * the most points first; a list that opens with eight passes buries it.
 */

import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { statusColor, statusLabel } from "@/lib/format";
import type { AtsRule } from "@/lib/types";

interface Props {
  rules: AtsRule[];
}

export function RuleList({ rules }: Props) {
  const reduceMotion = useReducedMotion();
  // Rules that lost points open by default - the fix is the point of the
  // screen, so hiding it behind a click would be perverse.
  const [open, setOpen] = useState<Set<string>>(
    () => new Set(rules.filter((r) => r.status !== "pass").map((r) => r.id)),
  );

  const ordered = [...rules].sort((a, b) => {
    const lost = (rule: AtsRule) => rule.points - rule.earned;
    return lost(b) - lost(a);
  });

  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <ul className="divide-y divide-rule">
      {ordered.map((rule) => {
        const isOpen = open.has(rule.id);
        const lost = rule.points - rule.earned;
        const filled = (rule.earned / rule.points) * 100;

        return (
          <li key={rule.id}>
            <button
              type="button"
              onClick={() => toggle(rule.id)}
              aria-expanded={isOpen}
              className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-2"
            >
              {/* Status stripe: state readable without reading the number. */}
              <span
                aria-hidden
                className="mt-1.5 h-3 w-1 shrink-0"
                style={{ backgroundColor: statusColor[rule.status] }}
              />

              <span className="min-w-0 flex-1">
                <span className="flex items-baseline justify-between gap-3">
                  <span className="font-display text-[15px] font-bold">
                    {rule.title}
                  </span>
                  <span className="shrink-0 font-mono text-xs tabular-nums text-muted">
                    {rule.earned}/{rule.points}
                  </span>
                </span>

                <span className="mt-1.5 flex items-center gap-2">
                  <span className="h-1 flex-1 overflow-hidden bg-surface-2">
                    <span
                      className="block h-full"
                      style={{
                        width: `${filled}%`,
                        backgroundColor: statusColor[rule.status],
                      }}
                    />
                  </span>
                  <span
                    className="label"
                    style={{ color: statusColor[rule.status] }}
                  >
                    {statusLabel[rule.status]}
                  </span>
                </span>
              </span>
            </button>

            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  initial={reduceMotion ? false : { height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={reduceMotion ? undefined : { height: 0, opacity: 0 }}
                  transition={{ duration: 0.22, ease: "easeOut" }}
                  className="overflow-hidden"
                >
                  <div className="space-y-2 px-4 pb-4 pl-8">
                    <p className="text-[13.5px] text-muted">{rule.detail}</p>
                    {rule.fix && (
                      <p className="border-l-2 border-marker bg-surface-2 px-3 py-2 text-[13.5px] leading-relaxed">
                        <span className="label mr-2">Fix</span>
                        {rule.fix}
                      </p>
                    )}
                    {lost > 0 && !rule.fix && (
                      <p className="text-[13px] text-muted">
                        Worth {lost.toFixed(1)} more points.
                      </p>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </li>
        );
      })}
    </ul>
  );
}
