import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { get, patch, post } from "../api/client";
import { Badge, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";

interface Product {
  id: number; sku: string; name_zh: string; name_en: string; category: string; material: string;
  spec: string; moq: number; price_tiers_json: string; currency: string; lead_time_days: number;
  certifications_json: string; is_active: boolean; data_source: string;
}

export default function Products() {
  const qc = useQueryClient();
  const [params, setParams] = useState({ page: 1, q: "", category: "", active: "" });
  const list = useQuery({
    queryKey: ["products", params],
    queryFn: () => get<{ items: Product[]; total: number; categories: string[] }>(
      `/products?page=${params.page}&page_size=15&q=${encodeURIComponent(params.q)}&category=${params.category}&active=${params.active}`,
    ),
  });
  const toggle = useMutation({
    mutationFn: ({ ids, is_active }: { ids: number[]; is_active: boolean }) => post("/products/bulk-active", { ids, is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["products"] }),
  });

  return (
    <div>
      <PageHeader title="产品管理" desc="产品资料是匹配与报价的基础，来自导入或手工维护"
        actions={<Link to="/products/import" className="btn-primary">📥 导入产品</Link>} />
      <div className="mb-3 flex flex-wrap gap-2">
        <input className="input w-64" placeholder="搜索 SKU/名称/材质…" value={params.q}
               onChange={(e) => setParams({ ...params, q: e.target.value, page: 1 })} />
        <select className="input w-40" value={params.category} onChange={(e) => setParams({ ...params, category: e.target.value, page: 1 })}>
          <option value="">全部分类</option>
          {list.data?.categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="input w-28" value={params.active} onChange={(e) => setParams({ ...params, active: e.target.value, page: 1 })}>
          <option value="">全部状态</option>
          <option value="true">启用</option>
          <option value="false">停用</option>
        </select>
        <a className="btn-ghost" href="/api/products/export?fmt=xlsx" target="_blank" rel="noreferrer">导出 Excel</a>
      </div>

      {list.isLoading ? <Loading /> : list.error ? <ErrorState message={(list.error as Error).message} onRetry={list.refetch} /> :
        !list.data?.items.length ? <EmptyState icon="📦" text="没有产品，先去导入吧" /> : (
          <div className="card overflow-hidden">
            <table className="table-base">
              <thead>
                <tr><th>SKU</th><th>产品</th><th>材质/规格</th><th>MOQ</th><th>阶梯价</th><th>交期</th><th>认证</th><th>状态</th><th className="w-20">操作</th></tr>
              </thead>
              <tbody>
                {list.data.items.map((p) => (
                  <tr key={p.id} className={`hover:bg-slate-50 ${p.is_active ? "" : "opacity-50"}`}>
                    <td className="font-mono text-xs">{p.sku}</td>
                    <td>
                      <div className="text-sm font-medium text-slate-700">{p.name_en || p.name_zh}</div>
                      <div className="text-xs text-slate-400">{p.name_zh} · {p.category}</div>
                    </td>
                    <td className="text-xs text-slate-500">{p.material} / {p.spec}</td>
                    <td>{p.moq}</td>
                    <td className="font-mono text-xs">
                      {(JSON.parse(p.price_tiers_json || "[]") as { min_qty: number; unit_price: number }[])
                        .map((t) => `${t.min_qty}+:$${t.unit_price}`).join(" ") || "—"}
                    </td>
                    <td className="whitespace-nowrap">{p.lead_time_days}天</td>
                    <td className="text-xs">{(JSON.parse(p.certifications_json || "[]") as string[]).join(", ") || "—"}</td>
                    <td className="whitespace-nowrap"><Badge value={p.is_active ? "active" : "disconnected"} text={p.is_active ? "启用" : "停用"} /></td>
                    <td>
                      <button className="text-xs text-brand-500 hover:underline"
                              onClick={() => toggle.mutate({ ids: [p.id], is_active: !p.is_active })}>
                        {p.is_active ? "停用" : "启用"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-4 pb-3">
              <Pagination page={params.page} pageSize={15} total={list.data.total} onPage={(pg) => setParams({ ...params, page: pg })} />
            </div>
          </div>
        )}
    </div>
  );
}
