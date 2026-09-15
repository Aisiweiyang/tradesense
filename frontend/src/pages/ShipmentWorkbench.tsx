import { useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getToken, get, post, patch } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";

interface Issue {
  id: number; severity: string; issue_type: string; rule_code: string;
  title: string; expected_value: string; actual_value: string;
  evidence: { doc_id?: number; doc_type: string; field: string; page: number | null; text: string; value?: string }[];
  status: string; assigned_to?: string; resolution_note: string;
}
interface DocRow {
  id: number; doc_type: string; version: number; status: string;
  original_filename: string; pages: number; has_text_layer: boolean; extract_error: string;
}
interface FieldRow {
  id: number; document_id: number; doc_type: string; field_name: string; value: string;
  confidence: number; evidence_page: number | null; evidence_text: string; source: string;
}
interface FieldChange {
  id: number; document_id: number; field_name: string;
  old_value: string; new_value: string; change_type: string; prev_version: number;
}
interface ShipmentRow {
  id: number; shipment_no: string; order_no: string; transport_mode: string;
  status: string; port_of_loading: string; port_of_discharge: string; incoterm: string;
  etd: string | null; cutoff_at: string | null; customer_name: string;
  open_total: number; high: number; medium: number; low: number; risk: string;
}
interface Detail extends ShipmentRow {
  documents: DocRow[]; issues: Issue[]; notes: string;
}

const DOC_LABEL: Record<string, string> = {
  invoice: "商业发票", packing_list: "装箱单", bill_of_lading: "提单",
  customs_declaration: "报关单", letter_of_credit: "信用证",
  origin_certificate: "原产地证", other: "其他",
};
const SEV_LABEL: Record<string, string> = { high: "高风险", medium: "中风险", low: "低风险" };
const STATUS_LABEL: Record<string, string> = {
  preparing: "备货中", docs_making: "单证制作", ready_to_ship: "待发货",
  shipped: "已发货", blocked: "异常阻塞", settled: "已结汇", cancelled: "已取消",
};

