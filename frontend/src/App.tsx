/**
 * Routes.
 *
 * Three of the five screens are scoped to one resume and take its id in the
 * path. That is deliberate rather than reading the id from a store: a report
 * URL can then be bookmarked, refreshed and pasted to someone else, which
 * matters when a student wants to show a lecturer what the tool said.
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "@/components/Layout";
import { DashboardScreen } from "@/routes/Dashboard";
import { JobsScreen } from "@/routes/Jobs";
import { LandingScreen } from "@/routes/Landing";
import { MatchScreen } from "@/routes/Match";
import { ReportScreen } from "@/routes/Report";
import { UploadScreen } from "@/routes/Upload";

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<LandingScreen />} />
        <Route path="/upload" element={<UploadScreen />} />
        <Route path="/report/:id" element={<ReportScreen />} />
        <Route path="/match/:id" element={<MatchScreen />} />
        <Route path="/jobs/:id" element={<JobsScreen />} />
        <Route path="/dashboard" element={<DashboardScreen />} />

        {/* A scoped route reached without an id has no resume to show, so
            send the user to the one screen that can produce one. */}
        <Route path="/report" element={<Navigate to="/upload" replace />} />
        <Route path="/match" element={<Navigate to="/upload" replace />} />
        <Route path="/jobs" element={<Navigate to="/upload" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
