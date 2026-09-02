/**
 * One recommended job.
 *
 * Every card states why it surfaced. A recommendation with no visible reason
 * reads as arbitrary and the student cannot act on it - so `why`, the matched
 * skills and the missing ones are all on the card, not behind a click.
 */

import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { scoreColor } from "@/lib/format";
import type { Job } from "@/lib/types";

interface Props {
  job: Job;
  index: number;
}

export function JobCard({ job, index }: Props) {
  const reduceMotion = useReducedMotion();
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.article
      className="card"
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: reduceMotion ? 0 : index * 0.05 }}
    >
      <div className="flex items-start gap-4 p-4">
        {/* Score first: it is what the list is sorted by. */}
        <div
          className="flex h-12 w-12 shrink-0 flex-col items-center justify-center border"
          style={{ borderColor: scoreColor(job.score) }}
        >
          <span
            className="font-display text-lg font-extrabold leading-none tabular-nums"
            style={{ color: scoreColor(job.score) }}
          >
            {job.score}
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <h3 className="font-display text-base font-bold">{job.title}</h3>
          <p className="text-sm text-muted">
            {job.company} &middot; {job.location} &middot; {job.employment_type}
          </p>

          <p className="mt-2 text-[13.5px]">{job.why}</p>

          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {job.matching_skills.slice(0, 6).map((skill) => (
              <span key={skill} className="mark px-1.5 text-[12px]">
                {skill}
              </span>
            ))}
            {job.matching_skills.length > 6 && (
              <span className="font-mono text-[11px] text-muted">
                +{job.matching_skills.length - 6}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            // 11px text with no vertical padding made this a 16.5px tap
            // target - the disclosure on every job card, and the smallest
            // control in the app. py-1.5 takes it to 28.5px; mt-2 rather than
            // mt-3 keeps the gap above it looking the same. See issue #2.
            className="mt-2 py-1.5 font-mono text-[11px] uppercase tracking-wider text-muted underline-offset-4 hover:underline"
          >
            {expanded ? "Hide details" : "What they ask for"}
          </button>
        </div>

        {job.experience_years > 0 && (
          <span className="shrink-0 border border-rule-strong px-2 py-0.5 font-mono text-[11px] text-muted">
            {job.experience_years}+ yrs
          </span>
        )}
      </div>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={reduceMotion ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduceMotion ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            className="overflow-hidden border-t border-rule"
          >
            <div className="space-y-4 p-4">
              <p className="max-w-[70ch] text-[13.5px] leading-relaxed text-ink-soft">
                {job.description}
              </p>

              <div>
                <p className="label mb-2">Requirements</p>
                <ul className="list-disc space-y-1 pl-5 text-[13.5px] text-ink-soft">
                  {job.requirements.map((requirement) => (
                    <li key={requirement}>{requirement}</li>
                  ))}
                </ul>
              </div>

              {job.missing_skills.length > 0 && (
                <div>
                  <p className="label mb-2">Not on your resume</p>
                  <div className="flex flex-wrap gap-1.5">
                    {job.missing_skills.map((skill) => (
                      <span
                        key={skill}
                        className="border border-rule px-2 py-0.5 text-[12px] text-muted"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
}
