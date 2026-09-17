import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { del, get, post, put, patch, ApiError } from "../api/client";
import { Badge, Card, KV, Loading, PageHeader } from "../components/ui";

interface Health {
  status: string;
  database: string;
  ai_provider: string;
  ai_available: boolean;
  note: string;
}

interface FxRate {
  id: number;
  pair: string;
  base_currency: string;
  quote_currency: string;
  rate: number;
  updated_by_name: string;
  updated_at: string;
}

function FxCard() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ base_currency: "", quote_currency: "", rate: "" });
  const [msg, setMsg] = useState("");
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["fx"],
    queryFn: () => get<{ items: FxRate[] }>("/fx"),
  });

  const save = useMutation({
    mutationFn: () => put("/fx", {
      base_currency: form.base_currency.trim().toUpperCase(),
      quote_currency: form.quote_currency.trim().toUpperCase(),
      rate: Number(form.rate),
    }),
    onSuccess: () => {
      setForm({ base_currency: "", quote_currency: "", rate: "" });
      setMsg("已保存。反向币种查询按倒数折算。");
      qc.invalidateQueries({ queryKey: ["fx"] });
    },
    onError: (e) => setMsg((e as Error).message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => del(`/fx/${id}`),
    onSuccess: () => {
      setConfirmId(null);
      qc.invalidateQueries({ queryKey: ["fx"] });
    },
  });

  if (error) {
    return (
      <Card title="汇率" className="mb-4">
        <p className="text-sm text-slate-400">
          {(error as ApiError).status === 403
            ? "汇率配置仅管理员（manager+）可见。报价时按此表折算成本币种。"
            : (error as Error).message}
        </p>
      </Card>
    );
  }

  return (
    <Card title="汇率（手工维护）" className="mb-4" extra={
      <span className="text-xs text-slate-400">报价时成本币种≠报价币种，优先用这里的汇率</span>
    }>
      {isLoading ? <Loading /> : (
        <>
          {data?.items.length ? (
            <table className="mb-3 w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs text-slate-400">
                  <th className="py-1.5 font-medium">币种对</th>
                  <th className="py-1.5 text-right font-medium">汇率</th>
                  <th className="py-1.5 text-right font-medium">更新人 / 时间</th>
                  <th className="py-1.5"></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id} className="border-b border-slate-50">
                    <td className="py-1.5 font-mono text-slate-700">{r.pair}</td>
                    <td className="py-1.5 text-right tabular-nums text-slate-700">
                      {r.rate < 0.01 ? r.rate.toExponential(4) : r.rate.toString()}
                    </td>
                    <td className="py-1.5 text-right text-xs text-slate-400">
                      {r.updated_by_name || "—"} · {new Date(r.updated_at).toLocaleString("zh-CN")}
                    </td>
                    <td className="py-1.5 text-right">
                      {confirmId === r.id ? (
                        <span className="inline-flex gap-1">
                          <button className="btn-danger px-2 py-0.5 text-xs" disabled={remove.isPending}
                                  onClick={() => remove.mutate(r.id)}>确认删除</button>
                          <button className="btn-ghost px-2 py-0.5 text-xs" onClick={() => setConfirmId(null)}>取消</button>
                        </span>
                      ) : (
                        <button className="btn-ghost px-2 py-0.5 text-xs text-red-500 hover:bg-red-50"
                                onClick={() => setConfirmId(r.id)}>删除</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="mb-3 text-sm text-slate-400">还没有配置汇率；不同币种报价会按 1:1 计算并在报价中提示缺失。</p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <input className="input w-24" placeholder="基准币种" value={form.base_currency}
                   onChange={(e) => setForm({ ...form, base_currency: e.target.value })} />
            <span className="text-slate-400">/</span>
            <input className="input w-24" placeholder="目标币种" value={form.quote_currency}
                   onChange={(e) => setForm({ ...form, quote_currency: e.target.value })} />
            <span className="text-slate-400">=</span>
            <input className="input w-28" placeholder="汇率，如 7.2" value={form.rate}
                   onChange={(e) => setForm({ ...form, rate: e.target.value })} />
            <button className="btn-primary" disabled={save.isPending || !form.base_currency.trim()
                     || !form.quote_currency.trim() || !(Number(form.rate) > 0)}
                    onClick={() => save.mutate()}>
              {save.isPending ? "保存中…" : "保存"}
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            {msg || "填 1 基准币种兑多少目标币种，如 USD / CNY = 7.2。币种对会按字母序规范存储，反向查询自动取倒数。"}
          </p>
        </>
      )}
    </Card>
  );
}

interface AiStatus { provider: string; available: boolean; intake_enabled: boolean }

function AiCard() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => get<{ id: number; role: string }>("/auth/me"),
                        staleTime: 5 * 60 * 1000 });
  const st = useQuery({ queryKey: ["ai-status"], queryFn: () => get<AiStatus>("/ai/status") });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => put("/ai/settings", { intake_enabled: enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-status"] }),
  });
  const isOwner = me.data?.role === "owner";
  return (
    <Card title="AI Intake（询盘自动解析）" className="mb-4"
          extra={<span className="text-xs text-slate-400">AI 只提议字段，需求状态机裁决，人工确认</span>}>
      {st.isLoading ? <Loading /> : st.error ? (
        <p className="text-sm text-slate-400">{(st.error as Error).message}</p>
      ) : (
        <>
          <KV label="AI 提供方">{st.data?.provider === "none" ? "未配置（规则解析模式）" : String(st.data?.provider)}</KV>
          <KV label="Intake 状态">
            {st.data?.available
              ? (st.data.intake_enabled
                  ? <Badge value="active" text="已启用" />
                  : <Badge value="draft" text="已关闭（走规则解析）" />)
              : <Badge value="unknown" text="AI 未配置，规则解析" />}
          </KV>
          {isOwner && st.data?.available && (
            <div className="mt-2 flex gap-2">
              <button className="btn-primary text-xs" disabled={st.data.intake_enabled || toggle.isPending}
                      onClick={() => toggle.mutate(true)}>启用</button>
              <button className="btn-ghost text-xs" disabled={!st.data.intake_enabled || toggle.isPending}
                      onClick={() => toggle.mutate(false)}>关闭</button>
            </div>
          )}
          <p className="mt-2 text-xs leading-5 text-slate-400">
            启用后：新建询盘、渠道收信、上传附件时会由 AI 补充识别字段（附原文依据），
            经需求状态机裁决后落库——锁定字段不会被覆盖，低置信字段进入待确认。
            无 AI 时全部功能照常。
          </p>
        </>
      )}
    </Card>
  );
}

