import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";

interface Task {
  id: number; title: string; inquiry_id: number | null; customer_id: number | null;
  task_type: string; due_at: string | null; status: string; priority: string; reason_json: string;
}

export default function Followups() {
  const qc = useQueryClient();
  const [status, setStatusFilter] = useState("pending");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["followups", status],
    queryFn: () => get<{ items: Task[]; total: number }>(`/followups?status=${status}&page_size=100&sort=due_at`),
  });
  const act = useMutation({
    mutationFn: ({ id, st }: { id: number; st: string }) => post(`/followups/${id}/status`, { status: st }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["followups"] }),
  });

  return (
    <div>
      <PageHeader title="跟进任务" desc="每条任务都有来源与原因，可完成、延期或取消" />
      <div className="mb-3 flex gap-2">
        {[["pending", "待办"], ["done", "已完成"], ["snoozed", "已延期"], ["cancelled", "已取消"]].map(([v, l]) => (
          <button key={v} className={`rounded-lg px-3 py-1.5 text-sm ${status === v ? "bg-brand-500 text-white" : "bg-white text-slate-500 border border-slate-200"}`}
                  onClick={() => setStatusFilter(v)}>{l}</button>
        ))}
      </div>
      {isLoading ? <Loading /> : error ? <ErrorState message={(error as Error).message} onRetry={refetch} /> :
        !data?.items.length ? <EmptyState icon="🔔" text="没有任务" /> : (
          <Card>
            <ul className="divide-y divide-slate-50">
              {data.items.map((t) => {
                const overdue = t.status === "pending" && t.due_at && new Date(t.due_at) < new Date();
                return (
                  <li key={t.id} className="flex items-start gap-3 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Badge value={t.priority} text={t.priority === "high" ? "高优先" : "常规"} />
                        {overdue && <Badge value="error" text="已超期" />}
                        <span className="text-[10px] text-slate-400">{t.task_type}</span>
                      </div>
                      <div className="mt-1 text-sm text-slate-700">{t.title}</div>
                      <div className="mt-0.5 text-xs text-slate-400">
                        {t.inquiry_id && <a href={`/inquiries/${t.inquiry_id}`} className="text-brand-500 hover:underline">询盘 #{t.inquiry_id}</a>}
                        {t.due_at && ` · 截止 ${new Date(t.due_at).toLocaleString("zh-CN")}`}
                      </div>
                      <div className="mt-1 text-[10px] text-slate-400">
                        {(() => { try { return JSON.parse(t.reason_json)?.reason || ""; } catch { return ""; } })()}
                      </div>
                    </div>
                    {t.status === "pending" && (
                      <div className="flex shrink-0 gap-1.5">
                        <button className="btn-ghost px-2 py-1 text-xs" onClick={() => act.mutate({ id: t.id, st: "snoozed" })}>延期</button>
                        <button className="btn-ghost px-2 py-1 text-xs" onClick={() => act.mutate({ id: t.id, st: "cancelled" })}>取消</button>
                        <button className="btn-primary px-2 py-1 text-xs" onClick={() => act.mutate({ id: t.id, st: "done" })}>完成</button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
    </div>
  );
}
