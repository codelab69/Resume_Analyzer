/**
 * Theme state.
 *
 * Resolution order: a stored choice wins, otherwise the operating system
 * preference. The `.dark` class is applied to <html>, which is what the token
 * overrides in index.css hang off.
 *
 * The initial class is applied synchronously in main.tsx, before React
 * renders, so the page never flashes light before switching to dark.
 */

import { create } from "zustand";

type Theme = "light" | "dark";

const STORAGE_KEY = "resume-analyzer:theme";

export function resolveInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Private browsing and some embedded webviews throw on localStorage
    // access. The system preference is a perfectly good fallback.
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}

interface ThemeState {
  theme: Theme;
  toggle: () => void;
  set: (theme: Theme) => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: resolveInitialTheme(),

  set: (theme) => {
    applyTheme(theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Not being able to remember the choice is not worth failing over.
    }
    set({ theme });
  },

  toggle: () => get().set(get().theme === "dark" ? "light" : "dark"),
}));