export default function ShipmentWorkbench() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const routeParams = useParams();
  const [selected, setSelected] = useState<number | null>(
    routeParams.id ? Number(routeParams.id) : null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ order_no: "", port_of_loading: "", port_of_discharge: "", cutoff_at: "" });
  const fileRef = useRef<HTMLInputElement>(null);

  const list = useQuery({
    queryKey: ["shipments", q],
    queryFn: () => get<{ items: ShipmentRow[]; total: number }>(
      `/shipments?page_size=50&q=${encodeURIComponent(q)}`),
  });

  const detail = useQuery({
    queryKey: ["shipment", selected],
    queryFn: () => get<Detail>(`/shipments/${selected}`),
    enabled: selected !== null,
  });

  const create = useMutation({
    mutationFn: () => post("/shipments", {
      ...form,
      cutoff_at: form.cutoff_at ? new Date(form.cutoff_at).toISOString() : undefined,
    }),
    onSuccess: () => { setCreating(false); qc.invalidateQueries({ queryKey: ["shipments"] }); },
  });

  const totals = useMemo(() => {
    const items = list.data?.items || [];
    return {
      shipments: items.length,
      open: items.reduce((a, s) => a + s.open_total, 0),
      high: items.reduce((a, s) => a + s.high, 0),
      docs: undefined as number | undefined,
    };
  }, [list.data]);

  return (
    <div className="flex min-h-[calc(100vh-7rem)] flex-col">
      <PageHeader title="单证工作台" desc="货件 · 单证核验 · 异常处理 · 催补协作"
        actions={<button className="btn-primary" onClick={() => setCreating(!creating)}>＋ 新建货件</button>} />

      {/* 统计带 */}
      <div className="mb-3 flex items-center gap-6 rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-sm">
        <Stat label="今日待处理" n={totals.open} color="text-slate-800" />
        <Stat label="高风险" n={totals.high} color="text-red-600" />
        <Stat label="货件总数" n={totals.shipments} color="text-slate-800" />
        <span className="ml-auto text-xs text-slate-400">
          打开左侧货件查看异常与单证；点击证据可定位 PDF 页码
        </span>
      </div>

      {creating && (
        <Card className="mb-3" title="新建货件">
          <div className="grid grid-cols-5 gap-3">
            <input className="input" placeholder="订单号" value={form.order_no} onChange={(e) => setForm({ ...form, order_no: e.target.value })} />
            <input className="input" placeholder="起运港" value={form.port_of_loading} onChange={(e) => setForm({ ...form, port_of_loading: e.target.value })} />
            <input className="input" placeholder="目的港" value={form.port_of_discharge} onChange={(e) => setForm({ ...form, port_of_discharge: e.target.value })} />
            <input className="input" type="datetime-local" onChange={(e) => setForm({ ...form, cutoff_at: e.target.value })} />
            <button className="btn-primary" disabled={create.isPending} onClick={() => create.mutate()}>创建</button>
          </div>
        </Card>
      )}

      {/* 三段式：左列表 42% + 右详情 58% */}
      <div className="grid flex-1 grid-cols-[42%_1fr] gap-4">
        <div className="flex flex-col">
          <input className="input mb-2" placeholder="搜索货件号/订单号/港口…" value={q} onChange={(e) => setQ(e.target.value)} />
          {list.isLoading ? <Loading /> : list.error ? <ErrorState message={(list.error as Error).message} onRetry={list.refetch} /> :
            !list.data?.items.length ? <EmptyState icon="🚢" text="还没有货件。成交的报价可以一键转成货件，或点击右上角新建。" /> : (
              <div className="card divide-y divide-slate-100">
                {list.data.items.map((s) => (
                  <button key={s.id}
                          className={`w-full px-3 py-2.5 text-left hover:bg-slate-50 ${selected === s.id ? "bg-brand-50/60" : ""}`}
                          onClick={() => setSelected(s.id)}>
                    <div className="flex items-center gap-2">
                      <RiskDot risk={s.risk} />
                      <span className="font-mono text-xs text-slate-500">{s.shipment_no}</span>
                      <span className="ml-auto text-xs text-slate-400">
                        {s.port_of_loading} → {s.port_of_discharge}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs">
                      <span className="min-w-0 flex-1 truncate text-slate-700">{s.customer_name || s.order_no || "未关联客户"}</span>
                      {s.open_total > 0 ? (
                        <span className="text-xs">
                          <b className={s.high > 0 ? "text-red-500" : "text-amber-500"}>{s.open_total}</b> 个异常
                        </span>
                      ) : (
                        <span className="text-emerald-500">✓ 无异常</span>
                      )}
                      <Badge value={s.status} text={STATUS_LABEL[s.status] || s.status} />
                    </div>
                  </button>
                ))}
              </div>
            )}
        </div>

        <div>
          {selected === null ? (
            <EmptyState icon="📋" text="从左侧选择一个货件，查看异常、单证与字段对照" />
          ) : detail.isLoading ? <Loading /> : detail.error ? <ErrorState message={(detail.error as Error).message} onRetry={detail.refetch} /> : (
            <ShipmentDetailPanel detail={detail.data!} onChanged={() => {
              qc.invalidateQueries({ queryKey: ["shipment", selected] });
              qc.invalidateQueries({ queryKey: ["shipments"] });
            }} />
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, n, color }: { label: string; n: number; color: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <b className={`text-lg ${color}`}>{n}</b>
      <span className="text-xs text-slate-400">{label}</span>
    </span>
  );
}

function RiskDot({ risk }: { risk: string }) {
  const color = risk === "high" ? "bg-red-500" : risk === "medium" ? "bg-amber-500" : "bg-emerald-500";
  return <span className={`inline-block h-2 w-2 rounded-full ${color}`} aria-hidden />;
}

const TABS = [["issues", "异常"], ["docs", "单证"], ["fields", "字段对照"], ["comms", "沟通记录"]] as const;

function ShipmentDetailPanel({ detail, onChanged }: { detail: Detail; onChanged: () => void }) {
  const [tab, setTab] = useState<string>("issues");
  return (
    <Card title={
      <span className="flex items-center gap-2">
        <span className="font-mono text-xs text-slate-400">{detail.shipment_no}</span>
        <span>{detail.customer_name || detail.order_no}</span>
        <Badge value={detail.status} text={STATUS_LABEL[detail.status] || detail.status} />
        <span className="text-xs text-slate-400">{detail.incoterm} · {detail.port_of_loading} → {detail.port_of_discharge}</span>
      </span>
    } extra={
      <RecheckButton shipmentId={detail.id} onChanged={onChanged} />
    }>
      <div className="mb-3 flex gap-1 border-b border-slate-100">
        {TABS.map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)}
                  className={`border-b-2 px-3 py-1.5 text-sm ${tab === key ? "border-brand-500 font-medium text-brand-600" : "border-transparent text-slate-500"}`}>
            {label}{key === "issues" && detail.open_total > 0 ? ` (${detail.open_total})` : ""}
          </button>
        ))}
      </div>

      {tab === "issues" && <IssuesTab detail={detail} onChanged={onChanged} />}
      {tab === "docs" && <DocsTab detail={detail} onChanged={onChanged} />}
      {tab === "fields" && <FieldsTab detail={detail} onChanged={onChanged} />}
      {tab === "comms" && <CommsTab detail={detail} />}
    </Card>
  );
}

