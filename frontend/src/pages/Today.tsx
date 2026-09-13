import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";

interface Task {
  id: number;
  title: string;
  description: string;
  task_type: string;
  due_at: string | null;
  status: string;
  priority: string;
  reason_json: string;
  inquiry_id: number | null;
}

function TaskList({ title, tasks, empty }: { title: string; tasks: Task[]; empty: string }) {
  const qc = useQueryClient();
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      post(`/followups/${id}/status`, { status }),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <Card title={title}>
      {tasks.length === 0 ? (
        <EmptyState icon="🎉" text={empty} />
      ) : (
        <ul className="divide-y divide-slate-50">
          {tasks.map((t) => (
            <li key={t.id} className="flex items-start gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Badge value={t.priority} text={t.priority === "high" ? "高" : "常规"} />
                  {t.inquiry_id && (
                    <a href={`/inquiries/${t.inquiry_id}`} className="text-xs text-brand-500 hover:underline">
                      询盘 #{t.inquiry_id}
                    </a>
                  )}
                </div>
                <div className="mt-0.5 text-sm text-slate-700">{t.title}</div>
                <div className="text-xs text-slate-400">
                  {t.due_at ? `截止 ${new Date(t.due_at).toLocaleString("zh-CN")}` : "无截止时间"}
                </div>
              </div>
              <div className="flex shrink-0 gap-1.5">
                <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setStatus.mutate({ id: t.id, status: "snoozed" })}>
                  延期
                </button>
                <button className="btn-primary px-2 py-1 text-xs" onClick={() => setStatus.mutate({ id: t.id, status: "done" })}>
                  完成
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function Today() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["followups-workload"],
    queryFn: () => get<Record<string, (Task | { id: number; title: string })[]>>("/followups/workload"),
  });
  if (isLoading) return <Loading />;
  if (error) return <ErrorState message={(error as Error).message} onRetry={refetch} />;
  const wl = data!;
  const overdue = (wl.overdue || []) as Task[];
  const today = (wl.today_due || []) as Task[];

  return (
    <div>
      <PageHeader title="今日待办" desc="今天应该联系谁、发什么——先清空这里" />
      <div className="grid grid-cols-2 gap-4">
        <TaskList title={`⏰ 已超期 (${overdue.length})`} tasks={overdue} empty="没有超期任务" />
        <TaskList title={`📅 今日到期 (${today.length})`} tasks={today} empty="今天没有到期任务" />
      </div>
    </div>
  );
}
