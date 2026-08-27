/**
 * Typed wrappers around every backend endpoint.
 *
 * Every network call in the app goes through this file. Components never call
 * fetch directly, which means error handling, the base URL and the response
 * contract each live in exactly one place.
 *
 * ERROR HANDLING
 * --------------
 * The backend returns `{ detail: { detail, code } }` for every 4xx and 5xx.
 * `request()` unwraps that into an ApiError carrying a message written for the
 * user and a stable code the UI can branch on. Components catch ApiError and
 * render `error.message` directly - it is already human-readable, so there is
 * never a reason to replace it with "Something went wrong".
 */

import type {
  Health,
  Job,
  JobFilters,
  MatchResponse,
  MatchSummary,
  ResumeReport,
  ResumeSummary,
  Stats,
} from "./types";

/**
 * Empty in development: vite.config.ts proxies /api to the backend, so the
 * browser sees a single origin and there is no CORS preflight. In production
 * this is set to the deployed API's origin at build time.
 */
const BASE = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }

  /** True when retrying might work: server errors and network failures. */
  get isRetryable(): boolean {
    return this.status === 0 || this.status >= 500;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        // Only set a JSON content type when there is a JSON body. Setting it
        // on a FormData request breaks the multipart boundary the browser
        // would otherwise generate.
        ...(init?.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    });
  } catch {
    // fetch only rejects on a network-level failure - the server being down,
    // DNS failing, or the request being blocked. An HTTP error status is a
    // resolved promise, handled below.
    throw new ApiError(
      "Could not reach the server. Check that the backend is running on port 8000.",
      "network_error",
      0,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = body?.detail;

    // FastAPI's own validation errors (422) arrive as an array of issues
    // rather than our {detail, code} object, so they need their own branch.
    if (Array.isArray(detail)) {
      const first = detail[0];
      throw new ApiError(
        first?.msg ?? "That request was not valid.",
        "validation_error",
        response.status,
      );
    }

    if (detail && typeof detail === "object") {
      throw new ApiError(detail.detail, detail.code, response.status);
    }

    throw new ApiError(
      typeof detail === "string" ? detail : "The server returned an error.",
      "unknown_error",
      response.status,
    );
  }

  return body as T;
}

// ---------------------------------------------------------------------------
// Resume
// ---------------------------------------------------------------------------

export function uploadResume(file: File): Promise<ResumeReport> {
  const form = new FormData();
  form.append("file", file);
  return request<ResumeReport>("/api/resume/upload", {
    method: "POST",
    body: form,
  });
}

export function getResume(id: string): Promise<ResumeReport> {
  return request<ResumeReport>(`/api/resume/${id}`);
}

export function listResumes(limit = 50): Promise<ResumeSummary[]> {
  return request<ResumeSummary[]>(`/api/resume?limit=${limit}`);
}

export function deleteResume(id: string): Promise<void> {
  return request<void>(`/api/resume/${id}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Match
// ---------------------------------------------------------------------------

export function createMatch(input: {
  resumeId: string;
  jobDescription: string;
  jobTitle?: string;
  save?: boolean;
}): Promise<MatchResponse> {
  return request<MatchResponse>("/api/match", {
    method: "POST",
    body: JSON.stringify({
      resume_id: input.resumeId,
      job_description: input.jobDescription,
      job_title: input.jobTitle ?? null,
      save: input.save ?? true,
    }),
  });
}

export function getMatchHistory(resumeId: string): Promise<MatchSummary[]> {
  return request<MatchSummary[]>(`/api/match/history/${resumeId}`);
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export function recommendJobs(
  resumeId: string,
  options: {
    limit?: number;
    location?: string;
    category?: string;
    maxExperienceYears?: number;
  } = {},
): Promise<Job[]> {
  const query = new URLSearchParams();
  query.set("limit", String(options.limit ?? 10));
  if (options.location) query.set("location", options.location);
  if (options.category) query.set("category", options.category);
  if (options.maxExperienceYears !== undefined) {
    query.set("max_experience_years", String(options.maxExperienceYears));
  }
  return request<Job[]>(`/api/jobs/recommend/${resumeId}?${query}`);
}

export function getJobFilters(): Promise<JobFilters> {
  return request<JobFilters>("/api/jobs/filters");
}

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------

export function getHealth(): Promise<Health> {
  return request<Health>("/api/health");
}

export function getStats(): Promise<Stats> {
  return request<Stats>("/api/stats");
}
