import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend, LabelList } from "recharts";
import { get } from "../api/client";
import { Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";

interface Analytics {
  inquiry_total: number;
  stage_counts: Record<string, string | number>;
  channel_counts: Record<string, number>;
  completeness_buckets: Record<string, number>;
  quote_total: number;
  approved_quote_amount: number;
}

interface FunnelStage {
  stage: string;
  label: string;
  count: number;
  reached: number;
  conversion_to_next: number | null;
  next_stage: string | null;
  median_dwell_hours: number | null;
}

interface Insights {
  channels: { channel: string; total: number; reached_quoted: number; conversion: number | null }[];
  first_response: { median_hours: number | null; responded: number; waiting: number; longest_waiting_hours: number | null };
  target_hit: { hit: number; total: number; rate: number | null };
}

const STAGE_LABEL: Record<string, string> = {
  open: "新询盘", clarifying: "澄清中", quoted: "已报价", won: "已成交", lost: "已失败",
};
const CHANNEL_LABEL: Record<string, string> = {
  manual: "手动", email_imap: "邮箱", whatsapp_cloud: "WhatsApp", webform: "网站表单",
  generic_webhook: "Webhook",
};
const PIE_COLORS = ["#3b6fe0", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#64748b"];

// 主链按漏斗顺序展示，lost/dormant 是分支终态，放图外
const MAIN_CHAIN = ["new", "qualified", "clarifying", "quoted", "sample", "negotiating", "won"];
// 主链配色：蓝 → 绿渐进，成交收尾用深绿
const CHAIN_COLORS = ["#60a5fa", "#4f9bef", "#3b8ee6", "#3b82d6", "#2f9fc9", "#10b981", "#059669"];

function fmtHours(h: number | null): string {
  if (h == null) return "—";
  if (h < 72) return `${Math.round(h)} 小时`;
  return `${(h / 24).toFixed(1)} 天`;
}

function fmtConv(c: number | null): string {
  return c == null ? "—" : `${Math.round(c * 100)}%`;
}

const CHANNEL_ZH: Record<string, string> = {
  manual: "手动", email_imap: "邮箱", whatsapp_cloud: "WhatsApp",
  webform: "网站表单", generic_webhook: "Webhook", platform_csv: "平台导入",
};

function InsightsCard() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["insights"],
    queryFn: () => get<Insights>("/analytics/insights"),
  });
  if (isLoading) return <Card title="渠道与响应"><Loading text="统计中…" /></Card>;
  if (error) return <Card title="渠道与响应"><ErrorState message={(error as Error).message} onRetry={refetch} /></Card>;
  const fr = data!.first_response;
  const hit = data!.target_hit;
  return (
    <Card title="渠道与响应" extra={
      <span className="text-xs text-slate-400">触达已报价口径，与漏斗一致</span>
    }>
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg bg-slate-50 p-3 text-center">
          <div className="text-xl font-bold text-slate-800">{fr.median_hours == null ? "—" : fmtHours(fr.median_hours)}</div>
          <div className="mt-0.5 text-xs text-slate-500">首响中位数（已响 {fr.responded}）</div>
        </div>
        <div className="rounded-lg bg-slate-50 p-3 text-center">
          <div className="text-xl font-bold text-amber-600">{fr.waiting}</div>
          <div className="mt-0.5 text-xs text-slate-500">
            待响应{fr.longest_waiting_hours != null ? ` · 最长已等 ${fmtHours(fr.longest_waiting_hours)}` : ""}
          </div>
        </div>
        <div className="rounded-lg bg-slate-50 p-3 text-center">
          <div className="text-xl font-bold text-emerald-600">{hit.rate == null ? "—" : `${Math.round(hit.rate * 100)}%`}</div>
          <div className="mt-0.5 text-xs text-slate-500">目标价达成（{hit.hit}/{hit.total} 单）</div>
        </div>
      </div>
      {data!.channels.length === 0 ? (
        <div className="mt-3 py-6 text-center text-sm text-slate-400">还没有询盘进入漏斗</div>
      ) : (
        <div className="mt-3 space-y-1.5">
          {data!.channels.map((ch) => (
            <div key={ch.channel} className="flex items-center gap-2 text-xs">
              <span className="w-20 shrink-0 text-slate-500">{CHANNEL_ZH[ch.channel] || ch.channel}</span>
              <div className="h-3 flex-1 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-brand-500"
                     style={{ width: `${Math.round((ch.conversion ?? 0) * 100)}%` }} />
              </div>
              <span className="w-24 shrink-0 text-right tabular-nums text-slate-500">
                {ch.reached_quoted}/{ch.total} · {ch.conversion == null ? "—" : `${Math.round(ch.conversion * 100)}%`}
              </span>
            </div>
          ))}
        </div>
      )}
      <p className="mt-2 text-xs leading-relaxed text-slate-400">
        首响 = 询盘创建到我方第一条回复；待响应的按"至今"截断单独计，不进中位数。目标达成只统计有目标价的已批准报价。
      </p>
    </Card>
  );
}

