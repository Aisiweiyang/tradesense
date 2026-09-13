import { useQuery } from "@tanstack/react-query";
import { get } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";

interface SyncLogRow { id: number; account: string; level: string; event: string; detail: Record<string, unknown>; created_at: string }
interface ExtMsg { id: number; channel: string; sender: string; status: string; inquiry_id: number | null; received_at: string | null }

export default function SyncLogs() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["sync-logs"],
    queryFn: () => get<{ items: SyncLogRow[]; recent_messages: ExtMsg[]; total: number }>("/sync-logs?page_size=100"),
  });
  return (
    <div>
      <PageHeader title="同步日志" desc="连接器拉取、Webhook 推送、重复消息与失败记录全部可追溯" />
      {isLoading ? <Loading /> : error ? <ErrorState message={(error as Error).message} onRetry={refetch} /> : (
        <div className="grid grid-cols-3 gap-4">
          <Card title="同步事件" className="col-span-2">
            {!data?.items.length ? <EmptyState icon="🧾" text="暂无同步事件" /> : (
              <ul className="space-y-1.5 text-xs">
                {data.items.map((l) => (
                  <li key={l.id} className="flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2">
                    <Badge value={l.level === "error" ? "error" : l.level === "warn" ? "needs_confirmation" : "active"}
                           text={l.level} />
                    <div className="min-w-0 flex-1">
                      <div className="text-slate-600">{l.event} <span className="text-slate-400">· {l.account}</span></div>
                      <div className="truncate text-slate-400">{JSON.stringify(l.detail)}</div>
                    </div>
                    <span className="shrink-0 text-slate-300">{new Date(l.created_at).toLocaleString("zh-CN")}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="最近外部消息">
            {!data?.recent_messages.length ? <EmptyState icon="📩" text="暂无外部消息" /> : (
              <ul className="space-y-1.5 text-xs">
                {data.recent_messages.map((m) => (
                  <li key={m.id} className="rounded-lg bg-slate-50 px-3 py-2">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-600">{m.channel}</span>
                      <Badge value={m.status} text={{ processed: "已处理", duplicate: "重复", failed: "失败", pending: "待处理" }[m.status] || m.status} />
                    </div>
                    <div className="truncate text-slate-400">{m.sender}</div>
                    {m.inquiry_id && <a href={`/inquiries/${m.inquiry_id}`} className="text-brand-500">询盘 #{m.inquiry_id}</a>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
