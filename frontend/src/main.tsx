import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { I18nProvider } from "./i18n";
import { setToken } from "./api/client";
import "./index.css";

// Dev/demo convenience: allow #token=<jwt>[&next=<path>] on localhost only
// (used by automated screenshots); never send the token anywhere off-device.
if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
  const m = location.hash.match(/^#token=([^&]+)(?:&next=(.+))?$/);
  if (m) {
    setToken(decodeURIComponent(m[1]));
    const next = m[2] ? decodeURIComponent(m[2]) : "/";
    history.replaceState(null, "", next);
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 10_000 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  </StrictMode>,
);
