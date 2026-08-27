/**
 * History and cohort dashboard.
 *
 * Two audiences on one screen. A student sees their own analyses and whether
 * their score is moving. A placement officer sees the cohort: how many
 * resumes have been analysed, the average readiness score, and which role
 * families the batch is clustering into.
 *
 * The chart is a bar chart rather than a line because the analyses are
 * discrete uploads, not a time series - a line implies a continuous trend
 * between two points that does not exist.
 */

import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { deleteResume, getStats, listResumes } from "@/lib/api";
import { formatDate, scoreColor } from "@/lib/format";
import { EmptyState, SectionHeader, Spinner, Stat } from "@/components/ui";
import { useResumeStore } from "@/store/resume";

export function DashboardScreen() {
  const queryClient = useQueryClient();
  const { resumeId, setResumeId } = useResumeStore();

  const resumes = useQuery({ queryKey: ["resumes"], queryFn: () => listResumes(50) });
  const stats = useQuery({ queryKey: ["stats"], queryFn: getStats });

  const remove = useMutation({
    mutationFn: deleteResume,
    onSuccess: (_data, deletedId) => {
      // Clearing the active resume matters: leaving it pointing at a deleted
      // row would put dead links in the navigation.
      if (deletedId === resumeId) setResumeId(null);
      void queryClient.invalidateQueries({ queryKey: ["resumes"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  if (resumes.isLoading) return <Spinner label="Loading history" />;

  const rows = resumes.data ?? [];

  if (rows.length === 0) {
    return (
      <EmptyState
        title="No analyses yet"
        body="Upload a resume and it will appear here with its score, so you can watch the number move as you edit."
        action={
          <Link
            to="/upload"
            className="bg-ink px-5 py-2.5 text-sm font-semibold text-paper transition-opacity hover:opacity-85"
          >
            Analyse a resume
          </Link>
        }
      />
    );
  }

  // Oldest first so the chart reads left to right as time passing.
  const chartData = [...rows]
    .reverse()
    .map((row, index) => ({
      name: `#${index + 1}`,
      score: row.ats_score,
      filename: row.filename,
    }));

  return (
    <div className="py-2">
      <h1 className="font-display text-3xl font-extrabold">History</h1>
      <p className="mt-2 max-w-[62ch] text-[15px] text-ink-soft">
        Every analysis stored on this server, newest first.
      </p>

      {/* --- cohort tiles ------------------------------------------------- */}
      {stats.data && (
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Resumes analysed" value={stats.data.resume_count} />
          <Stat
            label="Average readiness"
            value={stats.data.average_ats_score}
            hint={`Best so far: ${stats.data.best_ats_score}`}
          />
          <Stat label="Job matches run" value={stats.data.match_count} />
          <Stat
            label="Average match"
            value={stats.data.average_match_score}
            hint="Across every saved match"
          />
        </div>
      )}

      {/* --- chart --------------------------------------------------------- */}
      <section className="mt-8">
        <SectionHeader
          eyebrow="Readiness score per upload, oldest first"
          title="Score over time"
        />
        <div className="card p-4" style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 4, left: -18 }}>
              <CartesianGrid
                strokeDasharray="2 4"
                stroke="var(--color-rule)"
                vertical={false}
              />
              <XAxis
                dataKey="name"
                stroke="var(--color-muted)"
                tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--color-rule)" }}
              />
              <YAxis
                domain={[0, 100]}
                stroke="var(--color-muted)"
                tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                cursor={{ fill: "var(--color-surface-2)" }}
                contentStyle={{
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-rule-strong)",
                  borderRadius: 2,
                  fontSize: 12,
                }}
                // Recharts types the formatter value as a union, so it is
                // narrowed here rather than asserted - a non-numeric value
                // would otherwise render as "[object Object]/100".
                formatter={(value) => [
                  `${typeof value === "number" ? value : 0}/100`,
                  "Readiness",
                ]}
                labelFormatter={(_label, payload) =>
                  (payload?.[0]?.payload as { filename?: string })?.filename ?? ""
                }
              />
              <Bar dataKey="score" radius={[1, 1, 0, 0]}>
                {/* Coloured per bar so a low score is visibly low, not just
                    shorter than its neighbours. */}
                {chartData.map((entry) => (
                  <Cell key={entry.name} fill={scoreColor(entry.score)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* --- by role -------------------------------------------------------- */}
      {stats.data && stats.data.by_role.length > 0 && (
        <section className="mt-8">
          <SectionHeader eyebrow="Cohort view" title="Predicted role families" />
          <ul className="flex flex-wrap gap-2">
            {stats.data.by_role.map((entry) => (
              <li key={entry.role} className="card px-3 py-2">
                <span className="text-sm font-medium">{entry.role}</span>
                <span className="ml-2 font-mono text-[11px] text-muted tabular-nums">
                  {entry.count} &middot; avg {entry.average_ats}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* --- table ---------------------------------------------------------- */}
      <section className="mt-8">
        <SectionHeader eyebrow={`${rows.length} stored`} title="All analyses" />
        <div className="overflow-x-auto border border-rule">
          <table className="w-full min-w-[620px] text-sm">
            <thead>
              <tr className="bg-surface-2">
                {["File", "Role", "Skills", "Readiness", "Analysed", ""].map((head) => (
                  <th
                    key={head}
                    className="label px-3 py-2 text-left font-bold"
                    scope="col"
                  >
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className="bg-surface transition-colors hover:bg-surface-2"
                >
                  <td className="max-w-[220px] truncate px-3 py-2">
                    <Link
                      to={`/report/${row.id}`}
                      onClick={() => setResumeId(row.id)}
                      className="underline-offset-4 hover:underline"
                    >
                      {row.filename}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-muted">{row.role ?? "—"}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">
                    {row.skill_count}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className="font-display font-bold tabular-nums"
                      style={{ color: scoreColor(row.ats_score) }}
                    >
                      {row.ats_score}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-muted">
                    {formatDate(row.created_at)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => remove.mutate(row.id)}
                      disabled={remove.isPending}
                      className="font-mono text-[11px] text-muted underline-offset-4 hover:underline disabled:opacity-40"
                      style={{ color: "var(--color-bad)" }}
                    >
                      DELETE
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
