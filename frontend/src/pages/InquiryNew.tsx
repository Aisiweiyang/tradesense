import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { post } from "../api/client";
import { Card, ErrorState, PageHeader } from "../components/ui";

const SAMPLE = `Subject: Inquiry: insulated water bottles 500ml

Dear Sir or Madam,

We found your company online and are interested in your vacuum insulated
bottles. We need 5,000 pcs of 500ml double wall stainless steel bottles in
matte black with our logo printed. Could you quote FOB Hamburg? We target
a price around USD 4.5 per piece. Delivery within 45 days is required.
LFGB certification is mandatory for the German market.

Best regards,
Anna Schmidt
HausKonzept GmbH, Hamburg, Germany`;

export default function InquiryNew() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [source, setSource] = useState("manual");
  const [error, setError] = useState("");

  const create = useMutation({
    mutationFn: () => post<{ id: number }>("/inquiries", { text, source_channel: source }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["inquiries"] });
      nav(`/inquiries/${data.id}`);
    },
    onError: (e) => setError(e instanceof Error ? e.message : "创建失败"),
  });

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="粘贴 / 录入询盘"
        desc="把客户的英文询盘原样粘贴进来，系统会自动识别语言、生成中文摘要、提取结构化需求"
      />
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <label className="text-sm text-slate-500">来源渠道</label>
            <select className="input w-40" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="manual">手动录入</option>
              <option value="email_imap">邮件转发</option>
              <option value="whatsapp_cloud">WhatsApp</option>
              <option value="webform">网站表单</option>
              <option value="platform_csv">第三方平台</option>
            </select>
          </div>
          <button className="text-xs text-brand-500 hover:underline" onClick={() => setText(SAMPLE)}>
            填入示例询盘
          </button>
        </div>
        <textarea
          className="input min-h-72 font-mono text-[13px] leading-6"
          placeholder="在此粘贴客户询盘原文（英文/中文均可）…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {error && <ErrorState message={error} />}
        <div className="mt-4 flex items-center justify-between">
          <p className="text-xs text-slate-400">
            支持自动识别：产品、材质、数量、颜色、目的港、贸易术语、认证、交期、目标价…
          </p>
          <button
            className="btn-primary px-6"
            disabled={text.trim().length < 5 || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "解析中…" : "创建并解析"}
          </button>
        </div>
      </Card>
    </div>
  );
}
