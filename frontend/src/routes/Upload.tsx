/**
 * Upload screen.
 *
 * The interesting part of this screen is the wait. Analysis takes a couple of
 * seconds, and a spinner in that gap makes the app feel like it is thinking
 * about nothing in particular. The stepper instead names each pipeline stage
 * as it goes, which turns dead time into an explanation of what the tool does.
 *
 * The stepper is honest about what it is: the backend does not stream
 * progress, so the steps advance on a timer calibrated to real stage timings
 * and the final step waits for the actual response. It never claims a stage
 * finished after the request has failed.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { ApiError, uploadResume } from "@/lib/api";
import { ErrorBanner } from "@/components/ui";
import { useResumeStore } from "@/store/resume";

const STAGES = [
  "Reading the file",
  "Finding the sections",
  "Pulling out contact details",
  "Matching skills",
  "Predicting the role",
  "Running the readiness checks",
];

const ACCEPT = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "text/plain": [".txt"],
};

const MAX_BYTES = 5 * 1024 * 1024;

export function UploadScreen() {
  const navigate = useNavigate();
  const reduceMotion = useReducedMotion();
  const setResumeId = useResumeStore((state) => state.setResumeId);

  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const timers = useRef<number[]>([]);

  // Any pending stage timer must be cleared when the component unmounts, or
  // React logs a state update on an unmounted component after navigation.
  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach(window.clearTimeout);
  }, []);

  const runStages = useCallback(() => {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
    setStage(0);
    // Stop one short of the end: the last stage stays lit until the real
    // response lands, so the UI never shows "done" before it is.
    STAGES.slice(0, -1).forEach((_, index) => {
      timers.current.push(
        window.setTimeout(() => setStage(index + 1), 260 * (index + 1)),
      );
    });
  }, []);

  const onDrop = useCallback(
    async (accepted: File[], rejected: readonly { file: File }[]) => {
      setError(null);

      if (rejected.length > 0) {
        const name = rejected[0]?.file.name ?? "That file";
        setError(
          `${name} cannot be read. Upload a PDF, DOCX or TXT file under 5 MB.`,
        );
        return;
      }

      const file = accepted[0];
      if (!file) return;

      setBusy(true);
      runStages();

      try {
        const report = await uploadResume(file);
        setResumeId(report.id);
        navigate(`/report/${report.id}`);
      } catch (caught) {
        timers.current.forEach(window.clearTimeout);
        setError(
          caught instanceof ApiError
            ? caught.message
            : "The analysis could not be completed. Try again.",
        );
        setBusy(false);
      }
    },
    [navigate, runStages, setResumeId],
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxSize: MAX_BYTES,
    multiple: false,
    disabled: busy,
    noClick: true,
    noKeyboard: true,
  });

  return (
    <div className="mx-auto max-w-2xl py-6">
      <p className="label mb-3">Step 1 of 3</p>
      <h1 className="font-display text-3xl font-extrabold">Upload a resume</h1>
      <p className="mt-3 max-w-[56ch] text-[15px] text-ink-soft">
        A text-based PDF gives the most accurate result. If the file is a scan
        or a photo, the analyser will say so rather than guess.
      </p>

      <div className="mt-8">
        <AnimatePresence mode="wait">
          {busy ? (
            <motion.div
              key="progress"
              initial={reduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="card p-6"
            >
              <p className="label mb-4">Analysing</p>
              <ol className="flex flex-col gap-2.5">
                {STAGES.map((name, index) => {
                  const done = index < stage;
                  const active = index === stage;
                  return (
                    <li key={name} className="flex items-center gap-3">
                      <span
                        aria-hidden
                        className="h-2 w-2 shrink-0 transition-colors"
                        style={{
                          backgroundColor: done
                            ? "var(--color-good)"
                            : active
                              ? "var(--color-marker)"
                              : "var(--color-rule-strong)",
                        }}
                      />
                      <span
                        className="text-sm transition-colors"
                        style={{
                          color:
                            done || active
                              ? "var(--color-ink)"
                              : "var(--color-muted)",
                          fontWeight: active ? 600 : 400,
                        }}
                      >
                        {name}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </motion.div>
          ) : (
            // getRootProps() supplies native HTML drag handlers, and motion
            // defines its own `onDrag` with a different signature. Spreading
            // them onto the same element is a type conflict and, worse, would
            // let motion swallow the drop event. Plain wrapper outside,
            // animated surface inside.
            <div key="dropzone" {...getRootProps()}>
              <motion.div
                initial={reduceMotion ? false : { opacity: 0 }}
                animate={{
                  opacity: 1,
                  scale: isDragActive && !reduceMotion ? 1.015 : 1,
                }}
                exit={{ opacity: 0 }}
                transition={{ type: "spring", stiffness: 300, damping: 25 }}
                className="card flex flex-col items-center gap-4 border-dashed px-6 py-14 text-center"
                style={{
                  borderColor: isDragActive
                    ? "var(--color-marker)"
                    : "var(--color-rule-strong)",
                  backgroundColor: isDragActive
                    ? "var(--color-surface-2)"
                    : "var(--color-surface)",
                }}
              >
                <input {...getInputProps()} />
                <p className="font-display text-lg font-bold">
                  {isDragActive ? "Drop it here" : "Drag a resume here"}
                </p>
                <p className="text-sm text-muted">
                  PDF, DOCX or TXT &middot; up to 5 MB
                </p>
                <button
                  type="button"
                  onClick={open}
                  className="bg-ink px-5 py-2.5 text-sm font-semibold text-paper transition-opacity hover:opacity-85"
                >
                  Choose a file
                </button>
              </motion.div>
            </div>
          )}
        </AnimatePresence>
      </div>

      {error && (
        <div className="mt-4">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="mt-10 border-t border-rule pt-5">
        <p className="label mb-2">Before you upload</p>
        <ul className="list-disc space-y-1.5 pl-5 text-[13.5px] text-muted">
          <li>Export from Word or Google Docs rather than scanning a printout.</li>
          <li>
            A single-column layout is read correctly by every parser. Two-column
            templates are not.
          </li>
          <li>
            Uploading the same file twice returns the stored analysis instead of
            creating a duplicate.
          </li>
        </ul>
      </div>
    </div>
  );
}
