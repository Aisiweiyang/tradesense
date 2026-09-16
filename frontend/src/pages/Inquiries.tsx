import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { get } from "../api/client";
import { Badge, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";

interface InquiryRow {
  id: number;
  title: string;
  status: string;
  stage: string;
  language: string;
  completeness: number;
  quality_flag: string;
  source_channel: string;
  customer_name: string;
  country: string;
  updated_at: string;
}

const STATUS_LABEL: Record<string, string> = {
  open: "新询盘", clarifying: "澄清中", quoted: "已报价",
  won: "已成交", lost: "已失败", spam: "垃圾",
};
const STAGE_LABEL: Record<string, string> = {
  new: "新询盘", qualified: "有效线索", clarifying: "澄清中", quoted: "已报价",
  sample: "寄样中", negotiating: "谈判中", won: "已成交", lost: "已失败", dormant: "休眠",
};
const CHANNEL_LABEL: Record<string, string> = {
  manual: "手动录入", email_imap: "邮箱", whatsapp_cloud: "WhatsApp",
  webform: "网站表单", generic_webhook: "Webhook", platform_csv: "平台导入",
};

export default function Inquiries() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") || 1);
  const q = params.get("q") || "";
  const status = params.get("status") || "";
  const stage = params.get("stage") || "";
  const [search, setSearch] = useState(q);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["inquiries", page, q, status, stage],
    queryFn: () =>
      get<{ items: InquiryRow[]; total: number }>(
        `/inquiries?page=${page}&page_size=15&q=${encodeURIComponent(q)}&status=${status}&stage=${stage}`,
      ),
  });

  function update(next: Record<string, string>) {
    const sp = new URLSearchParams(params);
    Object.entries(next).forEach(([k, v]) => (v ? sp.set(k, v) : sp.delete(k)));
    if (!("page" in next)) sp.delete("page");
    setParams(sp);
  }

  return (
    <div>
      <PageHeader
        title="询盘列表"
        desc="所有渠道进来的询盘都会汇总在这里"
        actions={
          <Link to="/inquiries/new" className="btn-primary">＋ 粘贴/录入询盘</Link>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <form
          onSubmit={(e) => { e.preventDefault(); update({ q: search }); }}
          className="flex gap-2"
        >
          <input className="input w-64" placeholder="搜索标题/内容…" value={search}
                 onChange={(e) => setSearch(e.target.value)} />
          <button className="btn-ghost">搜索</button>
        </form>
        <select className="input w-32" value={status} onChange={(e) => update({ status: e.target.value })}>
          <option value="">全部状态</option>
          {Object.entries(STATUS_LABEL).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
        <select className="input w-32" value={stage} onChange={(e) => update({ stage: e.target.value })}>
          <option value="">全部阶段</option>
          {Object.entries(STAGE_LABEL).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <Loading />
      ) : error ? (
        <ErrorState message={(error as Error).message} onRetry={refetch} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState icon="📩" text="还没有询盘。点击右上角「粘贴/录入询盘」开始" />
      ) : (
        <div className="card overflow-hidden">
          <table className="table-base">
            <thead>
              <tr>
                <th className="w-14">完整度</th>
                <th>询盘</th>
                <th className="w-28">客户</th>
                <th className="w-24">渠道</th>
                <th className="w-20">状态</th>
                <th className="w-20">阶段</th>
                <th className="w-36">更新时间</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((i) => (
                <tr key={i.id} className="hover:bg-slate-50">
                  <td>
                    <div className="flex items-center gap-1.5">
                      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-slate-100">
                        <div className={`h-full rounded-full ${i.completeness >= 70 ? "bg-emerald-500" : i.completeness >= 40 ? "bg-amber-500" : "bg-red-400"}`}
                             style={{ width: `${i.completeness}%` }} />
                      </div>
                      <span className="text-xs text-slate-400">{i.completeness}%</span>
                    </div>
                  </td>
                  <td>
                    <Link to={`/inquiries/${i.id}`} className="font-medium text-slate-700 hover:text-brand-600">
                      {i.title.slice(0, 60)}
                    </Link>
                    {i.quality_flag !== "normal" && (
                      <span className="ml-2"><Badge value={i.quality_flag} text={i.quality_flag === "low_quality" ? "低质量" : "疑似欺诈"} /></span>
                    )}
                    <div className="text-xs text-slate-400">#{i.id} · {i.language === "zh" ? "中文" : "英文"}</div>
                  </td>
                  <td>
                    <div className="text-sm text-slate-600">{i.customer_name || "—"}</div>
                    <div className="text-xs text-slate-400">{i.country}</div>
                  </td>
                  <td><Badge value={i.source_channel} text={CHANNEL_LABEL[i.source_channel] || i.source_channel} /></td>
                  <td><Badge value={i.status} text={STATUS_LABEL[i.status] || i.status} /></td>
                  <td className="text-xs text-slate-500">{STAGE_LABEL[i.stage] || i.stage}</td>
                  <td className="text-xs text-slate-400">{new Date(i.updated_at).toLocaleString("zh-CN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 pb-3">
            <Pagination page={page} pageSize={15} total={data.total} onPage={(p) => update({ page: String(p) })} />
          </div>
        </div>
      )}
    </div>
  );
}
