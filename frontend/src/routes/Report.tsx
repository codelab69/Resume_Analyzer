/**
 * Report screen - the centrepiece.
 *
 * Split view: the resume with its skills marked on the left, the score and its
 * ten rules on the right. Putting them side by side is the point. A list of
 * findings next to the document they describe lets the student verify every
 * claim the tool makes, which is what stops it feeling like a black box.
 */

import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";

import { getResume } from "@/lib/api";
import {
  bandLabel,
  formatDuration,
  formatExperience,
  prettyCategory,
} from "@/lib/format";
import { ResumeHighlight } from "@/components/ResumeHighlight";
import { RuleList } from "@/components/RuleList";
import { ScoreGauge } from "@/components/ScoreGauge";
import { ErrorBanner, Notice, SectionHeader, Spinner, Stat } from "@/components/ui";
import { useResumeStore } from "@/store/resume";

export function ReportScreen() {
  const { id = "" } = useParams();
  const reduceMotion = useReducedMotion();
  const setResumeId = useResumeStore((state) => state.setResumeId);
  const [focus, setFocus] = useState<Set<string>>(new Set());

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["resume", id],
    queryFn: () => getResume(id),
    enabled: Boolean(id),
  });

  // Landing here directly from a bookmark should make this the active resume,
  // so the nav links and the other screens follow.
  useMemo(() => {
    if (data?.id) setResumeId(data.id);
  }, [data?.id, setResumeId]);

  if (isLoading) return <Spinner label="Loading the report" />;
  if (error || !data) {
    return (
      <ErrorBanner
        message={
          error instanceof Error
            ? error.message
            : "That report could not be loaded."
        }
        onRetry={() => void refetch()}
      />
    );
  }

  const totalMs = Object.values(data.timings_ms).reduce((a, b) => a + b, 0);
  const toggleFocus = (skill: string) =>
    setFocus((current) => {
      const next = new Set(current);
      if (next.has(skill)) next.delete(skill);
      else next.add(skill);
      return next;
    });

  return (
    <div className="py-2">
      {/* --- header ------------------------------------------------------ */}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label mb-1">Report &middot; {data.filename}</p>
          <h1 className="font-display text-3xl font-extrabold">
            {data.profile.contact.name ?? "Resume analysis"}
          </h1>
          <p className="mt-1 text-sm text-muted">{data.role.summary}</p>
        </div>

        <div className="flex gap-2">
          <Link
            to={`/match/${data.id}`}
            className="bg-ink px-4 py-2 text-sm font-semibold text-paper transition-opacity hover:opacity-85"
          >
            Match to a job
          </Link>
          <Link
            to={`/jobs/${data.id}`}
            className="border border-rule-strong px-4 py-2 text-sm font-medium transition-colors hover:bg-surface-2"
          >
            See openings
          </Link>
        </div>
      </div>

      {data.warnings.length > 0 && (
        <div className="mb-6 flex flex-col gap-2">
          {data.warnings.map((warning) => (
            <Notice key={warning}>{warning}</Notice>
          ))}
        </div>
      )}

      {/* --- score and facts --------------------------------------------- */}
      <div className="mb-8 grid gap-5 lg:grid-cols-[auto_1fr]">
        <motion.div
          className="card flex flex-col items-center justify-center px-8 py-6"
          initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4 }}
        >
          <ScoreGauge
            score={data.ats.score}
            label={bandLabel[data.ats.band]}
            sublabel="Applicant tracking readiness"
          />
        </motion.div>

        <div className="grid content-start gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Stat
            label="Skills detected"
            value={data.skill_names.length}
            hint={`Across ${Object.keys(data.skills_by_category).length} categories`}
          />
          <Stat
            label="Experience"
            value={formatExperience(data.profile.experience_months)}
            hint="Work and dated project history only"
          />
          <Stat
            label="Highest degree"
            value={data.profile.education.highest_degree ?? "Not found"}
            hint={
              data.profile.education.cgpa
                ? `CGPA ${data.profile.education.cgpa}`
                : "No CGPA detected"
            }
          />
          <Stat label="Pages" value={data.page_count} hint={`Read with ${data.reader}`} />
          <Stat
            label="Sections found"
            value={data.sections.length}
            hint={data.sections.slice(0, 3).join(", ")}
          />
          <Stat
            label="Analysis time"
            value={formatDuration(totalMs)}
            hint="Across six pipeline stages"
          />
        </div>
      </div>

      {/* --- what to fix first -------------------------------------------- */}
      {data.ats.top_fixes.length > 0 && (
        <section className="mb-8">
          <SectionHeader
            eyebrow="Worth the most points"
            title="Fix these three first"
          />
          <ol className="grid gap-3 md:grid-cols-3">
            {data.ats.top_fixes.map((fix, index) => (
              <motion.li
                key={fix}
                className="card border-l-2 border-l-marker p-4"
                initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: reduceMotion ? 0 : index * 0.07 }}
              >
                <span className="label">Fix {index + 1}</span>
                <p className="mt-2 text-[13.5px] leading-relaxed">{fix}</p>
              </motion.li>
            ))}
          </ol>
        </section>
      )}

      {/* --- split view --------------------------------------------------- */}
      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <SectionHeader
            eyebrow={`${data.skills.length} occurrences marked`}
            title="Your resume, as the parser read it"
            aside={
              focus.size > 0 ? (
                <button
                  type="button"
                  onClick={() => setFocus(new Set())}
                  className="font-mono text-[11px] text-muted underline-offset-4 hover:underline"
                >
                  CLEAR FILTER ({focus.size})
                </button>
              ) : undefined
            }
          />
          <div className="card">
            <ResumeHighlight text={data.text} spans={data.skills} focus={focus} />
          </div>
          <p className="mt-2 text-[12px] text-muted">
            A dotted underline means the skill was recovered from a likely
            typo. Check those - they are the ones most likely to be wrong.
          </p>
        </section>

        <div className="flex flex-col gap-6">
          <section>
            <SectionHeader
              eyebrow="Ten checks, one hundred points"
              title="Readiness breakdown"
            />
            <div className="card">
              <RuleList rules={data.ats.rules} />
            </div>
          </section>

          <section>
            <SectionHeader
              eyebrow="Click a skill to isolate it in the text"
              title="Skills by category"
            />
            <div className="flex flex-col gap-4">
              {Object.entries(data.skills_by_category)
                .sort(([, a], [, b]) => b.length - a.length)
                .map(([category, names]) => (
                  <div key={category}>
                    <p className="label mb-2">
                      {prettyCategory(category)} &middot; {names.length}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {names.map((name) => {
                        const isFocused = focus.has(name);
                        return (
                          <button
                            key={name}
                            type="button"
                            onClick={() => toggleFocus(name)}
                            aria-pressed={isFocused}
                            // py-1, not py-0.5: 13px text on a 19.5px line
                            // height plus 2px of padding came to 23.5px, and
                            // WCAG 2.2 SC 2.5.8 asks for 24. Half a pixel, on
                            // the control a phone user taps most on this
                            // screen. 4px of padding takes it to 27.5.
                            // The identically padded chips elsewhere are all
                            // <span> labels, so the criterion does not reach
                            // them - only this one is a target. See issue #2.
                            className={`px-2 py-1 text-[13px] transition-colors ${
                              isFocused ? "mark-active" : "mark"
                            }`}
                          >
                            {name}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
