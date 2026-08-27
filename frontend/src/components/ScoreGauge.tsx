/**
 * Animated radial score gauge.
 *
 * The centrepiece of the report screen. An SVG arc whose stroke is drawn on
 * with `strokeDashoffset`, and a number that counts up to the score.
 *
 * WHY A SPRING RATHER THAN A LINEAR TWEEN
 * ---------------------------------------
 * A linear count-up reads as a loading bar - a thing you wait for. A spring
 * settles, which reads as a measurement landing. It is a small difference and
 * it is the whole feel of the moment the student has been waiting for.
 *
 * Reduced motion is respected: the arc and the number appear at their final
 * values with no animation at all.
 */

import { useEffect } from "react";
import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "motion/react";

import { scoreColor } from "@/lib/format";

interface Props {
  score: number;
  /** Outer diameter in pixels. */
  size?: number;
  label?: string;
  sublabel?: string;
}

const STROKE = 12;

export function ScoreGauge({ score, size = 200, label, sublabel }: Props) {
  const reduceMotion = useReducedMotion();

  // One motion value drives both the arc and the digits, so they can never
  // drift out of sync mid-animation.
  const progress = useMotionValue(reduceMotion ? score : 0);
  const displayed = useTransform(progress, (value) => Math.round(value));

  const radius = (size - STROKE) / 2;
  const circumference = 2 * Math.PI * radius;
  // The arc is drawn as one dash the length of the circle, offset backwards by
  // the portion that should stay hidden.
  const offset = useTransform(
    progress,
    (value) => circumference - (Math.max(0, Math.min(100, value)) / 100) * circumference,
  );

  useEffect(() => {
    if (reduceMotion) {
      progress.set(score);
      return;
    }
    const controls = animate(progress, score, {
      type: "spring",
      stiffness: 55,
      damping: 16,
      // Without this the spring can overshoot past 100 and the arc briefly
      // wraps around itself.
      restDelta: 0.5,
    });
    return () => controls.stop();
  }, [score, progress, reduceMotion]);

  const color = scoreColor(score);

  return (
    <div
      className="relative inline-flex items-center justify-center"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${label ?? "Score"}: ${score} out of 100`}
    >
      <svg width={size} height={size} className="-rotate-90">
        {/* Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-surface-2)"
          strokeWidth={STROKE}
        />
        {/* Value */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={STROKE}
          strokeLinecap="butt"
          strokeDasharray={circumference}
          style={{ strokeDashoffset: offset }}
        />
      </svg>

      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="flex items-baseline font-display font-extrabold tabular-nums">
          <motion.span style={{ fontSize: size * 0.3, lineHeight: 1 }}>
            {displayed}
          </motion.span>
          <span
            className="text-muted font-semibold"
            style={{ fontSize: size * 0.12 }}
          >
            /100
          </span>
        </div>
        {label && (
          <span className="label mt-2" style={{ color }}>
            {label}
          </span>
        )}
        {sublabel && (
          <span className="text-muted mt-1 text-xs">{sublabel}</span>
        )}
      </div>
    </div>
  );
}
