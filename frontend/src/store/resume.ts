/**
 * Which resume the app is currently working on.
 *
 * Only the id lives here. The report itself is server state and belongs to
 * TanStack Query, which already handles caching, refetching and staleness -
 * copying it into a store as well would create a second source of truth that
 * can silently go out of date.
 *
 * The id is persisted to localStorage so a refresh, or coming back to the tab
 * later, does not lose the analysis and force a re-upload.
 */

import { create } from "zustand";

const STORAGE_KEY = "resume-analyzer:current";

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

interface ResumeState {
  resumeId: string | null;
  setResumeId: (id: string | null) => void;
}

export const useResumeStore = create<ResumeState>((set) => ({
  resumeId: readStored(),

  setResumeId: (id) => {
    try {
      if (id) localStorage.setItem(STORAGE_KEY, id);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Session-only is an acceptable degradation.
    }
    set({ resumeId: id });
  },
}));
