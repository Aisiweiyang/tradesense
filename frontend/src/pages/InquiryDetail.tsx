import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { del, get, post, patch } from "../api/client";
import { Badge, Card, CompletenessRing, EmptyState, ErrorState, KV, Loading } from "../components/ui";

const FIELD_LABELS: Record<string, string> = {
  product: "产品", material: "材质", color: "颜色", spec: "规格", quantity: "数量",
  target_price: "目标价", destination_country: "目的国", destination_port: "目的港",
  incoterm: "贸易术语", packaging: "包装", customization: "定制", certification: "认证",
  lead_time: "交期", payment_terms: "付款", sample: "样品", shipping_method: "运输",
  notes: "备注",
};
const STATUS_TEXT: Record<string, string> = {
  active: "已确认", unknown: "未知", replaced: "旧值", unconstrained: "无要求",
  conflicting: "矛盾", needs_confirmation: "待确认",
};

interface ReqView {
  completeness: { score: number; confirmed: string[]; missing: string[]; conflicting: string[] };
  fields: Record<string, { value: string; normalized: string; status: string; raw: string; unit: string; locked: boolean; confirmed: boolean; confidence: number; source_message_id: number | null }>;
  cannot_quote_reasons: string[];
}

const TABS = [
  ["overview", "📋 概览"], ["messages", "💬 对话"], ["requirement", "🧩 需求"],
  ["clarify", "❓ 追问"], ["match", "🎯 匹配"], ["quotes", "💰 报价"],
  ["replies", "✉️ 回复"], ["followups", "🔔 跟进"],
] as const;

