import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { get } from "../api/client";
import { Badge, Card, CompletenessRing, ErrorState, KV, Loading, PageHeader } from "../components/ui";

interface Workbench {
  counts: Record<string, number>;
  workload_sizes: Record<string, number>;
  workload: {
    quoted_no_reply: { id: number; title: string; customer_name: string }[];
    long_silence: { id: number; title: string }[];
    high_intent: { id: number; title: string; completeness: number }[];
    incomplete: { id: number; title: string }[];
  };
  recent_inquiries: { id: number; title: string; status: string; completeness: number }[];
  due_tasks: { id: number; title: string; due_at: string | null; priority: string }[];
}

export default function Dashboard() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["workbench"],
    queryFn: () => get<Workbench>("/dashboard/workbench"),
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorState message={(error as Error).message} onRetry={refetch} />;
  const wb = data!;

  const cards: [string, number, string][] = [
    ["待处理询盘", wb.counts.open_inquiries, "/inquiries"],
    ["客户总数", wb.counts.customers, "/customers"],
    ["在售产品", wb.counts.products, "/products"],
    ["报价单", wb.counts.quotes, "/quotes"],
    ["待办任务", wb.counts.pending_followups, "/followups"],
  ];

  return (
    <div>
      <PageHeader title="工作台" desc="先看今天该做什么，再看客户推进到哪一步" />
      <div className="mb-5 grid grid-cols-5 gap-3">
        {cards.map(([label, value, to]) => (
          <Link key={label} to={to} className="card p-4 transition-shadow hover:shadow-md">
            <div className="text-2xl font-bold text-slate-800">{value}</div>
            <div className="mt-1 text-xs text-slate-500">{label}</div>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card title="⚠️ 需要关注" className="col-span-2">
          <div className="grid grid-cols-2 gap-3">
            <AlertRow to="/followups?scope=due" label="今日/超期待办" n={wb.workload_sizes.today_due + wb.workload_sizes.overdue} />
            <AlertRow to="/inquiries" label="报价后未回复" n={wb.workload_sizes.quoted_no_reply} />
            <AlertRow to="/inquiries" label="长期沉默" n={wb.workload_sizes.long_silence} />
            <AlertRow to="/inquiries" label="信息不完整询盘" n={wb.workload_sizes.incomplete} />
          </div>
          <div className="mt-4 border-t border-slate-100 pt-3">
            <div className="mb-2 text-xs font-medium text-slate-500">今日到期任务</div>
            {wb.due_tasks.length === 0 && <div className="text-sm text-slate-400">今天没有到期任务 🎉</div>}
            <ul className="space-y-1.5">
              {wb.due_tasks.map((t) => (
                <li key={t.id} className="flex items-center gap-2 text-sm">
                  <Badge value={t.priority} text={t.priority === "high" ? "高" : "常规"} />
                  <span className="truncate text-slate-700">{t.title}</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>

        <Card title="🔥 高意向询盘">
          {wb.workload.high_intent.length === 0 && <div className="text-sm text-slate-400">暂无</div>}
          <ul className="space-y-2">
            {wb.workload.high_intent.slice(0, 5).map((i) => (
              <li key={i.id}>
                <Link to={`/inquiries/${i.id}`} className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-slate-50">
                  <CompletenessRing score={i.completeness} />
                  <span className="line-clamp-2 text-sm text-slate-700">{i.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="最新询盘" className="col-span-2">
          {wb.recent_inquiries.length === 0 && <div className="text-sm text-slate-400">还没有询盘，去粘贴第一封吧</div>}
          <ul>
            {wb.recent_inquiries.map((i) => (
              <li key={i.id} className="border-b border-slate-50 py-2 last:border-0">
                <Link to={`/inquiries/${i.id}`} className="flex items-center gap-3 text-sm hover:text-brand-600">
                  <Badge value={i.status} />
                  <span className="flex-1 truncate text-slate-700">{i.title}</span>
                  <span className="text-xs text-slate-400">完整度 {i.completeness}%</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="📊 漏斗概览">
          <KV label="全部询盘">{wb.counts.inquiries}</KV>
          <KV label="跟进中">{wb.counts.open_inquiries}</KV>
          <KV label="已报价">{wb.workload_sizes.quoted_no_reply + wb.counts.quotes}</KV>
          <p className="mt-3 text-xs leading-5 text-slate-400">
            下一步建议：先处理「今日/超期待办」，再进入高意向询盘推进报价。
          </p>
        </Card>
      </div>
    </div>
  );
}

function AlertRow({ to, label, n }: { to: string; label: string; n: number }) {
  return (
    <Link to={to} className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50/50 px-3 py-2.5 hover:bg-slate-50">
      <span className="text-sm text-slate-600">{label}</span>
      <span className={`text-lg font-bold ${n > 0 ? "text-red-500" : "text-slate-300"}`}>{n}</span>
    </Link>
  );
}
