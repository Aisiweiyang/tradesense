import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post, del } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";

interface Acct {
  id: number; connector_type: string; name: string; mode: string; status: string;
  auth_state: string; last_sync_at: string | null; last_error: string; label: string;
  live_supported: boolean; env_keys: string[]; config_nonsecret: Record<string, string>;
}
interface TypeMeta {
  type: string; label: string; channel: string; required_config: string[];
  env_keys: string[]; live_supported: boolean; description: string;
}

export default function Connectors() {
  const qc = useQueryClient();
  const [adding, setAdding] = useState<string | null>(null);
  const [cfg, setCfg] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const types = useQuery({ queryKey: ["connector-types"], queryFn: () => get<{ items: TypeMeta[] }>("/connectors/types") });
  const accounts = useQuery({ queryKey: ["connectors"], queryFn: () => get<{ items: Acct[] }>("/connectors") });
  const create = useMutation({
    mutationFn: (type: string) => post("/connectors", { connector_type: type, name: name || type, config: cfg }),
    onSuccess: () => { setAdding(null); setCfg({}); setName(""); qc.invalidateQueries({ queryKey: ["connectors"] }); },
  });
  const op = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) => post(`/connectors/${id}/${action}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connectors"] }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => del(`/connectors/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connectors"] }),
  });

  return (
    <div>
      <PageHeader title="渠道连接中心" desc="所有渠道进入统一的询盘模型；缺少凭据时使用明确标注的模拟连接器" />
      {(op.error || remove.error) && (
        <div role="alert" className="mb-3 text-sm text-red-600">{((op.error || remove.error) as Error).message}</div>
      )}
      {accounts.isLoading || types.isLoading ? <Loading /> : accounts.error || types.error ? (
        <ErrorState message={((accounts.error || types.error) as Error).message}
                    onRetry={() => { accounts.refetch(); types.refetch(); }} />
      ) : (
        <>
          <div className="mb-5 grid grid-cols-2 gap-4">
            {accounts.data!.items.map((a) => (
              <Card key={a.id} title={a.name}
                    extra={
                      <div className="flex items-center gap-1.5">
                        <Badge value={a.mode} text={a.mode === "simulated" ? "模拟" : "真实模式"} />
                        <Badge value={a.status} text={a.status === "error" ? "错误"
                          : a.mode === "simulated" ? (a.status === "connected" ? "模拟可用" : "未测试")
                          : a.auth_state !== "authorized" ? "待验证"
                          : a.status === "connected" ? "已连接" : "未连接"} />
                      </div>
                    }>
                <div className="text-xs text-slate-500">
                  <div className="mb-1.5">
                    <span className="mr-1 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px]">{a.connector_type}</span>
                    {a.mode === "simulated" && (
                      <span className="text-amber-600">未真实授权 · 使用内置模拟数据演示同步</span>
                    )}
                    {a.mode === "live" && a.auth_state !== "authorized" && (
                      <span className="text-amber-600">请测试连接，验证通过后再同步</span>
                    )}
                  </div>
                  {a.live_supported && a.env_keys.length > 0 && (
                    <div className="text-slate-400">接入真实账号需配置环境变量：{a.env_keys.join(", ")}</div>
                  )}
                  {a.last_sync_at && <div className="mt-1 text-slate-400">最近同步 {new Date(a.last_sync_at).toLocaleString("zh-CN")}</div>}
                  {a.last_error && <div className="mt-1 rounded bg-red-50 p-1.5 text-red-500">⚠ {a.last_error}</div>}
                </div>
                <div className="mt-3 flex gap-2">
                  <button className="btn-ghost text-xs" onClick={() => op.mutate({ id: a.id, action: "test" })} disabled={op.isPending}>测试连接</button>
                  <button className="btn-primary text-xs" onClick={() => op.mutate({ id: a.id, action: "sync" })} disabled={op.isPending}>立即同步</button>
                  <a className="btn-ghost text-xs" href="/sync-logs">日志</a>
                  <button className="btn-danger text-xs" onClick={() => remove.mutate(a.id)}>删除</button>
                </div>
              </Card>
            ))}
            {accounts.data!.items.length === 0 && <EmptyState icon="🔌" text="还没有配置任何渠道" />}
          </div>

          <Card title="添加新渠道">
            <div className="grid grid-cols-3 gap-3">
              {types.data!.items.map((t) => (
                <div key={t.type} className="rounded-xl border border-slate-200 p-3">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium text-slate-700">{t.label}</div>
                    {adding === t.type ? (
                      <button className="text-xs text-slate-400" onClick={() => setAdding(null)}>收起</button>
                    ) : (
                      <button className="text-xs text-brand-500 hover:underline" onClick={() => { setAdding(t.type); setCfg({}); setName(t.label); }}>添加</button>
                    )}
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-400">{t.description}</p>
                  {adding === t.type && (
                    <div className="mt-3 space-y-2">
                      <input className="input py-1 text-xs" placeholder="账号名称" value={name} onChange={(e) => setName(e.target.value)} />
                      {t.required_config.map((k) => (
                        <input key={k} className="input py-1 text-xs" placeholder={k}
                               onChange={(e) => setCfg({ ...cfg, [k]: e.target.value })} />
                      ))}
                      {t.live_supported ? (
                        <p className="text-[10px] leading-4 text-slate-400">
                          真实模式需要环境变量：{t.env_keys.join(", ") || "无"}。邮箱配置完成后需测试连接；缺少配置时使用模拟模式。
                        </p>
                      ) : (
                        <p className="text-[10px] text-slate-400">该类型通过接口推送接入（Webhook/表单）。</p>
                      )}
                      <button className="btn-primary w-full justify-center text-xs" disabled={create.isPending}
                              onClick={() => create.mutate(t.type)}>创建</button>
                      {create.error && <div className="text-[10px] text-red-500">{(create.error as Error).message}</div>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
