import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post, patch } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";

interface Contact { id: number; name: string; email: string; is_primary: boolean }
interface Customer {
  id: number; company_name: string; country: string; stage: string; priority: string;
  source_channel: string; lead_score: number; lead_score_factors: string;
  last_contact_at: string | null; next_follow_up_at: string | null; contacts: Contact[];
}
const STAGES: Record<string, string> = {
  new: "新客户", qualified: "已确认", clarifying: "澄清中", quoted: "已报价",
  sample: "样品中", negotiating: "谈判中", won: "已成交", lost: "已失败", dormant: "休眠",
};

export default function Customers() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ company_name: "", country: "", contact_name: "", email: "" });
  const list = useQuery({
    queryKey: ["customers", q],
    queryFn: () => get<{ items: Customer[]; total: number }>(`/customers?page_size=50&q=${encodeURIComponent(q)}`),
  });
  const create = useMutation({
    mutationFn: () => post("/customers", {
      company_name: form.company_name, country: form.country,
      contacts: form.contact_name ? [{ name: form.contact_name, email: form.email, is_primary: true }] : [],
    }),
    onSuccess: () => { setCreating(false); setForm({ company_name: "", country: "", contact_name: "", email: "" }); qc.invalidateQueries({ queryKey: ["customers"] }); },
  });
  const setStage = useMutation({
    mutationFn: ({ id, stage }: { id: number; stage: string }) => patch(`/customers/${id}`, { stage }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["customers"] }),
  });

  return (
    <div>
      <PageHeader title="客户管理" desc="轻量 CRM：来源、阶段、线索评分（评分因素可见）"
        actions={<button className="btn-primary" onClick={() => setCreating(!creating)}>＋ 新建客户</button>} />
      {creating && (
        <Card className="mb-4" title="新建客户">
          <div className="grid grid-cols-4 gap-3">
            <input className="input" placeholder="公司名称 *" value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} />
            <input className="input" placeholder="国家" value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} />
            <input className="input" placeholder="联系人" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
            <input className="input" placeholder="邮箱" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div className="mt-3 text-right">
            <button className="btn-primary" disabled={!form.company_name.trim() || create.isPending} onClick={() => create.mutate()}>创建</button>
          </div>
        </Card>
      )}
      <div className="mb-3">
        <input className="input w-72" placeholder="搜索公司/国家/标签…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {list.isLoading ? <Loading /> : list.error ? <ErrorState message={(list.error as Error).message} onRetry={list.refetch} /> :
        !list.data?.items.length ? <EmptyState icon="🤝" text="还没有客户，收到询盘后会自动创建" /> : (
          <div className="card overflow-hidden">
            <table className="table-base">
              <thead><tr><th>公司</th><th>联系人</th><th>阶段</th><th>线索评分</th><th>最近联系</th><th>下次跟进</th></tr></thead>
              <tbody>
                {list.data.items.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-50">
                    <td>
                      <div className="font-medium text-slate-700">{c.company_name}</div>
                      <div className="text-xs text-slate-400">{c.country} · #{c.id}</div>
                    </td>
                    <td className="text-xs text-slate-500">
                      {c.contacts.map((ct) => <div key={ct.id}>{ct.name} {ct.email && <span className="text-slate-400">{ct.email}</span>}</div>)}
                    </td>
                    <td>
                      <select className="rounded border border-slate-200 px-1.5 py-1 text-xs" value={c.stage}
                              onChange={(e) => setStage.mutate({ id: c.id, stage: e.target.value })}>
                        {Object.entries(STAGES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    </td>
                    <td>
                      <div className="flex items-center gap-1.5">
                        <span className={`text-sm font-bold ${c.lead_score >= 60 ? "text-emerald-600" : c.lead_score >= 30 ? "text-amber-600" : "text-slate-400"}`}>{c.lead_score}</span>
                        <span className="max-w-52 truncate text-[10px] text-slate-400" title={c.lead_score_factors}>
                          ({Object.entries(JSON.parse(c.lead_score_factors || "{}")).filter(([, v]) => v).map(([k]) => k).slice(0, 3).join("、")})
                        </span>
                      </div>
                    </td>
                    <td className="text-xs text-slate-400">{c.last_contact_at ? new Date(c.last_contact_at).toLocaleDateString("zh-CN") : "—"}</td>
                    <td className="text-xs text-slate-400">{c.next_follow_up_at ? new Date(c.next_follow_up_at).toLocaleDateString("zh-CN") : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  );
}
