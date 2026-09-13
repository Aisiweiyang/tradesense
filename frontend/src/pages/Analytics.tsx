import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from "recharts";
import { get } from "../api/client";
import { Card, ErrorState, Loading, PageHeader } from "../components/ui";

interface Analytics {
  inquiry_total: number;
  stage_counts: Record<string, string | number>;
  channel_counts: Record<string, number>;
  completeness_buckets: Record<string, number>;
  quote_total: number;
  approved_quote_amount: number;
}

const STAGE_LABEL: Record<string, string> = {
  open: "新询盘", clarifying: "澄清中", quoted: "已报价", won: "已成交", lost: "已失败",
};
const CHANNEL_LABEL: Record<string, string> = {
  manual: "手动", email_imap: "邮箱", whatsapp_cloud: "WhatsApp", webform: "网站表单",
  generic_webhook: "Webhook",
};
const PIE_COLORS = ["#3b6fe0", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#64748b"];

export default function Analytics() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["analytics"],
    queryFn: () => get<Analytics>("/dashboard/analytics"),
  });
  if (isLoading) return <Loading />;
  if (error) return <ErrorState message={(error as Error).message} onRetry={refetch} />;
  const a = data!;
  const stageData = Object.entries(a.stage_counts).map(([k, v]) => ({ name: STAGE_LABEL[k] || k, value: v as number }));
  const channelData = Object.entries(a.channel_counts).map(([k, v]) => ({ name: CHANNEL_LABEL[k] || k, value: v }));
  const bucketData = Object.entries(a.completeness_buckets).map(([k, v]) => ({ name: k, 数量: v }));

  return (
    <div>
      <PageHeader title="数据看板" desc="询盘漏斗、渠道来源与信息完整度分布" />
      <div className="mb-4 grid grid-cols-3 gap-3">
        <div className="card p-4"><div className="text-2xl font-bold text-slate-800">{a.inquiry_total}</div><div className="text-xs text-slate-500">询盘总数</div></div>
        <div className="card p-4"><div className="text-2xl font-bold text-slate-800">{a.quote_total}</div><div className="text-xs text-slate-500">有效报价单</div></div>
        <div className="card p-4"><div className="text-2xl font-bold text-emerald-600">${a.approved_quote_amount.toFixed(0)}</div><div className="text-xs text-slate-500">已批准报价金额（内部统计）</div></div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Card title="询盘阶段分布">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={stageData}>
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="value" fill="#3b6fe0" radius={[6, 6, 0, 0]} name="数量" isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="渠道来源">
          {channelData.length === 0 ? <div className="py-16 text-center text-sm text-slate-400">暂无数据</div> : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={channelData} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={3} isAnimationActive={false}>
                  {channelData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Legend />
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="询盘信息完整度分布" className="col-span-2">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={bucketData}>
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="数量" fill="#10b981" radius={[6, 6, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
          <p className="mt-2 text-xs text-slate-400">完整度低于 40% 的询盘建议优先补充信息或发送目录引导。</p>
        </Card>
      </div>
    </div>
  );
}