function FunnelCard() {
  const [selected, setSelected] = useState<string | null>(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["funnel"],
    queryFn: () => get<{ stages: FunnelStage[] }>("/analytics/funnel"),
  });
  if (isLoading) return <Card title="销售漏斗"><Loading text="漏斗计算中…" /></Card>;
  if (error) return <Card title="销售漏斗"><ErrorState message={(error as Error).message} onRetry={refetch} /></Card>;

  const byStage = new Map(data!.stages.map((s) => [s.stage, s]));
  const chain = MAIN_CHAIN.map((s) => byStage.get(s)!);
  const branches = data!.stages.filter((s) => !MAIN_CHAIN.includes(s.stage));
  const totalReached = chain.reduce((n, s) => n + s.reached, 0);
  if (totalReached === 0) {
    return (
      <Card title="销售漏斗">
        <EmptyState icon="📊" text="还没有询盘进入漏斗。询盘创建后会自动记录阶段流转。" />
      </Card>
    );
  }
  const sel = selected ? byStage.get(selected) : null;

  return (
    <Card
      title="销售漏斗"
      extra={
        <span className="flex items-center gap-2 text-xs text-slate-400">
          {branches.map((b) => (
            <span key={b.stage} className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-500">
              {b.label} {b.count}
            </span>
          ))}
        </span>
      }
    >
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chain} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 8 }}
                  barSize={18}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="label" width={64} tick={{ fontSize: 12, fill: "#475569" }}
                 axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: "rgba(148,163,184,0.08)" }}
            formatter={(value: number, _name, item) => {
              const s = item.payload as FunnelStage;
              return [`触达 ${s.reached} 个（当前停留 ${s.count}）`, s.label];
            }}
            contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
          />
          <Bar dataKey="reached" radius={[4, 8, 8, 4]} isAnimationActive={false}
               onClick={(_d, i) => setSelected(chain[i].stage === selected ? null : chain[i].stage)}
               className="cursor-pointer">
            {chain.map((_, i) => <Cell key={i} fill={CHAIN_COLORS[i]} fillOpacity={selected == null || selected === chain[i].stage ? 1 : 0.35} />)}
            <LabelList dataKey="reached" position="right" offset={8} formatter={(v: number) => (v > 0 ? v : "")}
                       style={{ fill: "#64748b", fontSize: 11 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <table className="mt-1 w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100 text-left text-xs text-slate-400">
            <th className="py-1.5 font-medium">阶段</th>
            <th className="py-1.5 text-right font-medium">触达</th>
            <th className="py-1.5 text-right font-medium">停留中</th>
            <th className="py-1.5 text-right font-medium">转化到下一阶段</th>
            <th className="py-1.5 text-right font-medium">停留时长中位数</th>
          </tr>
        </thead>
        <tbody>
          {chain.map((s) => (
            <tr key={s.stage} onClick={() => setSelected(s.stage === selected ? null : s.stage)}
                className={`cursor-pointer border-b border-slate-50 transition-colors hover:bg-slate-50 ${selected === s.stage ? "bg-brand-50/60" : ""}`}>
              <td className="py-1.5">
                <span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: CHAIN_COLORS[MAIN_CHAIN.indexOf(s.stage)] }} />
                {s.label}
              </td>
              <td className="py-1.5 text-right tabular-nums text-slate-700">{s.reached}</td>
              <td className="py-1.5 text-right tabular-nums text-slate-500">{s.count}</td>
              <td className="py-1.5 text-right tabular-nums">
                <span className={s.conversion_to_next != null && s.conversion_to_next >= 0.5 ? "text-emerald-600" : "text-slate-600"}>
                  {fmtConv(s.conversion_to_next)}
                </span>
              </td>
              <td className="py-1.5 text-right tabular-nums text-slate-600">{fmtHours(s.median_dwell_hours)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="mt-2 text-xs leading-relaxed text-slate-400">
        {sel
          ? <>「{sel.label}」：历史上有 {sel.reached} 个询盘进入过该阶段，{sel.count} 个仍停留在这里。
             {sel.next_stage
               ? <>推进到「{byStage.get(sel.next_stage)?.label}」的比例为 {fmtConv(sel.conversion_to_next)}。</>
               : <>这是主链终点，成交即归档。</>}
             停留时长按进入该阶段到离开（或至今）计算，仍在阶段的按当前时刻截断，中位数是保守下界。</>
          : <>触达 = 曾进入过该阶段的询盘数；点击任一阶段查看口径说明。停留时长仍在计时的询盘按"至今"截断，属右删失的保守估计。</>}
      </p>
    </Card>
  );
}

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
        <FunnelCard />
        <InsightsCard />
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
