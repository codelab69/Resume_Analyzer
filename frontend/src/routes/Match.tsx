/**
 * Job match screen.
 *
 * Paste a job description, get a score with its four parts and the ranked
 * gaps. The total is never shown on its own - the sub-scores sit beside it,
 * because "62" is not something a student can act on and "34 on skill
 * overlap" is.
 */

import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";

import { ApiError, createMatch, getMatchHistory, getResume } from "@/lib/api";
import { formatDate, scoreColor, verdictLabel } from "@/lib/format";
import { GapList } from "@/components/GapList";
import { MatchBars } from "@/components/MatchBars";
import { ScoreGauge } from "@/components/ScoreGauge";
import {
  ErrorBanner,
  Notice,
  PrimaryButton,
  SectionHeader,
  Spinner,
} from "@/components/ui";
import type { MatchResponse } from "@/lib/types";

const MIN_LENGTH = 40;

export function MatchScreen() {
  const { id = "" } = useParams();
  const reduceMotion = useReducedMotion();

  const [jobText, setJobText] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [result, setResult] = useState<MatchResponse | null>(null);

  const {
    data: resume,
    isLoading,
    error: resumeError,
    refetch: refetchResume,
  } = useQuery({
    queryKey: ["resume", id],
    queryFn: () => getResume(id),
    enabled: Boolean(id),
  });

  const history = useQuery({
    queryKey: ["match-history", id],
    queryFn: () => getMatchHistory(id),
    enabled: Boolean(id),
  });

  const mutation = useMutation({
    mutationFn: () =>
      createMatch({
        resumeId: id,
        jobDescription: jobText,
        jobTitle: jobTitle.trim() || undefined,
      }),
    onSuccess: (data) => {
      setResult(data);
      void history.refetch();
    },
  });

  if (isLoading) return <Spinner label="Loading the resume" />;

  // This query's error used to be dropped on the floor: only `data` and
  // `isLoading` were read, so a resume that no longer exists rendered the full
  // form. A student could paste an entire job description, press Score this
  // match, and only then be told the resume was gone - having lost the paste.
  // Report and Openings both guard here; this screen is the one that did not.
  if (resumeError || !resume) {
    return (
      <ErrorBanner
        message={
          resumeError instanceof Error
            ? resumeError.message
            : "That resume could not be loaded."
        }
        onRetry={() => void refetchResume()}
      />
    );
  }

  const tooShort = jobText.trim().length < MIN_LENGTH;

  return (
    <div className="py-2">
      <p className="label mb-1">Step 2 of 3</p>
      <h1 className="font-display text-3xl font-extrabold">Match to a job</h1>
      <p className="mt-2 max-w-[62ch] text-[15px] text-ink-soft">
        Paste the whole posting, including the requirements list. A job title
        on its own has nothing to measure against and will produce a score that
        means nothing.
      </p>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {/* --- input ----------------------------------------------------- */}
        <section>
          <SectionHeader eyebrow="The posting" title="Job description" />

          <label className="mb-3 block">
            <span className="label mb-1.5 block">Title (optional)</span>
            <input
              value={jobTitle}
              onChange={(event) => setJobTitle(event.target.value)}
              placeholder="Backend Developer at Northwind"
              className="w-full border border-rule bg-surface px-3 py-2 text-sm outline-none focus:border-rule-strong"
            />
            <span className="mt-1 block text-[12px] text-muted">
              Only used to label this match in your history.
            </span>
          </label>

          <label className="block">
            <span className="label mb-1.5 block">Full posting</span>
            <textarea
              value={jobText}
              onChange={(event) => setJobText(event.target.value)}
              rows={16}
              placeholder={"Paste the job description here, including:\n\n- what the role does\n- the requirements list\n- any experience or degree requirements"}
              className="w-full resize-y border border-rule bg-surface px-3 py-2 font-mono text-[13px] leading-relaxed outline-none focus:border-rule-strong"
            />
          </label>

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <PrimaryButton
              onClick={() => mutation.mutate()}
              disabled={tooShort || mutation.isPending}
            >
              {mutation.isPending ? "Scoring..." : "Score this match"}
            </PrimaryButton>
            <span className="font-mono text-[11px] text-muted tabular-nums">
              {jobText.trim().length} characters
              {tooShort && jobText.length > 0 && ` — need at least ${MIN_LENGTH}`}
            </span>
          </div>

          {mutation.isError && (
            <div className="mt-4">
              <ErrorBanner
                message={
                  mutation.error instanceof ApiError
                    ? mutation.error.message
                    : "The match could not be scored."
                }
                onRetry={() => mutation.mutate()}
              />
            </div>
          )}

          {/* --- history ------------------------------------------------- */}
          {history.data && history.data.length > 0 && (
            <div className="mt-8">
              <SectionHeader eyebrow="Saved" title="Previous matches" />
              <ul className="divide-y divide-rule border border-rule">
                {history.data.map((row) => (
                  <li
                    key={row.id}
                    className="flex items-center justify-between gap-3 bg-surface px-3 py-2"
                  >
                    <span className="min-w-0 truncate text-sm">
                      {row.job_title ?? "Untitled posting"}
                    </span>
                    <span className="flex shrink-0 items-center gap-3">
                      <span className="font-mono text-[11px] text-muted">
                        {formatDate(row.created_at)}
                      </span>
                      <span
                        className="font-display text-sm font-bold tabular-nums"
                        style={{ color: scoreColor(row.score) }}
                      >
                        {row.score}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* --- result ---------------------------------------------------- */}
        <section>
          {!result ? (
            <div className="card flex h-full min-h-[300px] flex-col items-center justify-center gap-3 px-6 py-14 text-center">
              <h3 className="font-display text-lg font-bold">
                No match scored yet
              </h3>
              <p className="max-w-[42ch] text-sm text-muted">
                {resume
                  ? `${resume.skill_names.length} skills were found in this resume. Paste a posting to see how many of them the job actually asks for.`
                  : "Paste a posting to score it."}
              </p>
            </div>
          ) : (
            <motion.div
              initial={reduceMotion ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="flex flex-col gap-6"
            >
              <div className="card flex flex-wrap items-center gap-6 p-6">
                <ScoreGauge
                  score={result.score}
                  size={150}
                  label={verdictLabel[result.verdict]}
                />
                <div className="min-w-[200px] flex-1">
                  <p className="label mb-2">Against this posting</p>
                  <p className="text-sm text-ink-soft">
                    The job names{" "}
                    <strong>{result.jd_skill_count} recognised skills</strong>.
                    Your resume shows{" "}
                    <strong>{result.matched_skills.length}</strong> of them.
                  </p>
                  {result.extra_skills.length > 0 && (
                    <p className="mt-2 text-[13px] text-muted">
                      You also have {result.extra_skills.length} skills this
                      posting did not ask for. Those never reduce your score.
                    </p>
                  )}
                </div>
              </div>

              {result.notes.length > 0 && (
                <div className="flex flex-col gap-2">
                  {result.notes.map((note) => (
                    <Notice key={note}>{note}</Notice>
                  ))}
                </div>
              )}

              <section>
                <SectionHeader
                  eyebrow="Where the score came from"
                  title="The four signals"
                />
                <MatchBars subScores={result.sub_scores} weights={result.weights} />
              </section>

              <section>
                <SectionHeader
                  eyebrow={`${result.missing_skills.length} to close`}
                  title="Skill gaps"
                />
                <GapList gaps={result.missing_skills} />
              </section>

              {result.matched_skills.length > 0 && (
                <section>
                  <SectionHeader
                    eyebrow="Already covered"
                    title="What lined up"
                  />
                  <div className="flex flex-wrap gap-1.5">
                    {result.matched_skills.map((skill) => (
                      <span key={skill} className="mark px-2 py-0.5 text-[13px]">
                        {skill}
                      </span>
                    ))}
                  </div>
                </section>
              )}
            </motion.div>
          )}
        </section>
      </div>
    </div>
  );
}
