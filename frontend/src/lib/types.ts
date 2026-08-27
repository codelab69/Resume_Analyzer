/**
 * Response shapes from the backend.
 *
 * These mirror the Pydantic models in backend/app/schemas/models.py exactly,
 * including the snake_case field names. There is no translation layer on
 * purpose: one naming convention across the wire means a renamed field is a
 * TypeScript error here rather than an `undefined` that renders as blank.
 *
 * When you change a backend schema, change this file in the same commit. The
 * authoritative reference is always /docs on the running API.
 */

export type AtsStatus = "pass" | "warn" | "fail";
export type AtsBand = "excellent" | "good" | "needs_work" | "poor";
export type Verdict = "strong" | "promising" | "stretch" | "weak";
export type Severity = "critical" | "important" | "nice_to_have";
export type SemanticBackend = "transformer" | "hashing";

export interface SkillSpan {
  name: string;
  category: string;
  /** Character offset into `ResumeReport.text`, inclusive. */
  start: number;
  /** Character offset into `ResumeReport.text`, exclusive. */
  end: number;
  surface: string;
  method: "exact" | "fuzzy";
}

export interface Contact {
  name: string | null;
  email: string | null;
  phone: string | null;
  linkedin: string | null;
  github: string | null;
  portfolio: string | null;
}

export interface Education {
  degrees: string[];
  highest_degree: string | null;
  institutions: string[];
  cgpa: number | null;
  percentage: number | null;
}

export interface Profile {
  contact: Contact;
  education: Education;
  experience_months: number;
  experience_years: number;
  date_ranges: string[];
}

export interface AtsRule {
  id: string;
  title: string;
  points: number;
  earned: number;
  status: AtsStatus;
  detail: string;
  fix: string;
}

export interface Ats {
  score: number;
  band: AtsBand;
  rules: AtsRule[];
  top_fixes: string[];
}

export interface Role {
  role: string;
  confidence: number;
  backend: "trained" | "profile";
  is_confident: boolean;
  summary: string;
  alternatives: { role: string; confidence: number }[];
}

export interface ResumeReport {
  id: string;
  filename: string;
  created_at: string | null;
  /** Skill offsets index into this string. Never re-normalise it. */
  text: string;
  page_count: number;
  file_type: string;
  reader: string;
  profile: Profile;
  skills: SkillSpan[];
  skills_by_category: Record<string, string[]>;
  skill_names: string[];
  role: Role;
  ats: Ats;
  sections: string[];
  warnings: string[];
  timings_ms: Record<string, number>;
}

export interface ResumeSummary {
  id: string;
  filename: string;
  ats_score: number;
  role: string | null;
  skill_count: number;
  created_at: string;
}

export interface SubScores {
  semantic: number;
  skill: number;
  lexical: number;
  fit: number;
}

export interface SkillGap {
  name: string;
  category: string;
  weight: number;
  severity: Severity;
}

export interface MatchResponse {
  id: string | null;
  resume_id: string;
  score: number;
  verdict: Verdict;
  sub_scores: SubScores;
  weights: Record<string, number>;
  matched_skills: string[];
  missing_skills: SkillGap[];
  extra_skills: string[];
  jd_skill_count: number;
  semantic_backend: SemanticBackend;
  notes: string[];
}

export interface MatchSummary {
  id: string;
  job_title: string | null;
  score: number;
  created_at: string;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  category: string;
  employment_type: string;
  experience_years: number;
  description: string;
  requirements: string[];
  url: string | null;
  score: number;
  matching_skills: string[];
  missing_skills: string[];
  why: string;
}

export interface JobFilters {
  locations: string[];
  categories: string[];
  total_jobs: number;
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  components: Record<string, string>;
  semantic_backend: string;
  notes: string[];
}

export interface Stats {
  resume_count: number;
  average_ats_score: number;
  best_ats_score: number;
  match_count: number;
  average_match_score: number;
  by_role: { role: string; count: number; average_ats: number }[];
}