function RecheckButton({ shipmentId, onChanged }: { shipmentId: number; onChanged: () => void }) {
  const recheck = useMutation({
    mutationFn: () => post(`/shipments/${shipmentId}/recheck`),
    onSuccess: onChanged,
  });
  return (
    <button className="btn-ghost text-xs" disabled={recheck.isPending} onClick={() => recheck.mutate()}>
      {recheck.isPending ? "校验中…" : "⟳ 重新校验"}
    </button>
  );
}

function IssuesTab({ detail, onChanged }: { detail: Detail; onChanged: () => void }) {
  const [noteFor, setNoteFor] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const act = useMutation({
    mutationFn: ({ id, action, note }: { id: number; action: string; note?: string }) =>
      post(`/shipments/issues/${id}/action`, { action, note }),
    onSuccess: onChanged,
  });
  const open = detail.issues.filter((i) => i.status === "open");
  const handled = detail.issues.filter((i) => i.status !== "open");

  const IssueCard = ({ i }: { i: Issue }) => (
    <div data-issue-id={i.id} className={`rounded-lg border p-3 ${i.severity === "high" ? "border-red-200 bg-red-50/40" : i.severity === "medium" ? "border-amber-200 bg-amber-50/40" : "border-slate-200 bg-slate-50"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Badge value={i.severity} text={SEV_LABEL[i.severity] || i.severity} />
            <span className="text-sm font-medium text-slate-700">{i.title}</span>
          </div>
          {i.status !== "open" && (
            <div className="mt-1 text-xs text-slate-400">
              状态 {i.status} · {i.resolution_note}
            </div>
          )}
          <ul className="mt-1.5 space-y-0.5 text-xs text-slate-500">
            {i.evidence.map((e, idx) => (
              <li key={idx}>
                证据：{DOC_LABEL[e.doc_type] || e.doc_type}
                {e.page ? ` 第${e.page}页` : ""}
                {e.text ? <span className="font-mono"> “{e.text.slice(0, 50)}”</span> : ""}
              </li>
            ))}
          </ul>
        </div>
      </div>
      {i.status === "open" && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          <button className="btn-primary px-2 py-1 text-xs" data-testid={`adopt-${i.id}`} onClick={() => act.mutate({ id: i.id, action: "adopt" })}>采纳建议</button>
          <button className="btn-ghost px-2 py-1 text-xs" onClick={() => act.mutate({ id: i.id, action: "manual_fixed" })}>已手动修改</button>
          {noteFor === i.id ? (
            <span className="flex items-center gap-1.5">
              <input className="input py-1 text-xs" placeholder="忽略理由（必填）" value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
              <button className="btn-danger px-2 py-1 text-xs"
                      disabled={!note.trim()}
                      onClick={() => { act.mutate({ id: i.id, action: "ignore", note }); setNoteFor(null); setNote(""); }}>
                确认忽略
              </button>
              <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setNoteFor(null)}>取消</button>
            </span>
          ) : (
            <button className="btn-ghost px-2 py-1 text-xs" onClick={() => { setNoteFor(i.id); setNote(""); }}>忽略并说明</button>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-2.5">
      {open.length === 0 && handled.length === 0 && (
        <EmptyState icon="✅" text="所有异常已解决" />
      )}
      {open.map((i) => <IssueCard key={i.id} i={i} />)}
      {handled.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-slate-400">已处理 ({handled.length})</summary>
          <div className="mt-2 space-y-2 opacity-70">
            {handled.map((i) => <IssueCard key={i.id} i={i} />)}
          </div>
        </details>
      )}
    </div>
  );
}

function DocsTab({ detail, onChanged }: { detail: Detail; onChanged: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<{ id: number; page: number } | null>(null);
  const [diffDocId, setDiffDocId] = useState<number | null>(null);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return fetch(`/api/shipments/${detail.id}/documents`, {
        method: "POST", body: fd, headers: { Authorization: `Bearer ${getToken()}` },
      }).then((r) => r.json());
    },
    onSuccess: () => onChanged,
  });
  const DOC_STATUS: Record<string, string> = {
    uploaded: "已上传", extracting: "解析中", extracted: "已提取",
    needs_manual: "待人工录入", verified: "已核验", failed: "失败",
  };
  return (
    <div>
      {preview && (
        <div className="mb-3 rounded-lg border border-slate-200">
          <div className="flex items-center justify-between bg-slate-50 px-3 py-1.5 text-xs text-slate-500">
            <span>PDF 预览{preview.page ? ` · 第 ${preview.page} 页` : ""}</span>
            <button className="text-brand-500" onClick={() => setPreview(null)}>关闭</button>
          </div>
          <iframe key={preview.page} title="document-preview"
                  src={`/api/shipments/documents/${preview.id}/file?access_token=${encodeURIComponent(getToken() || "")}#page=${preview.page || 1}`}
                  className="h-96 w-full" />
        </div>
      )}
      <div className="mb-3">
        <button className="btn-primary text-xs" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
          ⬆ 上传单证（PDF）
        </button>
        <input ref={fileRef} type="file" accept=".pdf" className="hidden"
               onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); }} />
        {upload.isPending && <span className="ml-2 text-xs text-slate-400">上传解析中…</span>}
        {upload.error && <span className="ml-2 text-xs text-red-500">上传失败</span>}
      </div>
      <table className="table-base text-xs">
        <thead><tr><th>单证</th><th>文件</th><th>版本</th><th>页数</th><th>状态</th><th></th></tr></thead>
        <tbody>
          {detail.documents.map((d) => (
            <tr key={d.id}>
              <td>{DOC_LABEL[d.doc_type] || d.doc_type}</td>
              <td className="font-mono">{d.original_filename}</td>
              <td>
                <button data-testid={`ver-${d.id}`} className="text-brand-600 underline decoration-dotted hover:text-brand-700"
                        onClick={() => setDiffDocId(diffDocId === d.id ? null : d.id)}
                        title="点击查看与上一版本的差异">
                  v{d.version}
                </button>
              </td>
              <td>{d.pages}</td>
              <td>
                <Badge value={d.status === "failed" ? "failed" : d.status === "needs_manual" ? "needs_confirmation" : "active"}
                       text={DOC_STATUS[d.status] || d.status} />
                {d.extract_error && <div className="max-w-56 text-[10px] text-amber-600">{d.extract_error}</div>}
              </td>
              <td>
                <button className="text-xs text-brand-500 hover:underline"
                        onClick={() => setPreview({ id: d.id, page: 1 })}>预览</button>
              </td>
            </tr>
          ))}
          {!detail.documents.length && <tr><td colSpan={6}><EmptyState icon="📄" text="还没有上传单证" /></td></tr>}
        </tbody>
      </table>
      {diffDocId !== null && <VersionDiffPanel docId={diffDocId} onClose={() => setDiffDocId(null)} />}
    </div>
  );
}

