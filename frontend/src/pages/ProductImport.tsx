import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Card, ErrorState, PageHeader } from "../components/ui";

interface PreviewRow {
  row_no: number; data: Record<string, string>; errors: string[]; warnings: string[];
  duplicate_of: number | null; valid: boolean;
}
interface Preview {
  token: string; file_name: string; total: number; valid: number; errors: number; duplicates: number;
  columns: string[]; mapping: Record<string, string>; suggested_mapping: Record<string, string>;
  standard_fields: string[];
  rows: PreviewRow[];
}

const FIELD_LABELS: Record<string, string> = {
  sku: "SKU", name_zh: "中文名", name_en: "英文名", category: "类别", description: "描述",
  material: "材质", spec: "规格", size: "尺寸", color: "颜色", packaging: "包装", moq: "MOQ",
  price_tiers: "阶梯价", currency: "币种", stock_status: "库存", lead_time_days: "交期",
  customization: "定制", certifications: "认证", supplier_name: "供应商", image_url: "图片",
  markets: "市场", unit_weight_kg: "单重kg",
};

export default function ProductImport() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<{ created: number; updated: number; failed: { row: number; errors: string[] }[] } | null>(null);
  const [error, setError] = useState("");

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api<Preview>("/imports/preview", { method: "POST", body: fd });
    },
    onSuccess: (p) => { setPreview(p); setResult(null); setError(""); },
    onError: (e) => setError(e instanceof Error ? e.message : "上传失败"),
  });
  const commit = useMutation({
    mutationFn: () => api<{ created: number; updated: number; failed: [] }>(`/imports/commit?token=${preview!.token}`, { method: "POST" }),
    onSuccess: (r) => { setResult(r); setPreview(null); },
    onError: (e) => setError(e instanceof Error ? e.message : "提交失败"),
  });

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="产品导入" desc="支持 CSV / Excel。先预览校验，确认后才会写入产品库"
        actions={<a className="btn-ghost" href="/api/imports/template" target="_blank" rel="noreferrer">⬇ 下载模板</a>} />

      <Card className="mb-4">
        <div
          className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 py-10 text-center hover:border-brand-400 hover:bg-brand-50/40"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const f = e.dataTransfer.files[0];
            if (f) upload.mutate(f);
          }}
        >
          <div className="text-3xl">📥</div>
          <div className="mt-2 text-sm text-slate-600">点击选择或拖拽 CSV / XLSX 文件到此处</div>
          <div className="mt-1 text-xs text-slate-400">自动识别中文表头（货号/品名/材质/阶梯价…），可先下载模板</div>
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xlsm" className="hidden"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); }} />
        </div>
        {upload.isPending && <div className="mt-3 text-center text-sm text-slate-400">解析中…</div>}
        {error && <ErrorState message={error} />}
      </Card>

      {result && (
        <Card className="mb-4" title="✅ 导入完成">
          <div className="flex gap-6 text-sm">
            <span>新建 <b className="text-emerald-600">{result.created}</b></span>
            <span>更新 <b className="text-brand-600">{result.updated}</b></span>
            <span>失败 <b className="text-red-500">{result.failed.length}</b></span>
          </div>
          <Link to="/products" className="btn-primary mt-3 inline-flex">前往产品列表 →</Link>
        </Card>
      )}

      {preview && (
        <>
          <Card className="mb-4" title="字段映射（识别结果，可核对）">
            <div className="flex flex-wrap gap-2 text-xs">
              {Object.entries(preview.mapping).map(([col, std]) => (
                <span key={col} className="rounded-full bg-brand-50 px-2.5 py-1 text-brand-600">
                  {col} → <b>{FIELD_LABELS[std] || std || "(未映射)"}</b>
                </span>
              ))}
              {preview.columns.filter((c) => !preview.mapping[c]).map((c) => (
                <span key={c} className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-400">{c} → 未映射</span>
              ))}
            </div>
          </Card>

          <Card title={`导入预览 · 共 ${preview.total} 行`}
                extra={
                  <div className="flex items-center gap-3 text-xs">
                    <span className="text-emerald-600">✓ 可导入 {preview.valid}</span>
                    <span className="text-red-500">✗ 错误 {preview.errors}</span>
                    <span className="text-amber-600">⇄ 更新已有 {preview.duplicates}</span>
                    <button className="btn-primary text-xs" disabled={preview.valid === 0 || commit.isPending}
                            onClick={() => commit.mutate()}>
                      {commit.isPending ? "导入中…" : `确认导入 ${preview.valid} 行`}
                    </button>
                  </div>
                }>
            <div className="max-h-96 overflow-auto">
              <table className="table-base text-xs">
                <thead><tr><th className="w-12">行号</th><th>SKU</th><th>名称</th><th>MOQ</th><th>价格</th><th>校验结果</th></tr></thead>
                <tbody>
                  {preview.rows.map((r) => (
                    <tr key={r.row_no} className={r.valid ? "" : "bg-red-50/40"}>
                      <td className="text-slate-400">{r.row_no}</td>
                      <td className="font-mono">{r.data.sku || "—"}</td>
                      <td>{r.data.name_zh || r.data.name_en || "—"}</td>
                      <td>{r.data.moq}</td>
                      <td className="font-mono">{r.data.price_tiers}</td>
                      <td>
                        {r.errors.map((e) => <div key={e} className="text-red-500">✗ {e}</div>)}
                        {r.warnings.map((w) => <div key={w} className="text-amber-500">△ {w}</div>)}
                        {r.valid && !r.warnings.length && <span className="text-emerald-500">✓ 通过</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-[10px] text-slate-400">
              仅「✓ 通过」的行会被导入；错误行会被跳过并在提交结果中列出；已有 SKU 会更新原产品。
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
