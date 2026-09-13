import { useQuery } from "@tanstack/react-query";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { clearToken, get, getToken } from "./api/client";
import { useI18n } from "./i18n";

interface Me {
  id: number;
  name: string;
  email: string;
}

const NAV = [
  ["/", "nav_dashboard", "🏢"],
  ["/today", "nav_today", "✅"],
  ["/inquiries", "nav_inquiries", "📩"],
  ["/customers", "nav_customers", "🤝"],
  ["/products", "nav_products", "📦"],
  ["/products/import", "nav_import", "📥"],
  ["/suppliers", "nav_suppliers", "🏭"],
  ["/quotes", "nav_quotes", "💰"],
  ["/followups", "nav_followups", "🔔"],
  ["/analytics", "nav_analytics", "📊"],
  ["/connectors", "nav_connectors", "🔌"],
  ["/sync-logs", "nav_synclogs", "🧾"],
  ["/glossary", "nav_glossary", "📖"],
  ["/audit", "nav_audit", "🛡️"],
  ["/settings", "nav_settings", "⚙️"],
] as const;

export default function Layout() {
  const { t, locale, setLocale } = useI18n();
  const location = useLocation();
  const token = getToken();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => get<Me>("/auth/me"),
    enabled: !!token,
    retry: false,
  });

  if (!token) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (me.isError) {
    clearToken();
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r border-slate-200 bg-white">
        <div className="flex h-14 items-center gap-2 border-b border-slate-100 px-4">
          <span className="text-xl">🌊</span>
          <div>
            <div className="text-sm font-bold text-slate-800">{t("appName")}</div>
            <div className="text-[10px] text-slate-400">{t("appTagline")}</div>
          </div>
        </div>
        <nav className="space-y-0.5 overflow-y-auto p-2" style={{ maxHeight: "calc(100vh - 3.5rem)" }}>
          {NAV.map(([to, key, icon]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
                  isActive ? "bg-brand-50 font-medium text-brand-600" : "text-slate-600 hover:bg-slate-50"
                }`
              }
            >
              <span>{icon}</span>
              {t(key as never)}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6">
          <div className="text-sm text-slate-400">
            {me.data ? `${me.data.name} · ${me.data.email}` : ""}
          </div>
          <div className="flex items-center gap-3">
            <select
              aria-label={t("language")}
              className="rounded-lg border border-slate-200 px-2 py-1 text-xs"
              value={locale}
              onChange={(e) => setLocale(e.target.value as never)}
            >
              <option value="zh-CN">中文</option>
              <option value="en-US">English</option>
            </select>
            <button
              className="btn-ghost"
              onClick={() => {
                clearToken();
                window.location.href = "/login";
              }}
            >
              {t("logout")}
            </button>
          </div>
        </header>
        <main className="flex-1 overflow-x-hidden p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