function VersionDiffPanel({ docId, onClose }: { docId: number; onClose: () => void }) {
  const diff = useQuery({
    queryKey: ["doc-diff", docId],
    queryFn: () => get<{ document_id: number; doc_type: string; version: number;
                         prev_version: number | null; items: FieldChange[] }>(
      `/shipments/documents/${docId}/diff`),
  });
  return (
    <div data-testid="version-diff" className="mt-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
      <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
        <span>
          版本差异
          {diff.data ? <>：{DOC_LABEL[diff.data.doc_type] || diff.data.doc_type}
            {diff.data.prev_version ? ` v${diff.data.prev_version} → v${diff.data.version}` : `（v${diff.data.version} 为首个版本）`}
          </> : ""}
        </span>
        <button className="text-brand-500" onClick={onClose}>关闭</button>
      </div>
      {diff.isLoading ? <Loading /> : diff.error ? <ErrorState message={(diff.error as Error).message} onRetry={diff.refetch} /> :
        !diff.data!.items.length ? <div className="py-3 text-center text-xs text-slate-400">
          {diff.data!.prev_version ? "与上一版本无字段差异" : "这是该类型的第一版，没有可对比的版本"}
        </div> : (
          <table className="table-base text-xs" data-testid="diff-table">
            <thead><tr><th>字段</th><th>类型</th><th>旧值（来源版本）</th><th>新值</th></tr></thead>
            <tbody>
              {diff.data!.items.map((c) => (
                <tr key={c.id} className={c.change_type === "changed" ? "bg-amber-50/70" : ""}>
                  <td className="font-medium text-slate-600">{c.field_name}</td>
                  <td>
                    <Badge value={c.change_type === "changed" ? "pending" : c.change_type === "added" ? "active" : "failed"}
                           text={c.change_type === "changed" ? "变更" : c.change_type === "added" ? "新增" : "移除"} />
                  </td>
                  <td className="font-mono text-slate-400">{c.old_value || "—"}<span className="ml-1 text-[10px]">v{c.prev_version}</span></td>
                  <td className="font-mono text-slate-700">{c.new_value || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </div>
  );
}

function FieldsTab({ detail, onChanged }: { detail: Detail; onChanged: () => void }) {
  const fields = useQuery({
    queryKey: ["shipment-fields", detail.id],
    queryFn: () => get<{ items: FieldRow[] }>(`/shipments/${detail.id}/fields`),
  });
  // 版本差异高亮：有变更记录的 (文档, 字段) 标黄并在悬浮提示中显示旧值
  const changes = useQuery({
    queryKey: ["shipment-field-changes", detail.id],
    queryFn: () => get<{ items: FieldChange[] }>(`/shipments/${detail.id}/field-changes`),
  });
  const changedMap = useMemo(() => {
    const m = new Map<string, FieldChange>();
    for (const c of changes.data?.items || []) {
      const key = `${c.document_id}:${c.field_name}`;
      const prev = m.get(key);
      // 同一字段多轮变更时，保留最新一条（id 更大）
      if (!prev || c.id > prev.id) m.set(key, c);
    }
    return m;
  }, [changes.data]);
  const [editing, setEditing] = useState<number | null>(null);
  const [value, setValue] = useState("");
  const save = useMutation({
    mutationFn: ({ id, value }: { id: number; value: string }) =>
      patch(`/shipments/fields/${id}`, { value }),
    onSuccess: () => { setEditing(null); onChanged(); fields.refetch(); },
  });
  if (fields.isLoading) return <Loading />;

  const byName = new Map<string, FieldRow[]>();
  for (const f of fields.data?.items || []) {
    byName.set(f.field_name, [...(byName.get(f.field_name) || []), f]);
  }
  return (
    <div className="max-h-[28rem] overflow-auto">
      <table className="table-base text-xs">
        <thead><tr><th>字段</th><th>单证</th><th>值</th><th>来源</th><th>证据</th><th></th></tr></thead>
        <tbody>
          {[...byName.entries()].map(([name, rows]) => (
            rows.map((f, idx) => {
              const change = changedMap.get(`${f.document_id}:${f.field_name}`);
              return (
              <tr key={f.id} className={`${idx > 0 ? "opacity-60" : ""} ${change ? "bg-amber-50/80" : ""}`}
                  data-changed={change ? "true" : undefined}
                  title={change ? `版本差异：${change.old_value || "（新增）"} → ${change.new_value}（自 v${change.prev_version}）` : undefined}>
                <td className="font-medium text-slate-600">
                  {idx === 0 ? <span>{name}{change && idx === 0 ? <span className="ml-1 text-amber-500" title="该字段近期有版本变更">●</span> : ""}</span> : ""}
                </td>
                <td>{DOC_LABEL[f.doc_type] || f.doc_type}</td>
                <td>
                  {editing === f.id ? (
                    <span className="flex items-center gap-1">
                      <input className="input py-0.5 text-xs" value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
                      <button className="btn-primary px-1.5 py-0.5 text-[10px]" onClick={() => save.mutate({ id: f.id, value })}>存</button>
                    </span>
                  ) : <span className="font-mono">{f.value}</span>}
                </td>
                <td>{f.source === "manual" ? <Badge value="active" text="人工" /> : <span className="text-slate-400">提取 {(f.confidence * 100).toFixed(0)}%</span>}</td>
                <td className="text-slate-400">{f.evidence_page ? `第${f.evidence_page}页` : "—"} {f.evidence_text.slice(0, 24)}</td>
                <td>
                  <button className="text-xs text-brand-500 hover:underline"
                          onClick={() => { setEditing(f.id); setValue(f.value); }}>修改</button>
                </td>
              </tr>
              );
            })
          ))}
        </tbody>
      </table>
      {!byName.size && <EmptyState icon="🔍" text="还没有提取到字段" />}
    </div>
  );
}

function CommsTab({ detail }: { detail: Detail }) {
  const chase = useMutation({
    mutationFn: () => post<{ subject_en: string; body_en: string; body_zh: string; needs_confirmation: string[] }>(
      `/shipments/${detail.id}/chase-email`),
  });
  const [draft, setDraft] = useState<{ subject_en: string; body_en: string; body_zh: string; needs_confirmation: string[] } | null>(null);
  const [copied, setCopied] = useState(false);

  return (
    <div>
      <button className="btn-primary mb-3 text-xs" disabled={chase.isPending}
              onClick={() => chase.mutate(undefined, { onSuccess: (d) => setDraft(d) })}>
        ✉️ 生成催补/改单邮件草稿
      </button>
      {chase.error && <ErrorState message={(chase.error as Error).message} />}
      {!draft ? <EmptyState icon="✉️" text="点击生成引用具体异常的催补邮件（不会自动发送）" /> : (
        <Card title={draft.subject_en}
              extra={<button className="btn-ghost text-xs"
                             onClick={() => { navigator.clipboard.writeText(`${draft.subject_en}\n\n${draft.body_en}`); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
                {copied ? "✓ 已复制" : "复制英文全文"}
              </button>}>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs leading-5">{draft.body_en}</pre>
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-slate-400">中文对照</summary>
            <pre className="mt-1 whitespace-pre-wrap rounded-lg bg-amber-50/60 p-3 text-xs leading-5">{draft.body_zh}</pre>
          </details>
          <ul className="mt-2 text-[10px] text-amber-600">
            {draft.needs_confirmation.map((n) => <li key={n}>⚠️ {n}</li>)}
          </ul>
        </Card>
      )}
    </div>
  );
}
