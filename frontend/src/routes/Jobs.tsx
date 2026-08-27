/**
 * Job recommendations screen.
 *
 * Filters live in the URL query rather than component state, so a filtered
 * list can be bookmarked and shared - which is how a placement officer sends
 * a student "the Chennai backend roles you match".
 */

import { useSearchParams, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getJobFilters, recommendJobs } from "@/lib/api";
import { JobCard } from "@/components/JobCard";
import { EmptyState, ErrorBanner, SectionHeader, Spinner } from "@/components/ui";

export function JobsScreen() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();

  const location = params.get("location") ?? "";
  const category = params.get("category") ?? "";
  const level = params.get("level") ?? "";

  const filters = useQuery({ queryKey: ["job-filters"], queryFn: getJobFilters });

  const jobs = useQuery({
    queryKey: ["jobs", id, location, category, level],
    queryFn: () =>
      recommendJobs(id, {
        limit: 12,
        location: location || undefined,
        category: category || undefined,
        maxExperienceYears: level ? Number(level) : undefined,
      }),
    enabled: Boolean(id),
  });

  /** Update one filter, dropping it from the URL when cleared. */
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const activeCount = [location, category, level].filter(Boolean).length;

  return (
    <div className="py-2">
      <p className="label mb-1">Step 3 of 3</p>
      <h1 className="font-display text-3xl font-extrabold">Openings for you</h1>
      <p className="mt-2 max-w-[62ch] text-[15px] text-ink-soft">
        Ranked by a two-stage search: a keyword pass over every posting, then a
        similarity pass over the strongest few. Each card says why it surfaced.
      </p>

      {/* --- filters ------------------------------------------------------ */}
      <div className="mt-6 flex flex-wrap items-end gap-3 border-y border-rule py-3">
        <label className="flex flex-col gap-1">
          <span className="label">Location</span>
          <select
            value={location}
            onChange={(event) => setFilter("location", event.target.value)}
            className="border border-rule bg-surface px-2.5 py-1.5 text-sm outline-none"
          >
            <option value="">Anywhere</option>
            {filters.data?.locations.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="label">Role family</span>
          <select
            value={category}
            onChange={(event) => setFilter("category", event.target.value)}
            className="border border-rule bg-surface px-2.5 py-1.5 text-sm outline-none"
          >
            <option value="">All roles</option>
            {filters.data?.categories.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="label">Experience asked for</span>
          <select
            value={level}
            onChange={(event) => setFilter("level", event.target.value)}
            className="border border-rule bg-surface px-2.5 py-1.5 text-sm outline-none"
          >
            <option value="">Any level</option>
            <option value="0">Freshers only</option>
            <option value="1">Up to 1 year</option>
            <option value="2">Up to 2 years</option>
            <option value="3">Up to 3 years</option>
          </select>
        </label>

        {activeCount > 0 && (
          <button
            type="button"
            onClick={() => setParams(new URLSearchParams(), { replace: true })}
            className="ml-auto font-mono text-[11px] text-muted underline-offset-4 hover:underline"
          >
            CLEAR {activeCount} FILTER{activeCount > 1 ? "S" : ""}
          </button>
        )}
      </div>

      {/* --- results ------------------------------------------------------ */}
      <div className="mt-6">
        {jobs.isLoading && <Spinner label="Ranking openings" />}

        {jobs.error && (
          <ErrorBanner
            message={
              jobs.error instanceof Error
                ? jobs.error.message
                : "Openings could not be loaded."
            }
            onRetry={() => void jobs.refetch()}
          />
        )}

        {jobs.data && jobs.data.length === 0 && (
          <EmptyState
            title="Nothing matches those filters"
            body="No posting in the corpus fits every filter at once. Clearing the location filter usually opens things up the most."
            action={
              <button
                type="button"
                onClick={() => setParams(new URLSearchParams(), { replace: true })}
                className="border border-rule-strong px-4 py-2 text-sm transition-colors hover:bg-surface-2"
              >
                Clear filters
              </button>
            }
          />
        )}

        {jobs.data && jobs.data.length > 0 && (
          <>
            <SectionHeader
              eyebrow={`${jobs.data.length} of ${filters.data?.total_jobs ?? "?"} postings`}
              title="Best matches first"
            />
            <div className="flex flex-col gap-3">
              {jobs.data.map((job, index) => (
                <JobCard key={job.id} job={job} index={index} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
