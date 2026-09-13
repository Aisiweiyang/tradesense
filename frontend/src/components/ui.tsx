import type { ReactNode } from "react";

export function PageHeader({ title, desc, actions }: { title: string; desc?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-bold text-slate-800">{title}</h1>
        {desc && <p className="mt-1 text-sm text-slate-500">{desc}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, extra, children, className = "" }: {
  title?: ReactNode; extra?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <div className={`card ${className}`}>
      {(title || extra) && (
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
          <div className="text-sm font-semibold text-slate-700">{title}</div>
          <div>{extra}</div>
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

const BADGE_COLORS: Record<string, string> = {
  open: "bg-blue-50 text-blue-600", clarifying: "bg-amber-50 text-amber-600",
  quoted: "bg-violet-50 text-violet-600", won: "bg-emerald-50 text-emerald-600",
  lost: "bg-slate-100 text-slate-500", dormant: "bg-slate-100 text-slate-500",
  active: "bg-emerald-50 text-emerald-700", unknown: "bg-slate-100 text-slate-400",
  replaced: "bg-slate-100 text-slate-400", unconstrained: "bg-sky-50 text-sky-600",
  conflicting: "bg-red-50 text-red-600", needs_confirmation: "bg-amber-50 text-amber-700",
  draft: "bg-slate-100 text-slate-600", pending_approval: "bg-amber-50 text-amber-700",
  approved: "bg-emerald-50 text-emerald-700", rejected: "bg-red-50 text-red-600",
  superseded: "bg-slate-100 text-slate-400",
  pending: "bg-amber-50 text-amber-700", done: "bg-emerald-50 text-emerald-700",
  snoozed: "bg-sky-50 text-sky-600", cancelled: "bg-slate-100 text-slate-400",
  simulated: "bg-amber-50 text-amber-700", live: "bg-emerald-50 text-emerald-700",
  error: "bg-red-50 text-red-600", disconnected: "bg-slate-100 text-slate-500",
  connected: "bg-emerald-50 text-emerald-700", processed: "bg-emerald-50 text-emerald-700",
  duplicate: "bg-amber-50 text-amber-700", failed: "bg-red-50 text-red-600",
  normal: "bg-slate-100 text-slate-500", low_quality: "bg-amber-50 text-amber-700",
  suspected_fraud: "bg-red-50 text-red-600", high: "bg-red-50 text-red-600",
};

export function Badge({ value, text }: { value: string; text?: string }) {
  const color = BADGE_COLORS[value] || "bg-slate-100 text-slate-600";
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {text || value}
    </span>
  );
}

export function CompletenessRing({ score }: { score: number }) {
  const color = score >= 70 ? "#10b981" : score >= 40 ? "#f59e0b" : "#ef4444";
  const angle = Math.round(score * 3.6);
  return (
    <div
      className="relative flex h-16 w-16 items-center justify-center rounded-full"
      style={{ background: `conic-gradient(${color} ${angle}deg, #e2e8f0 0deg)` }}
      title={`完整度 ${score}%`}
      role="meter"
      aria-valuenow={score}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-sm font-bold text-slate-700">
        {score}%
      </div>
    </div>
  );
}

export function Loading({ text = "加载中…" }: { text?: string }) {
  return (
    <div className="flex items-center justify-center py-16 text-sm text-slate-400" data-testid="loading">
      <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-500" />
      {text}
    </div>
  );
}

export function EmptyState({ icon = "📭", text = "暂无数据", action }: { icon?: string; text?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center" data-testid="empty">
      <div className="text-3xl">{icon}</div>
      <div className="mt-2 text-sm text-slate-400">{text}</div>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center" data-testid="error-state">
      <div className="text-3xl">⚠️</div>
      <div className="mt-2 text-sm text-red-500">{message}</div>
      {onRetry && (
        <button className="btn-ghost mt-3" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: {
  page: number; pageSize: number; total: number; onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  return (
    <div className="mt-3 flex items-center justify-end gap-2 text-sm text-slate-500">
      <span>共 {total} 条</span>
      <button className="btn-ghost px-2 py-1" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        上一页
      </button>
      <span>
        {page} / {pages}
      </span>
      <button className="btn-ghost px-2 py-1" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        下一页
      </button>
    </div>
  );
}

export function KV({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="py-1 text-sm">
      <span className="mr-2 inline-block w-24 shrink-0 text-slate-400">{label}</span>
      <span className="text-slate-700">{children || "—"}</span>
    </div>
  );
}