export default function InquiryDetail() {
  const { id } = useParams();
  const iid = Number(id);
  const [tab, setTab] = useState<string>("overview");
  const qc = useQueryClient();
  const inquiry = useQuery({
    queryKey: ["inquiry", iid],
    queryFn: () => get<Record<string, never>>(`/inquiries/${iid}`),
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["inquiry", iid] });
    qc.invalidateQueries({ queryKey: ["req", iid] });
  };

  if (inquiry.isLoading) return <Loading />;
  if (inquiry.error) return <ErrorState message={(inquiry.error as Error).message} onRetry={inquiry.refetch} />;
  const inq = inquiry.data as unknown as {
    id: number; title: string; status: string; raw_text: string; language: string;
    completeness: number; quality_flag: string; source_channel: string;
    customer: { company_name: string; country: string } | null;
  };

  return (
    <div>
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-xl font-bold text-slate-800">#{inq.id} {inq.title}</h1>
            <Badge value={inq.status} />
            {inq.quality_flag !== "normal" && <Badge value={inq.quality_flag} text={inq.quality_flag === "low_quality" ? "低质量" : "疑似欺诈"} />}
          </div>
          <div className="mt-1 text-sm text-slate-500">
            {inq.customer ? `${inq.customer.company_name} · ${inq.customer.country}` : "未关联客户"} · 渠道 {inq.source_channel}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <CompletenessRing score={inq.completeness} />
        </div>
      </div>

      <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)}
                  className={`whitespace-nowrap border-b-2 px-4 py-2 text-sm ${tab === key ? "border-brand-500 font-medium text-brand-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" && <Overview iid={iid} />}
      {tab === "messages" && <Messages iid={iid} rawText={inq.raw_text} onChanged={refresh} />}
      {tab === "requirement" && <Requirement iid={iid} />}
      {tab === "clarify" && <Clarify iid={iid} />}
      {tab === "match" && <Match iid={iid} />}
      {tab === "quotes" && <QuotesTab iid={iid} />}
      {tab === "replies" && <Replies iid={iid} />}
      {tab === "followups" && <FollowupsTab iid={iid} />}
    </div>
  );
}

// ------------------------------------------------------------- 概览
function Overview({ iid }: { iid: number }) {
  // all hooks must run before any early return (rules of hooks)
  const reqQ = useQuery({
    queryKey: ["req", iid],
    queryFn: () => get<ReqView>(`/inquiries/${iid}/requirement`),
  });
  const summaryQ = useQuery({
    queryKey: ["inquiry", iid],
    queryFn: () => get<{ summary_json: string }>(`/inquiries/${iid}`),
  });

  if (reqQ.isLoading || summaryQ.isLoading) return <Loading />;
  if (reqQ.error) return <ErrorState message={(reqQ.error as Error).message} onRetry={reqQ.refetch} />;
  const req = reqQ.data!;
  let s: Record<string, unknown> = {};
  if (summaryQ.data?.summary_json) {
    try { s = JSON.parse(summaryQ.data.summary_json); } catch { /* ignore */ }
  }

  return (
    <div className="grid grid-cols-3 gap-4">
      <Card title="📋 询盘中文摘要" className="col-span-2">
        <KV label="客户要什么">{s.what as string}</KV>
        <KV label="数量">{s.quantity as string}</KV>
        <KV label="目的国/港口">{s.destination as string}</KV>
        <KV label="目标价格">{s.target_price as string}</KV>
        <KV label="贸易术语">{s.incoterm as string}</KV>
        <KV label="定制要求">{s.customization as string}</KV>
        <KV label="认证要求">{s.certification as string}</KV>
        <KV label="交期">{s.lead_time as string}</KV>
      </Card>
      <div className="space-y-4">
        <Card title="✅ 完整度">
          <div className="flex items-center gap-3">
            <CompletenessRing score={req.completeness.score} />
            <div className="text-xs leading-5 text-slate-500">
              <div>已确认：{req.completeness.confirmed.map((f) => FIELD_LABELS[f]).join("、") || "—"}</div>
              <div className="text-amber-600">待确认：{req.completeness.missing.map((f) => FIELD_LABELS[f]).join("、") || "—"}</div>
            </div>
          </div>
        </Card>
        <Card title="🚧 当前不能正式报价的原因">
          {req.cannot_quote_reasons.length === 0 ? (
            <div className="text-sm text-emerald-600">信息已齐全，可以生成正式报价（仍需人工批准）</div>
          ) : (
            <ul className="list-disc space-y-1 pl-4 text-sm text-amber-700">
              {req.cannot_quote_reasons.map((r) => <li key={r}>{r}</li>)}
            </ul>
          )}
        </Card>
      </div>
      <Card title="⚠️ 潜在风险" className="col-span-1">
        {(s.risks as string[])?.length ? (
          <ul className="list-disc space-y-1 pl-4 text-sm text-red-600">
            {(s.risks as string[]).map((r) => <li key={r}>{r}</li>)}
          </ul>
        ) : <div className="text-sm text-slate-400">未发现明显风险</div>}
      </Card>
      <Card title="🧭 建议下一步" className="col-span-2">
        <div className="rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-700">
          {s.next_step as string}
        </div>
        <div className="mt-3 text-xs text-slate-400">
          建议依据当前缺失字段与矛盾字段生成；每条建议都可以忽略或修改。
        </div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------- 对话
interface Msg { id: number; direction: string; sender: string; sent_at: string; raw_content: string; parse_json: string }

function Messages({ iid, rawText, onChanged }: { iid: number; rawText: string; onChanged: () => void }) {
  const [text, setText] = useState("");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["messages", iid],
    queryFn: () => get<{ items: Msg[] }>(`/inquiries/${iid}/messages`),
  });
  const add = useMutation({
    mutationFn: () => post(`/inquiries/${iid}/messages`, { text, direction: "in" }),
    onSuccess: () => { setText(""); onChanged(); refetch(); },
  });

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-2">
        <Card title="对话记录">
          {isLoading ? <Loading /> : error ? <ErrorState message={(error as Error).message} /> : (
            <div className="space-y-3">
              {(data!.items.length === 0) && <EmptyState text="暂无消息" icon="💬" />}
              {data!.items.map((m) => (
                <div key={m.id} className={`flex ${m.direction === "out" ? "justify-end" : ""}`}>
                  <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm ${m.direction === "out" ? "bg-brand-500 text-white" : "bg-slate-50 text-slate-700"}`}>
                    <div className="mb-1 text-[10px] opacity-60">
                      {m.direction === "in" ? "📩 客户" : "📤 我方"} · {new Date(m.sent_at).toLocaleString("zh-CN")}
                    </div>
                    <pre className="whitespace-pre-wrap font-sans">{m.raw_content}</pre>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="添加客户消息（多轮）" className="mt-4">
          <textarea className="input min-h-24" placeholder="粘贴客户的新回复，系统会自动更新需求状态…" value={text} onChange={(e) => setText(e.target.value)} />
          <div className="mt-2 flex justify-end">
            <button className="btn-primary" disabled={!text.trim() || add.isPending} onClick={() => add.mutate()}>
              {add.isPending ? "解析中…" : "添加并重新解析"}
            </button>
          </div>
        </Card>
      </div>
      <Card title="原始询盘">
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs text-slate-600">{rawText}</pre>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------- 需求
interface Hist { id: number; field: string; change_type: string; old_value: string; new_value: string; actor: string; note: string; created_at: string }

