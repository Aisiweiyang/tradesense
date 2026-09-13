import { useQuery } from "@tanstack/react-query";
import { get } from "../api/client";
import { Card, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";

interface AuditRow {
  id: number; action: string; entity_type: string; entity_id: string;
  detail: Record<string, unknown>; user: string; created_at: string;
}

export default function Audit() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["audit"],
    queryFn: () => get<{ items: AuditRow[]; total: number }>("/audit?page_size=100"),
  });
  return (
    <div>
      <PageHeader title="审计日志" desc="登录、报价批准、草稿批准、导入提交等重要操作全量留痕（敏感信息脱敏）" />
      {isLoading ? <Loading /> : error ? <ErrorState message={(error as Error).message} onRetry={refetch} /> :
        !data?.items.length ? <EmptyState icon="🛡️" text="暂无审计记录" /> : (
          <div className="card overflow-hidden">
            <table className="table-base text-xs">
              <thead><tr><th className="w-40">时间</th><th className="w-24">操作人</th><th className="w-36">动作</th><th>对象</th><th>详情</th></tr></thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <td className="text-slate-400">{new Date(r.created_at).toLocaleString("zh-CN")}</td>
                    <td>{r.user || "—"}</td>
                    <td><span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono">{r.action}</span></td>
                    <td className="text-slate-500">{r.entity_type} {r.entity_id && `#${r.entity_id}`}</td>
                    <td className="max-w-0 truncate text-slate-400">{JSON.stringify(r.detail)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-4 pb-3"><Pagination page={1} pageSize={100} total={data.total} onPage={() => {}} /></div>
          </div>
        )}
    </div>
  );
}
