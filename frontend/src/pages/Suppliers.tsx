import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";

interface Supplier {
  id: number; name: string; region: string; contact_name: string; email: string;
  reliability_score: number; notes: string; is_active: boolean;
}

export default function Suppliers() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", region: "", contact_name: "", email: "" });
  const list = useQuery({
    queryKey: ["suppliers", q],
    queryFn: () => get<{ items: Supplier[] }>(`/suppliers?q=${encodeURIComponent(q)}`),
  });
  const create = useMutation({
    mutationFn: () => post("/suppliers", { ...form, reliability_score: 0.8 }),
    onSuccess: () => { setCreating(false); setForm({ name: "", region: "", contact_name: "", email: "" }); qc.invalidateQueries({ queryKey: ["suppliers"] }); },
  });

  return (
    <div>
      <PageHeader title="供应商管理" desc="供应商可靠性参与匹配排序；同一产品可维护多个供应商比价"
        actions={<button className="btn-primary" onClick={() => setCreating(!creating)}>＋ 新建供应商</button>} />
      {creating && (
        <Card className="mb-4">
          <div className="grid grid-cols-4 gap-3">
            <input className="input" placeholder="供应商名称 *" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="input" placeholder="所在地区" value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} />
            <input className="input" placeholder="联系人" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
            <input className="input" placeholder="邮箱" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div className="mt-3 text-right">
            <button className="btn-primary" disabled={!form.name.trim() || create.isPending} onClick={() => create.mutate()}>创建</button>
          </div>
        </Card>
      )}
      <input className="input mb-3 w-64" placeholder="搜索供应商…" value={q} onChange={(e) => setQ(e.target.value)} />
      {list.isLoading ? <Loading /> : list.error ? <ErrorState message={(list.error as Error).message} onRetry={list.refetch} /> :
        !list.data?.items.length ? <EmptyState icon="🏭" text="暂无供应商" /> : (
          <div className="card overflow-hidden">
            <table className="table-base">
              <thead><tr><th>供应商</th><th>地区</th><th>联系人</th><th>可靠性</th><th>状态</th></tr></thead>
              <tbody>
                {list.data.items.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50">
                    <td className="font-medium text-slate-700">{s.name}</td>
                    <td className="text-slate-500">{s.region}</td>
                    <td className="text-xs text-slate-500">{s.contact_name} {s.email}</td>
                    <td>
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-100">
                          <div className="h-full rounded-full bg-brand-500" style={{ width: `${s.reliability_score * 100}%` }} />
                        </div>
                        <span className="text-xs text-slate-400">{(s.reliability_score * 100).toFixed(0)}</span>
                      </div>
                    </td>
                    <td>{s.is_active ? "启用" : "停用"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  );
}