function Requirement({ iid }: { iid: number }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const [lock, setLock] = useState(false);
  const req = useQuery({ queryKey: ["req", iid], queryFn: () => get<ReqView>(`/inquiries/${iid}/requirement`) });
  const hist = useQuery({ queryKey: ["hist", iid], queryFn: () => get<{ items: Hist[] }>(`/inquiries/${iid}/history`) });
  const save = useMutation({
    mutationFn: (field: string) => post(`/inquiries/${iid}/slots`, { field, value, lock }),
    onSuccess: () => { setEditing(null); setValue(""); setLock(false); qc.invalidateQueries(); },
  });
  const unlock = useMutation({
    mutationFn: (field: string) => del(`/inquiries/${iid}/slots/${field}/lock`),
    onSuccess: () => qc.invalidateQueries(),
  });

  if (req.isLoading) return <Loading />;
  if (req.error) return <ErrorState message={(req.error as Error).message} />;
  const fields = Object.entries(req.data!.fields).filter(([, v]) => v.status !== "unknown" || v.value);

  return (
    <div className="grid grid-cols-3 gap-4">
      <Card title="🧩 结构化需求（人工确认具有最高优先级）" className="col-span-2">
        <table className="table-base">
          <thead><tr><th>字段</th><th>当前值</th><th>状态</th><th>依据</th><th className="w-40">操作</th></tr></thead>
          <tbody>
            {fields.map(([f, v]) => (
              <tr key={f} className={v.status === "conflicting" ? "bg-red-50/40" : ""}>
                <td className="font-medium text-slate-600">{FIELD_LABELS[f] || f}</td>
                <td>
                  {editing === f ? (
                    <div className="flex items-center gap-1.5">
                      <input className="input py-1 text-xs" autoFocus value={value} onChange={(e) => setValue(e.target.value)} />
                      <label className="flex items-center gap-1 text-[10px] text-slate-500">
                        <input type="checkbox" checked={lock} onChange={(e) => setLock(e.target.checked)} />锁定
                      </label>
                      <button className="btn-primary px-2 py-0.5 text-xs" onClick={() => save.mutate(f)}>存</button>
                      <button className="btn-ghost px-2 py-0.5 text-xs" onClick={() => setEditing(null)}>取消</button>
                    </div>
                  ) : (
                    <span className={v.status === "conflicting" ? "text-red-600" : "text-slate-700"}>{v.value || "—"}</span>
                  )}
                </td>
                <td>
                  <Badge value={v.status} text={STATUS_TEXT[v.status] || v.status} />
                  {v.locked && <span className="ml-1 text-xs text-amber-600">🔒</span>}
                </td>
                <td className="text-xs text-slate-400">
                  消息 #{v.source_message_id ?? "—"} · 置信度 {(v.confidence * 100).toFixed(0)}%
                </td>
                <td>
                  <div className="flex gap-1">
                    <button className="text-xs text-brand-500 hover:underline" onClick={() => { setEditing(f); setValue(v.raw || ""); }}>修改</button>
                    {v.locked && <button className="text-xs text-slate-400 hover:underline" onClick={() => unlock.mutate(f)}>解锁</button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title="🕓 修改历史">
        {hist.isLoading ? <Loading /> : (
          <ul className="space-y-2 text-xs">
            {(hist.data?.items || []).slice(0, 30).map((h) => (
              <li key={h.id} className="rounded-lg bg-slate-50 p-2">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-600">{FIELD_LABELS[h.field] || h.field}</span>
                  <span className="text-slate-400">{h.change_type} · {h.actor === "human" ? "👤人工" : "⚙️系统"}</span>
                </div>
                {h.old_value !== h.new_value && (
                  <div className="mt-0.5 text-slate-500">{h.old_value || "∅"} → <span className="text-slate-700">{h.new_value}</span></div>
                )}
                {h.note && <div className="mt-0.5 text-slate-400">{h.note}</div>}
              </li>
            ))}
            {(hist.data?.items || []).length === 0 && <EmptyState text="暂无修改记录" icon="🕓" />}
          </ul>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------- 追问
interface Clar { field: string; question_en: string; question_zh: string; reason: string; priority_score: number }

function Clarify({ iid }: { iid: number }) {
  const qc = useQueryClient();
  const rec = useQuery({
    queryKey: ["clarify", iid],
    queryFn: () => post<{ primary: Clar | null; secondary: Clar[] }>(`/inquiries/${iid}/clarification`),
  });
  const dismiss = useMutation({
    mutationFn: (logId: number) => post(`/inquiries/${iid}/clarification/${logId}/dismiss`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clarify", iid] }),
  });

  if (rec.isLoading) return <Loading />;
  if (rec.error) return <ErrorState message={(rec.error as Error).message} />;
  const { primary, secondary } = rec.data!;

  return (
    <div className="grid grid-cols-3 gap-4">
      <Card title="❓ 最值得追问的一个问题" className="col-span-2">
        {primary ? (
          <div className="rounded-xl border border-brand-100 bg-brand-50/60 p-4">
            <p className="text-base font-medium text-slate-800">{primary.question_en}</p>
            <p className="mt-1 text-sm text-slate-500">{primary.question_zh}</p>
            <div className="mt-3 rounded-lg bg-white/70 px-3 py-2 text-xs text-slate-500">
              <span className="font-medium text-slate-600">为什么建议问这个：</span>{primary.reason}
              <span className="ml-2 text-slate-400">（优先级 {primary.priority_score.toFixed(0)}）</span>
            </div>
            <div className="mt-3 flex gap-2">
              <button className="btn-primary text-xs" onClick={() => navigator.clipboard.writeText(primary.question_en)}>
                复制英文问题
              </button>
            </div>
          </div>
        ) : <EmptyState icon="🎉" text="暂时没有必须追问的问题" />}
      </Card>
      <Card title="其他待确认">
        <ul className="space-y-2">
          {secondary.map((s) => (
            <li key={s.field} className="rounded-lg bg-slate-50 p-2.5 text-xs">
              <div className="font-medium text-slate-600">{FIELD_LABELS[s.field] || s.field}</div>
              <div className="mt-0.5 text-slate-500">{s.question_zh}</div>
              <div className="mt-0.5 text-slate-400">{s.reason}</div>
            </li>
          ))}
          {secondary.length === 0 && <EmptyState text="暂无" icon="✅" />}
        </ul>
      </Card>
      <Card title="排序规则说明" className="col-span-3">
        <div className="text-xs text-slate-400">
          追问会按「法规/报价阻塞 &gt; 矛盾 &gt; 高信息增益 &gt; 偏好」排序，同一条问题不会重复骚扰客户；点击「修改」人工补齐字段后，对应追问会自动关闭。
        </div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------- 匹配
interface MatchItem {
  id: number; rank: number; total_score: number; scores_json: string; met_json: string;
  unmet_json: string; excluded: boolean; exclude_reason: string; is_alternative: boolean;
  data_snapshot_json: string;
  product: { id: number; sku: string; name_zh: string; name_en: string; moq: number; lead_time_days: number; certifications: string[]; material: string; spec: string };
}

function Match({ iid }: { iid: number }) {
  const qc = useQueryClient();
  const latest = useQuery({
    queryKey: ["matches", iid],
    queryFn: () => get<{ items: MatchItem[]; batch_no: string | null }>(`/inquiries/${iid}/matches`),
  });
  const run = useMutation({
    mutationFn: () => post(`/inquiries/${iid}/match`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["matches", iid] }),
  });
  if (latest.isLoading) return <Loading />;

  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <button className="btn-primary" onClick={() => run.mutate()} disabled={run.isPending}>
          {run.isPending ? "匹配中…" : "▶ 运行匹配"}
        </button>
        <span className="text-xs text-slate-400">
          两阶段检索：先召回候选，再按可配置权重确定性重排序；硬条件不满足会明确淘汰并显示原因
        </span>
      </div>
      {run.error && <ErrorState message={(run.error as Error).message} />}
      {(!latest.data || latest.data.items.length === 0) ? (
        <EmptyState icon="🎯" text="还没有匹配结果，点击「运行匹配」" />
      ) : (
        <div className="space-y-3">
          {latest.data.items.map((m) => {
            const scores = JSON.parse(m.scores_json) as Record<string, { score: number; max: number; detail: string }>;
            const met = JSON.parse(m.met_json) as string[];
            const unmet = JSON.parse(m.unmet_json) as string[];
            return (
              <Card key={m.id}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-slate-700">
                        #{m.rank} {m.product.name_en}
                      </span>
                      <span className="text-xs text-slate-400">{m.product.sku} · MOQ {m.product.moq} · {m.product.lead_time_days}天</span>
                      {m.excluded ? (
                        <Badge value="error" text={m.is_alternative ? "替代方案" : "已淘汰"} />
                      ) : (
                        <Badge value="active" text="推荐" />
                      )}
                      <SupplierCompare productId={m.product.id} />
                    </div>
                    <div className="mt-0.5 text-xs text-slate-400">{m.product.name_zh} · {m.product.material} · {m.product.spec} · 认证 {m.product.certifications.join(", ") || "无"}</div>
                    {m.exclude_reason && (
                      <div className="mt-2 rounded-lg bg-red-50 px-3 py-1.5 text-xs text-red-600">
                        ⚠️ {m.exclude_reason}
                      </div>
                    )}
                    <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                      {met.map((x) => <div key={x} className="text-emerald-600">✓ {x}</div>)}
                      {unmet.map((x) => <div key={x} className="text-amber-600">△ {x}</div>)}
                    </div>
                  </div>
                  <div className="w-40 shrink-0 space-y-1">
                    <div className="text-right text-2xl font-bold text-brand-600">{m.total_score}</div>
                    {Object.entries(scores).filter(([, v]) => v.max > 0).slice(0, 8).map(([k, v]) => (
                      <div key={k} className="flex items-center gap-1.5 text-[10px] text-slate-400" title={v.detail}>
                        <span className="w-16 truncate text-right">{k}</span>
                        <div className="h-1 flex-1 overflow-hidden rounded bg-slate-100">
                          <div className="h-full rounded bg-brand-400" style={{ width: `${(v.score / v.max) * 100}%` }} />
                        </div>
                        <span className="w-8">{v.score}/{v.max}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------- 报价
interface Quote {
  id: number; version: number; status: string; product_id: number | null; incoterm: string; currency: string;
  quantity: number; unit_cost: number; unit_price: number; customer_price: number; total_amount: number;
  is_formal: boolean; valid_until: string | null; product_name?: string;
}
interface QuoteDetail extends Quote {
  breakdown: { item: string; per_unit: number; amount: number; source: string }[];
  assumptions: string[]; missing: string[]; risks: string[];
  requirement_blockers: string[];
}

function QuotesTab({ iid }: { iid: number }) {
  const qc = useQueryClient();
  const [detail, setDetail] = useState<number | null>(null);
  const [form, setForm] = useState({ product_id: "", quantity: "1000", incoterm: "FOB", margin_rate: "0.15", printing: false });
  const products = useQuery({ queryKey: ["products-lite"], queryFn: () => get<{ items: { id: number; sku: string; name_en: string }[] }>("/products?page=1&page_size=100") });
  const quotes = useQuery({ queryKey: ["quotes", iid], queryFn: () => get<{ items: Quote[] }>(`/quotes/by-inquiry/${iid}`) });
  const create = useMutation({
    mutationFn: () => post("/quotes", { inquiry_id: iid, product_id: Number(form.product_id), quantity: Number(form.quantity), incoterm: form.incoterm, margin_rate: Number(form.margin_rate), printing: form.printing }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["quotes", iid] }); qc.invalidateQueries({ queryKey: ["inquiry", iid] }); },
  });
  const detailQ = useQuery({
    queryKey: ["quote", detail],
    queryFn: () => get<QuoteDetail>(`/quotes/${detail}`),
    enabled: !!detail,
  });
  const approve = useMutation({
    mutationFn: (id: number) => post(`/quotes/${id}/approve`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["quote", detail] }); qc.invalidateQueries({ queryKey: ["quotes", iid] }); },
  });
  if (quotes.isLoading) return <Loading />;

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-2 space-y-4">
        <Card title="报价版本">
          {!quotes.data?.items.length ? <EmptyState icon="💰" text="还没有报价" /> : (
            <table className="table-base">
              <thead><tr><th>版本</th><th>产品</th><th>数量</th><th>术语</th><th>内部成本</th><th>建议/客户价</th><th>状态</th><th></th></tr></thead>
              <tbody>
                {quotes.data.items.map((q) => (
                  <tr key={q.id}>
                    <td>v{q.version}</td>
                    <td className="text-xs">{q.product_name}</td>
                    <td>{q.quantity}</td>
                    <td>{q.incoterm}</td>
                    <td className="font-mono text-xs text-slate-400">${q.unit_cost.toFixed(3)}</td>
                    <td className="font-mono">${q.customer_price.toFixed(2)}</td>
                    <td><Badge value={q.status} text={{ draft: "草稿", pending_approval: "待批", approved: "已批准", rejected: "已拒绝", superseded: "已替代" }[q.status] || q.status} /></td>
                    <td><button className="text-xs text-brand-500 hover:underline" onClick={() => setDetail(q.id)}>明细</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        {detail && detailQ.data && (
          <Card title={`计算明细 · v${detailQ.data.version} (${detailQ.data.incoterm})`}
                extra={<div className="flex gap-2">
                  {detailQ.data.status !== "approved" && (
                    <button className="btn-primary text-xs" onClick={() => approve.mutate(detailQ.data!.id)} disabled={approve.isPending}>
                      ✓ 批准为正式报价
                    </button>
                  )}
                  <button className="btn-ghost text-xs" onClick={() => setDetail(null)}>关闭</button>
                </div>}>
            {detailQ.data.requirement_blockers.length > 0 && (
              <div className="mb-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                {detailQ.data.requirement_blockers.map((b) => <div key={b}>⚠️ {b}</div>)}
              </div>
            )}
            <table className="table-base text-xs">
              <thead><tr><th>项目</th><th>单件</th><th>小计</th><th>数据来源</th></tr></thead>
              <tbody>
                {detailQ.data.breakdown.map((b) => (
                  <tr key={b.item}>
                    <td className="text-slate-600">{b.item}</td>
                    <td className="font-mono">${b.per_unit.toFixed(4)}</td>
                    <td className="font-mono">${b.amount.toFixed(2)}</td>
                    <td className="text-slate-400">{b.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-3 flex items-center justify-between rounded-lg bg-slate-50 px-4 py-2.5">
              <span className="text-sm text-slate-500">
                内部成本 <b className="text-slate-700">${detailQ.data.unit_cost.toFixed(3)}</b> ·
                建议报价 <b className="text-brand-600">${detailQ.data.unit_price.toFixed(2)}</b> ·
                合计 <b>${detailQ.data.total_amount.toFixed(2)}</b>
              </span>
              {detailQ.data.valid_until && <span className="text-xs text-slate-400">有效期至 {new Date(detailQ.data.valid_until).toLocaleDateString("zh-CN")}</span>}
            </div>
            {detailQ.data.risks.length > 0 && (
              <div className="mt-2 rounded-lg bg-red-50 p-3 text-xs text-red-600">
                {detailQ.data.risks.map((r) => <div key={r}>⚠️ {r}</div>)}
              </div>
            )}
            {detailQ.data.assumptions.map((a) => <div key={a} className="mt-1 text-[10px] text-slate-400">ℹ️ {a}</div>)}
          </Card>
        )}
        {create.error && <ErrorState message={(create.error as Error).message} />}
      </div>

      <Card title="新建报价（确定性计算）">
        <div className="space-y-3">
          <div>
            <label className="label">产品</label>
            <select className="input" value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })}>
              <option value="">选择产品…</option>
              {products.data?.items.map((p) => (
                <option key={p.id} value={p.id}>{p.sku} · {p.name_en}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="label">数量</label>
              <input className="input" type="number" min="1" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
            </div>
            <div>
              <label className="label">贸易术语</label>
              <select className="input" value={form.incoterm} onChange={(e) => setForm({ ...form, incoterm: e.target.value })}>
                {["EXW", "FOB", "CIF", "DDP"].map((t) => <option key={t}>{t}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="label">利润率</label>
            <input className="input" type="number" step="0.01" min="0" max="0.9" value={form.margin_rate} onChange={(e) => setForm({ ...form, margin_rate: e.target.value })} />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={form.printing} onChange={(e) => setForm({ ...form, printing: e.target.checked })} />
            含 Logo 印刷（版费摊销）
          </label>
          <button className="btn-primary w-full justify-center" disabled={!form.product_id || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "计算中…" : "计算并创建草稿"}
          </button>
          <p className="text-[10px] leading-4 text-slate-400">
            报价由程序按阶梯价 + 包装/印刷/物流/保险/税率确定性计算，AI 不参与定价；
            只有点击「批准」后才成为正式报价。
          </p>
        </div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------- 回复
interface Draft {
  id: number; kind: string; tone: string; subject_en: string; body_en: string; body_zh: string;
  status: string; facts_used: { field: string; value: string }[]; needs_confirmation: string[];
}
const KINDS: [string, string][] = [
  ["first_reply", "首次回复"], ["ask_missing_info", "追问缺失信息"], ["product_recommend", "产品推荐"],
  ["sample", "样品沟通"], ["quote_send", "发送报价"], ["quote_follow_up", "报价后跟进"],
  ["delay_notice", "交期延误"], ["alternative_offer", "替代方案"], ["polite_rejection", "礼貌拒绝"],
  ["reactivation", "重新激活"],
];

function Replies({ iid }: { iid: number }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState("first_reply");
  const [tone, setTone] = useState("friendly");
  const [openId, setOpenId] = useState<number | null>(null);
  const drafts = useQuery({ queryKey: ["replies", iid], queryFn: () => get<{ items: Draft[] }>(`/replies?inquiry_id=${iid}`) });
  const gen = useMutation({
    mutationFn: () => post<Draft>("/replies/generate", { kind, tone, extra: { inquiry_id: iid } }),
    onSuccess: (d) => { qc.invalidateQueries({ queryKey: ["replies", iid] }); setOpenId(d.id); },
  });
  const open = useQuery({
    queryKey: ["reply", openId],
    queryFn: () => get<Draft>(`/replies/${openId}`),
    enabled: !!openId,
  });
  const approve = useMutation({
    mutationFn: (id: number) => post(`/replies/${id}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reply", openId] }),
  });
  const current = open.data;
  const [copied, setCopied] = useState("");

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="space-y-4">
        <Card title="生成新草稿">
          <label className="label">场景</label>
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <label className="label mt-3">语气</label>
          <div className="flex gap-2">
            {["formal", "friendly", "concise"].map((tn) => (
              <button key={tn} className={`flex-1 rounded-lg border px-2 py-1.5 text-xs ${tone === tn ? "border-brand-500 bg-brand-50 text-brand-600" : "border-slate-200 text-slate-500"}`}
                      onClick={() => setTone(tn)}>
                {{ formal: "正式", friendly: "友好", concise: "简洁" }[tn]}
              </button>
            ))}
          </div>
          <button className="btn-primary mt-4 w-full justify-center" disabled={gen.isPending} onClick={() => gen.mutate()}>
            {gen.isPending ? "生成中…" : "生成中英文草稿"}
          </button>
        </Card>
        <Card title="历史草稿">
          <ul className="space-y-1">
            {drafts.data?.items.map((d) => (
              <li key={d.id}>
                <button className={`w-full rounded-lg px-2 py-1.5 text-left text-xs ${openId === d.id ? "bg-brand-50 text-brand-600" : "text-slate-600 hover:bg-slate-50"}`}
                        onClick={() => setOpenId(d.id)}>
                  {KINDS.find(([k]) => k === d.kind)?.[1]} · v{d.id} <Badge value={d.status} text={{ draft: "草稿", edited: "已编辑", approved: "已批准", sent_manually: "已人工发送" }[d.status] || d.status} />
                </button>
              </li>
            ))}
            {!drafts.data?.items.length && <EmptyState text="还没有草稿" icon="✉️" />}
          </ul>
        </Card>
      </div>
      <div className="col-span-2">
        {!current ? <EmptyState icon="✉️" text="生成或选择一个草稿查看" /> : (
          <Card title={current.subject_en}
                extra={<div className="flex gap-2">
                  <button className="btn-ghost text-xs" onClick={() => { navigator.clipboard.writeText(`${current.subject_en}\n\n${current.body_en}`); setCopied("en"); setTimeout(() => setCopied(""), 1500); }}>
                    {copied === "en" ? "✓ 已复制" : "复制英文全文"}
                  </button>
                  {current.status !== "approved" && (
                    <button className="btn-primary text-xs" onClick={() => approve.mutate(current.id)}>✓ 批准</button>
                  )}
                </div>}>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-[13px] leading-6 text-slate-700">{current.body_en}</pre>
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-slate-400">中文对照</summary>
              <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-amber-50/60 p-4 text-[13px] leading-6 text-slate-600">{current.body_zh}</pre>
            </details>
            <div className="mt-4 grid grid-cols-2 gap-4 text-xs">
              <div>
                <div className="mb-1 font-medium text-slate-500">使用的事实</div>
                <ul className="space-y-0.5 text-slate-500">
                  {current.facts_used.map((f) => (
                    <li key={f.field}>• {FIELD_LABELS[f.field] || f.field} = {f.value}</li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="mb-1 font-medium text-amber-600">发送前需人工确认</div>
                <ul className="space-y-0.5 text-amber-700">
                  {current.needs_confirmation.map((n) => <li key={n}>⚠️ {n}</li>)}
                </ul>
              </div>
            </div>
            <p className="mt-3 text-[10px] text-slate-400">系统不会自动发送任何邮件/消息；批准后请在邮箱或 WhatsApp 中人工发送。</p>
          </Card>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------- 跟进
interface Task { id: number; title: string; due_at: string | null; status: string; priority: string; reason_json: string }

function FollowupsTab({ iid }: { iid: number }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const tasks = useQuery({ queryKey: ["followups-inquiry", iid], queryFn: () => get<{ items: Task[] }>(`/followups?inquiry_id=${iid}&page_size=50`) });
  const create = useMutation({
    mutationFn: () => post("/followups", { title, inquiry_id: iid, due_at: due ? new Date(due).toISOString() : undefined, reason: { source: "manual" } }),
    onSuccess: () => { setTitle(""); setDue(""); qc.invalidateQueries({ queryKey: ["followups-inquiry", iid] }); },
  });
  const done = useMutation({
    mutationFn: (id: number) => post(`/followups/${id}/status`, { status: "done" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["followups-inquiry", iid] }),
  });
  return (
    <div className="grid grid-cols-3 gap-4">
      <Card title="任务列表" className="col-span-2">
        <ul className="divide-y divide-slate-50">
          {tasks.data?.items.map((t) => (
            <li key={t.id} className="flex items-center gap-3 py-2.5">
              <Badge value={t.priority} text={t.priority === "high" ? "高" : "常规"} />
              <span className={`flex-1 text-sm ${t.status === "done" ? "text-slate-300 line-through" : "text-slate-700"}`}>{t.title}</span>
              <span className="text-xs text-slate-400">{t.due_at ? new Date(t.due_at).toLocaleDateString("zh-CN") : ""}</span>
              {t.status !== "done" && <button className="btn-ghost px-2 py-1 text-xs" onClick={() => done.mutate(t.id)}>完成</button>}
            </li>
          ))}
          {!tasks.data?.items.length && <EmptyState text="暂无跟进任务" icon="🔔" />}
        </ul>
      </Card>
      <Card title="创建跟进任务">
        <input className="input" placeholder="任务标题，如：发送报价给客户" value={title} onChange={(e) => setTitle(e.target.value)} />
        <input className="input mt-2" type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
        <button className="btn-primary mt-3 w-full justify-center" disabled={!title.trim() || create.isPending} onClick={() => create.mutate()}>
          创建任务
        </button>
      </Card>
    </div>
  );
}


// ------------------------------------------------------------- 供应商比价
interface SupplierQuote {
  id: number; supplier_id: number; supplier_name: string; cost_price: number;
  currency: string; moq: number; lead_time_days: number; total: number;
  scores: Record<string, { score: number; raw: number; detail: string }>;
}

function SupplierCompare({ productId }: { productId: number }) {
  const [open, setOpen] = useState(false);
  const quotes = useQuery({
    queryKey: ["supplier-quotes", productId],
    queryFn: () => get<{ items: SupplierQuote[]; recommend_reason: string }>(
      `/products/${productId}/supplier-quotes`),
    enabled: open,
  });
  return (
    <span className="inline-block">
      <button className="text-xs text-brand-500 hover:underline" onClick={() => setOpen(!open)}>
        {open ? "收起比价" : "供应商比价"}
      </button>
      {open && (
        <div className="mt-1.5 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
          {quotes.isLoading ? <span className="text-xs text-slate-400">加载中…</span> :
           !quotes.data?.items.length ? <span className="text-xs text-slate-400">暂无供应商比价记录</span> : (
            <>
              <div className="mb-1 text-[11px] text-emerald-600">💡 {quotes.data.recommend_reason}</div>
              <table className="w-full text-[11px]">
                <thead><tr className="text-slate-400"><th className="text-left">供应商</th><th>成本</th><th>交期</th><th>可靠性</th><th>综合</th></tr></thead>
                <tbody>
                  {quotes.data.items.map((q, idx) => (
                    <tr key={q.id} className="border-t border-slate-100">
                      <td className="py-0.5 text-slate-600">{q.supplier_name}{idx === 0 && <span className="ml-1 text-emerald-500">←推荐</span>}</td>
                      <td className="text-center font-mono">{q.cost_price}</td>
                      <td className="text-center">{q.lead_time_days}天</td>
                      <td className="text-center">{q.scores.reliability?.score ?? "—"}</td>
                      <td className="text-center font-bold text-brand-600">{q.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </span>
  );
}
