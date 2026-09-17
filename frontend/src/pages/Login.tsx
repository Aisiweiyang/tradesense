import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { get, post, setToken } from "../api/client";
import { Loading } from "../components/ui";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-brand-50 via-slate-50 to-slate-100 p-6">
      {/* 背景装饰：两个柔和光斑 */}
      <div className="pointer-events-none absolute -top-24 -left-24 h-96 w-96 rounded-full bg-brand-200/40 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 -right-16 h-[28rem] w-[28rem] rounded-full bg-emerald-200/30 blur-3xl" />

      <div className="relative grid w-full max-w-3xl overflow-hidden rounded-2xl bg-white shadow-xl ring-1 ring-slate-900/5 md:grid-cols-2">
        {/* 左：品牌与卖点 */}
        <div className="hidden flex-col justify-between bg-gradient-to-br from-brand-600 to-brand-800 p-8 text-white md:flex">
          <div>
            <div className="text-3xl">🌊</div>
            <h1 className="mt-3 text-2xl font-bold">TradeSense</h1>
            <p className="mt-1 text-sm text-brand-100">外贸询盘 · 客户跟进 · 报价辅助</p>
          </div>
          <ul className="space-y-2.5 text-sm text-brand-50">
            <li>📩 多渠道询盘自动解析成结构化需求</li>
            <li>💰 报价由程序计算，每一行有来源</li>
            <li>🚢 单证核验与复核包，异常有证据</li>
            <li>🔒 数据按组织隔离，系统永不代替你发送</li>
          </ul>
          <p className="text-xs text-brand-200">AI 只提供建议，人工确认才算数</p>
        </div>
        <div className="p-8">{children}</div>
      </div>
    </div>
  );
}

function LoginForm({ error, busy, submit }: {
  error: string; busy: boolean; submit: (e: React.FormEvent<HTMLFormElement>) => void;
}) {
  const [email, setEmail] = useState("demo@tradesense-demo.cn");
  const [password, setPassword] = useState("");
  return (
    <>
      <h2 className="mb-5 text-lg font-bold text-slate-800">登录工作台</h2>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="label" htmlFor="email">邮箱</label>
          <input id="email" className="input" type="email" required value={email}
                 onChange={(e) => setEmail(e.target.value)} placeholder="you@company.cn" />
        </div>
        <div>
          <label className="label" htmlFor="password">密码</label>
          <input id="password" className="input" type="password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
        </div>
        {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
        <button className="btn-primary w-full justify-center py-2.5" disabled={busy}>
          {busy ? "登录中…" : "登录"}
        </button>
      </form>
      <div className="mt-5 rounded-lg bg-slate-50 p-3 text-center text-xs text-slate-500">
        演示账号：<span className="font-mono">demo@tradesense-demo.cn</span> /{" "}
        <span className="font-mono">demo1234</span>
      </div>
    </>
  );
}

function BootstrapForm({ error, busy, submit }: {
  error: string; busy: boolean; submit: (e: React.FormEvent<HTMLFormElement>) => void;
}) {
  const [orgName, setOrgName] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  return (
    <>
      <h2 className="mb-1 text-lg font-bold text-slate-800">初始化系统</h2>
      <p className="mb-5 text-xs leading-5 text-slate-400">
        检测到还没有任何账号。创建你的公司与管理员账号——这一步只在首次使用时出现。
      </p>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="label" htmlFor="org_name">公司 / 团队名称</label>
          <input id="org_name" className="input" required maxLength={200} value={orgName}
                 onChange={(e) => setOrgName(e.target.value)} placeholder="例如：宏达外贸" />
        </div>
        <div>
          <label className="label" htmlFor="name">管理员姓名</label>
          <input id="name" className="input" required maxLength={100} value={name}
                 onChange={(e) => setName(e.target.value)} placeholder="你的名字" />
        </div>
        <div>
          <label className="label" htmlFor="b_email">管理员邮箱</label>
          <input id="b_email" className="input" type="email" required value={email}
                 onChange={(e) => setEmail(e.target.value)} placeholder="you@company.cn" />
        </div>
        <div>
          <label className="label" htmlFor="b_password">密码（至少 8 位）</label>
          <input id="b_password" className="input" type="password" required minLength={8} value={password}
                 onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
        </div>
        {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
        <button className="btn-primary w-full justify-center py-2.5" disabled={busy}>
          {busy ? "创建中…" : "创建并进入"}
        </button>
      </form>
    </>
  );
}

export default function Login() {
  const nav = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const status = useQuery({
    queryKey: ["auth-status"],
    queryFn: () => get<{ needs_bootstrap: boolean }>("/auth/status"),
    retry: false,
  });

  const login = useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      post<{ access_token: string }>("/auth/login", body),
    onSuccess: (r) => { setToken(r.access_token); nav("/"); },
    onError: (e) => setError(e instanceof Error ? e.message : "登录失败"),
    onSettled: () => setBusy(false),
  });
  const bootstrap = useMutation({
    mutationFn: (body: { org_name: string; name: string; email: string; password: string }) =>
      post<{ access_token: string }>("/auth/bootstrap", body),
    onSuccess: (r) => { setToken(r.access_token); nav("/"); },
    onError: (e) => setError(e instanceof Error ? e.message : "初始化失败"),
    onSettled: () => setBusy(false),
  });

  if (status.isLoading) return <Shell><Loading /></Shell>;

  const needsBootstrap = status.data?.needs_bootstrap === true;
  const handleSubmit = (fn: typeof login | typeof bootstrap, read: (f: FormData) => Record<string, string>) =>
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      setBusy(true);
      setError("");
      fn.mutate(read(new FormData(e.currentTarget)) as never);
    };

  return (
    <Shell>
      {needsBootstrap ? (
        <BootstrapForm error={error} busy={busy}
          submit={handleSubmit(bootstrap, (f) => ({
            org_name: String(f.get("org_name") || ""),
            name: String(f.get("name") || ""),
            email: String(f.get("b_email") || ""),
            password: String(f.get("b_password") || ""),
          }))} />
      ) : (
        <LoginForm error={error} busy={busy}
          submit={handleSubmit(login, (f) => ({
            email: String(f.get("email") || ""),
            password: String(f.get("password") || ""),
          }))} />
      )}
    </Shell>
  );
}
