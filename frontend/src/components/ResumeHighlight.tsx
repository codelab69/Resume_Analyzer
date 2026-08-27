/**
 * The resume text with every detected skill marked, in place.
 *
 * This is the component that makes the analysis believable. A list of
 * extracted skills is a claim; the same skills highlighted inside the
 * student's own resume is proof, and it immediately exposes false positives
 * where a list would hide them.
 *
 * HOW THE OFFSETS WORK
 * --------------------
 * The API returns `text` plus spans carrying absolute character offsets into
 * that exact string. Slice, never search: searching for the skill name would
 * mark the wrong occurrence when a skill appears more than once, and would
 * miss alias matches entirely ("sklearn" is highlighted, "scikit-learn" is
 * the name).
 *
 * The spans arrive sorted and never overlap - the matcher consumes tokens as
 * it goes - so a single pass through them is enough.
 */

import { useMemo } from "react";
import { motion, useReducedMotion } from "motion/react";

import type { SkillSpan } from "@/lib/types";

interface Props {
  text: string;
  spans: SkillSpan[];
  /** Highlight only these skill names. Empty or undefined marks all of them. */
  focus?: Set<string>;
}

type Piece =
  | { kind: "plain"; text: string }
  | { kind: "skill"; text: string; span: SkillSpan };

function split(text: string, spans: SkillSpan[]): Piece[] {
  const pieces: Piece[] = [];
  let cursor = 0;

  for (const span of spans) {
    // Defensive: a malformed span must not corrupt the whole document.
    if (span.start < cursor || span.end > text.length || span.start >= span.end) {
      continue;
    }
    if (span.start > cursor) {
      pieces.push({ kind: "plain", text: text.slice(cursor, span.start) });
    }
    pieces.push({
      kind: "skill",
      text: text.slice(span.start, span.end),
      span,
    });
    cursor = span.end;
  }

  if (cursor < text.length) {
    pieces.push({ kind: "plain", text: text.slice(cursor) });
  }
  return pieces;
}

export function ResumeHighlight({ text, spans, focus }: Props) {
  const reduceMotion = useReducedMotion();

  // Splitting a two-page resume into a few hundred pieces on every render
  // would make the focus filter feel sluggish, so it is memoised on the
  // inputs that actually change it.
  const pieces = useMemo(() => split(text, spans), [text, spans]);

  let markIndex = 0;

  return (
    <div className="max-h-[70vh] overflow-y-auto px-5 py-4">
      <pre className="font-sans text-[14.5px] leading-[1.75] whitespace-pre-wrap break-words text-ink-soft">
        {pieces.map((piece, index) => {
          if (piece.kind === "plain") {
            return <span key={index}>{piece.text}</span>;
          }

          const isFocused = !focus || focus.size === 0 || focus.has(piece.span.name);
          if (!isFocused) {
            return <span key={index}>{piece.text}</span>;
          }

          // Stagger the marker sweep so it reads like someone running a
          // highlighter down the page, not like everything flashing at once.
          const delay = reduceMotion ? 0 : Math.min(markIndex * 0.04, 1.6);
          markIndex += 1;

          return (
            <motion.mark
              key={index}
              className="mark text-ink"
              title={`${piece.span.name} (${piece.span.category}${
                piece.span.method === "fuzzy" ? ", fuzzy match" : ""
              })`}
              initial={
                reduceMotion
                  ? { backgroundSize: "100% 100%" }
                  : { backgroundSize: "0% 100%" }
              }
              animate={{ backgroundSize: "100% 100%" }}
              transition={{ duration: 0.28, delay, ease: "easeOut" }}
              style={{
                backgroundRepeat: "no-repeat",
                // A dotted underline distinguishes a fuzzy (typo-recovered)
                // match from an exact one, so a wrong guess is visible.
                textDecoration:
                  piece.span.method === "fuzzy" ? "underline dotted" : undefined,
              }}
            >
              {piece.text}
            </motion.mark>
          );
        })}
      </pre>
    </div>
  );
}
