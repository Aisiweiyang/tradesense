import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";

interface Quote {
  id: number; inquiry_id: number; product_id: number | null; version: number; status: string;
  incoterm: string; currency: string; quantity: number; unit_cost: number; unit_price: number;
  customer_price: number; total_amount: number; is_formal: boolean; valid_until: string | null;
  notes: string;
}
const STATUS_LABEL: Record<string, string> = {
  draft: "草稿", pending_approval: "待审批", approved: "已批准",
  rejected: "已拒绝", superseded: "已替代",
};

export default function Quotes() {
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["quotes-all", page],
    queryFn: () => get<{ items: Quote[]; total: number }>(`/quotes?page=${page}&page_size=${pageSize}`),
  });
  return (
    <div>
      <PageHeader title="报价记录" desc="内部成本永远不会展示给客户；只有批准过的版本才算正式报价" />
      {isLoading ? <Loading /> : error ? <ErrorState message={(error as Error).message} onRetry={refetch} /> :
        !data?.items.length ? (
          <EmptyState icon="💰" text="还没有报价，去询盘详情页创建" />
        ) : (
          <div className="card overflow-hidden">
            <table className="table-base">
              <thead>
                <tr><th>版本</th><th>询盘</th><th>数量</th><th>术语</th><th>内部成本</th><th>建议价</th><th>客户价</th><th>合计</th><th>状态</th><th>有效期</th></tr>
              </thead>
              <tbody>
                {data.items.map((q) => {
                  const vu = q.valid_until ? new Date(q.valid_until) : null;
                  const expired = vu != null && !["superseded", "rejected"].includes(q.status)
                    && vu.setHours(23, 59, 59, 999) < Date.now();  // "有效至"含当天，次日零点起算过期
                  return (
                  <tr key={q.id} className="hover:bg-slate-50">
                    <td className="text-xs">v{q.version}</td>
                    <td><a className="text-brand-600 hover:underline" href={`/inquiries/${q.inquiry_id}`}>#{q.inquiry_id}</a></td>
                    <td>{q.quantity}</td>
                    <td>{q.incoterm}</td>
                    <td className="font-mono text-xs text-slate-400">{q.currency} {q.unit_cost.toFixed(3)}</td>
                    <td className="font-mono">{q.currency} {q.unit_price.toFixed(2)}</td>
                    <td className="font-mono">{q.currency} {q.customer_price.toFixed(2)}</td>
                    <td className="font-mono">{q.currency} {q.total_amount.toFixed(2)}</td>
                    <td><Badge value={q.status} text={STATUS_LABEL[q.status] || q.status} /></td>
                    <td className="text-xs">
                      {vu ? vu.toLocaleDateString("zh-CN") : "—"}
                      {expired && <span className="ml-1 rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-600">已过期</span>}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="px-4 pb-3"><Pagination page={page} pageSize={pageSize} total={data.total} onPage={setPage} /></div>
          </div>
        )}
    </div>
  );
}
