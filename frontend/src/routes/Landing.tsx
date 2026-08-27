/**
 * Landing screen.
 *
 * One job: get the visitor to upload a resume. It states what the tool does,
 * what it does not do, and gets out of the way. There is no marketing section,
 * no testimonials and no feature grid - this is a tool a student was sent a
 * link to, not a product they are being sold.
 */

import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";

import { useResumeStore } from "@/store/resume";

const STEPS = [
  {
    n: "01",
    title: "It reads the file",
    body: "PDF or Word. Text, layout and structure - the same things automated screening software sees before a person ever does.",
  },
  {
    n: "02",
    title: "It scores what is fixable",
    body: "Ten checks, a hundred points, every one of them explained. No black box, no single opaque number.",
  },
  {
    n: "03",
    title: "It compares against a real job",
    body: "Paste any job description. Get a match score broken into its four parts, and the exact skills that are missing.",
  },
];

export function LandingScreen() {
  const reduceMotion = useReducedMotion();
  const resumeId = useResumeStore((state) => state.resumeId);

  return (
    <div className="py-6">
      <motion.section
        initial={reduceMotion ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="max-w-[52ch]"
      >
        <p className="label mb-4">Resume analysis &middot; job matching</p>

        <h1 className="font-display text-4xl font-extrabold leading-[1.05] sm:text-5xl">
          Find out what a screening system{" "}
          <span className="mark">actually reads</span> in your resume.
        </h1>

        <p className="mt-5 text-[17px] leading-relaxed text-ink-soft">
          Upload a resume and get back a readiness score with every deduction
          explained, a match score against any job description broken into its
          parts, and the ranked list of skills standing between you and the
          role.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link
            to="/upload"
            className="bg-ink px-6 py-3 text-sm font-semibold text-paper transition-opacity hover:opacity-85"
          >
            Analyse a resume
          </Link>
          {resumeId && (
            <Link
              to={`/report/${resumeId}`}
              className="border border-rule-strong px-6 py-3 text-sm font-medium transition-colors hover:bg-surface-2"
            >
              Back to my last report
            </Link>
          )}
        </div>

        <p className="mt-4 font-mono text-[11px] text-muted">
          PDF, DOCX or TXT &middot; nothing is sent anywhere except this app's
          own backend
        </p>
      </motion.section>

      <section className="mt-16 grid gap-px border border-rule bg-rule sm:grid-cols-3">
        {STEPS.map((step, index) => (
          <motion.article
            key={step.n}
            className="bg-surface p-5"
            initial={reduceMotion ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: reduceMotion ? 0 : 0.15 + index * 0.08 }}
          >
            {/* Numbered because these really are sequential - the pipeline
                runs in this order and each step needs the one before it. */}
            <span className="label">{step.n}</span>
            <h2 className="mt-2 font-display text-lg font-bold">{step.title}</h2>
            <p className="mt-2 text-[14px] leading-relaxed text-muted">
              {step.body}
            </p>
          </motion.article>
        ))}
      </section>

      <section className="mt-10 max-w-[62ch]">
        <p className="label mb-2">What this is not</p>
        <p className="text-[14px] leading-relaxed text-muted">
          It does not predict whether you will get an interview, and it does not
          rewrite your resume for you. It measures the things that are
          measurable - structure, keywords, skill coverage, eligibility - and
          tells you which of them you can change.
        </p>
      </section>
    </div>
  );
}
