import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { App } from "./App";
import { applyTheme, resolveInitialTheme } from "./store/theme";
import "./index.css";

// Applied before the first paint. Doing this inside a React effect would let
// the page render light for one frame and then flip, which is very visible on
// a dark-theme machine.
applyTheme(resolveInitialTheme());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Analyses are immutable once created, so refetching them on every tab
      // focus is pure noise. A minute is long enough to stop that and short
      // enough that the history list stays current.
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      // A 404 will never succeed on retry; only server and network failures
      // are worth a second attempt.
      retry: (failureCount, error) => {
        const status = (error as { status?: number })?.status ?? 0;
        if (status >= 400 && status < 500) return false;
        return failureCount < 2;
      },
    },
  },
});

const container = document.getElementById("root");
if (!container) {
  throw new Error("No #root element - check index.html");
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
