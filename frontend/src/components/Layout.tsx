/**
 * App shell: masthead, navigation, theme toggle, degraded-mode banner.
 *
 * The navigation is context-aware. Report, Match and Jobs all operate on one
 * resume, so those links only appear once a resume is loaded - showing links
 * that lead to an error page is worse than showing nothing.
 */

import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { useQuery } from "@tanstack/react-query";

import { getHealth } from "@/lib/api";
import { useTheme } from "@/store/theme";
import { useResumeStore } from "@/store/resume";

interface NavItem {
  to: string;
  label: string;
  /** Needs a loaded resume to be reachable. */
  scoped?: boolean;
}

const NAV: NavItem[] = [
  { to: "/upload", label: "Analyse" },
  { to: "/report", label: "Report", scoped: true },
  { to: "/match", label: "Job match", scoped: true },
  { to: "/jobs", label: "Openings", scoped: true },
  { to: "/dashboard", label: "History" },
];

export function Layout({ children }: { children: ReactNode }) {
  const { theme, toggle } = useTheme();
  const resumeId = useResumeStore((state) => state.resumeId);
  const location = useLocation();
  const reduceMotion = useReducedMotion();

  // Health is polled rarely - it changes only when the server restarts, and a
  // tight poll would put a request in the log every few seconds during a demo.
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 60_000,
    retry: false,
  });

  const links = NAV.filter((item) => !item.scoped || resumeId);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-rule bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-5 py-3">
          <NavLink to="/" className="flex items-baseline gap-2">
            <span className="font-display text-lg font-extrabold tracking-tight">
              Resume Analyzer
            </span>
          </NavLink>

          <nav className="flex flex-wrap items-center gap-1" aria-label="Main">
            {links.map((item) => {
              const to = item.scoped ? `${item.to}/${resumeId}` : item.to;
              const isActive = location.pathname.startsWith(item.to);
              return (
                <NavLink
                  key={item.to}
                  to={to}
                  className="relative px-3 py-1.5 text-sm font-medium transition-colors"
                  style={{
                    color: isActive ? "var(--color-ink)" : "var(--color-muted)",
                  }}
                >
                  {item.label}
                  {isActive && (
                    <motion.span
                      // layoutId gives the underline a shared-element
                      // transition between links instead of a hard cut.
                      layoutId="nav-underline"
                      className="absolute inset-x-2 -bottom-0.5 h-0.5 bg-marker"
                      transition={
                        reduceMotion
                          ? { duration: 0 }
                          : { type: "spring", stiffness: 380, damping: 30 }
                      }
                    />
                  )}
                </NavLink>
              );
            })}
          </nav>

          <button
            type="button"
            onClick={toggle}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            className="ml-auto border border-rule-strong px-2.5 py-1 font-mono text-[11px] transition-colors hover:bg-surface-2"
          >
            {theme === "dark" ? "LIGHT" : "DARK"}
          </button>
        </div>

        {/*
          Degraded mode is stated up front. A word-overlap score presented
          without this banner would be read as a semantic one, and every
          number on the screen would be quietly misinterpreted.
        */}
        {health?.status === "degraded" && (
          <div className="border-t border-rule bg-surface-2 px-5 py-1.5">
            <p className="mx-auto max-w-6xl font-mono text-[11px] text-muted">
              REDUCED ACCURACY MODE &middot; {health.notes[0] ?? "A component is unavailable."}
            </p>
          </div>
        )}
      </header>

      <main className="mx-auto max-w-6xl px-5 py-8">{children}</main>

      <footer className="mx-auto max-w-6xl border-t border-rule px-5 py-6">
        <p className="font-mono text-[11px] text-muted">
          Resume Analyzer &amp; Job Match &middot; scores are decomposed, never
          a single opaque number
        </p>
      </footer>
    </div>
  );
}