interface ManagedUser { id: number; email: string; name: string; role: string; is_active: boolean }

const ROLE_ZH: Record<string, string> = {
  owner: "管理员", manager: "经理", member: "业务员", viewer: "只读",
};

function UsersCard() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => get<{ id: number; role: string }>("/auth/me"),
                        staleTime: 5 * 60 * 1000 });
  const isOwner = me.data?.role === "owner";
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => get<{ items: ManagedUser[] }>("/users"),
    enabled: isOwner,
  });
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "member" });
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [resetId, setResetId] = useState<number | null>(null);

  const create = useMutation({
    mutationFn: () => post("/users", form),
    onSuccess: () => {
      setForm({ name: "", email: "", password: "", role: "member" });
      setErr(""); setMsg("已创建账号，初始密码即对方登录密码。");
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e) => { setMsg(""); setErr((e as Error).message); },
  });
  const patchUser = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => patch(`/users/${id}`, body),
    onSuccess: () => { setErr(""); qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => setErr((e as Error).message),
  });
  if (!isOwner) return null;

  return (
    <Card title="用户管理" className="mb-4"
          extra={<span className="text-xs text-slate-400">组织至少保留一名可登录的 owner</span>}>
      <table className="mb-4 w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100 text-left text-xs text-slate-400">
            <th className="py-1.5 font-medium">成员</th>
            <th className="py-1.5 font-medium">角色</th>
            <th className="py-1.5 font-medium">状态</th>
            <th className="py-1.5"></th>
          </tr>
        </thead>
        <tbody>
          {(users.data?.items || []).map((u) => (
            <tr key={u.id} className="border-b border-slate-50">
              <td className="py-1.5">
                <div className="font-medium text-slate-700">{u.name}</div>
                <div className="text-xs text-slate-400">{u.email}</div>
              </td>
              <td className="py-1.5">
                <select className="input w-24 px-2 py-1 text-xs" value={u.role}
                        disabled={u.id === me.data?.id || patchUser.isPending}
                        onChange={(e) => patchUser.mutate({ id: u.id, body: { role: e.target.value } })}>
                  {Object.entries(ROLE_ZH).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </td>
              <td className="py-1.5">
                <Badge value={u.is_active ? "active" : "cancelled"} text={u.is_active ? "正常" : "已停用"} />
              </td>
              <td className="py-1.5 text-right whitespace-nowrap">
                {u.id !== me.data?.id && (
                  <>
                    <button className="btn-ghost px-2 py-0.5 text-xs" onClick={() => {
                      const pw = window.prompt(`为 ${u.name} 设置新密码（至少 8 位）`);
                      if (pw && pw.length >= 8) patchUser.mutate({ id: u.id, body: { password: pw } });
                    }}>重置密码</button>
                    {u.is_active ? (
                      <button className="btn-ghost ml-1 px-2 py-0.5 text-xs text-red-500 hover:bg-red-50"
                              onClick={() => patchUser.mutate({ id: u.id, body: { is_active: false } })}>停用</button>
                    ) : (
                      <button className="btn-ghost ml-1 px-2 py-0.5 text-xs"
                              onClick={() => patchUser.mutate({ id: u.id, body: { is_active: true } })}>启用</button>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="rounded-lg bg-slate-50 p-3">
        <div className="mb-2 text-xs font-medium text-slate-500">添加成员</div>
        <div className="flex flex-wrap items-center gap-2">
          <input className="input w-28" placeholder="姓名" value={form.name}
                 onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className="input w-48" placeholder="邮箱" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="input w-32" type="password" placeholder="初始密码（≥8 位）" value={form.password}
                 onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <select className="input w-24" value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {Object.entries(ROLE_ZH).filter(([v]) => v !== "owner").map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
          <button className="btn-primary" disabled={create.isPending || !form.name.trim()
                   || !form.email.trim() || form.password.length < 8}
                  onClick={() => create.mutate()}>
            {create.isPending ? "创建中…" : "添加"}
          </button>
        </div>
        {err && <p className="mt-2 text-xs text-red-500">{err}</p>}
        {msg && <p className="mt-2 text-xs text-emerald-600">{msg}</p>}
      </div>
    </Card>
  );
}

function PasswordCard() {
  const [form, setForm] = useState({ old_password: "", new_password: "", confirm: "" });
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const save = useMutation({
    mutationFn: () => post("/auth/change-password", {
      old_password: form.old_password, new_password: form.new_password,
    }),
    onSuccess: () => {
      setForm({ old_password: "", new_password: "", confirm: "" });
      setErr("");
      setMsg("密码已更新，下次登录请使用新密码。");
    },
    onError: (e) => setErr((e as Error).message),
  });
  const mismatch = form.confirm !== form.new_password && form.confirm !== "";
  return (
    <Card title="修改密码" className="mb-4">
      <div className="grid max-w-md gap-2">
        <input className="input" type="password" placeholder="当前密码" autoComplete="current-password"
               value={form.old_password}
               onChange={(e) => setForm({ ...form, old_password: e.target.value })} />
        <input className="input" type="password" placeholder="新密码（至少 8 位）" autoComplete="new-password"
               value={form.new_password}
               onChange={(e) => setForm({ ...form, new_password: e.target.value })} />
        <input className="input" type="password" placeholder="再输一遍新密码" autoComplete="new-password"
               value={form.confirm}
               onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
        {mismatch && <p className="text-xs text-red-500">两次输入的新密码不一致</p>}
        {err && <p className="text-xs text-red-500">{err}</p>}
        {msg && <p className="text-xs text-emerald-600">{msg}</p>}
        <button className="btn-primary justify-center"
                disabled={!form.old_password || form.new_password.length < 8 || mismatch || save.isPending}
                onClick={() => save.mutate()}>
          {save.isPending ? "提交中…" : "更新密码"}
        </button>
      </div>
    </Card>
  );
}

export default function Settings() {
  const h = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const r = await fetch("/api/health");
      return (await r.json()) as Health;
    },
  });

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="设置" desc="系统运行状态与接入说明" />
      <AiCard />
      <UsersCard />
      <PasswordCard />
      <FxCard />
      <Card title="系统状态" className="mb-4">
        {h.isLoading ? <Loading /> : (
          <>
            <KV label="运行状态">{String(h.data?.status)}</KV>
            <KV label="数据库">{String(h.data?.database)}</KV>
            <KV label="AI 提供方">
              {String(h.data?.ai_provider)}{" "}
              {h.data?.ai_available
                ? <Badge value="active" text="可用" />
                : <Badge value="unknown" text="未配置（确定性模式）" />}
            </KV>
            <p className="mt-2 text-xs leading-5 text-slate-400">{String(h.data?.note || "")}</p>
          </>
        )}
      </Card>
      <Card title="AI 接入（可选）" className="mb-4">
        <p className="text-sm leading-6 text-slate-600">
          TradeSense 无 AI 时全部核心功能可用。如需启用摘要润色等增强能力，在 backend/.env 中配置：
        </p>
        <pre className="mt-2 rounded-lg bg-slate-900 p-3 text-xs leading-5 text-slate-100">{`AI_PROVIDER=openai_compat      # 或 ollama / none
OPENAI_BASE_URL=https://api.xxx.com/v1
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4o-mini
# 本地模型（无需密钥）：
# AI_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=qwen2.5:7b`}</pre>
        <p className="mt-2 text-xs text-slate-400">
          AI 输出仅作为建议（必须人工确认），不会编造价格/认证/交期，也不会修改确定性报价。
        </p>
      </Card>
      <Card title="账号与数据">
        <KV label="数据隔离">所有业务数据按组织隔离，跨组织访问一律 404</KV>
        <KV label="密码">PBKDF2-SHA256 哈希存储</KV>
        <KV label="正式输出">报价需人工批准、回复需人工批准后自行发送</KV>
      </Card>
    </div>
  );
}
