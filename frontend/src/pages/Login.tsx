import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { post, setToken } from "../api/client";

export default function Login() {
  const nav = useNavigate();
  const [email, setEmail] = useState("demo@tradesense-demo.cn");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await post<{ access_token: string }>("/auth/login", { email, password });
      setToken(r.access_token);
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-slate-100 p-6">
      <div className="card w-full max-w-md p-8">
        <div className="mb-6 text-center">
          <div className="text-4xl">🌊</div>
          <h1 className="mt-2 text-2xl font-bold text-slate-800">TradeSense</h1>
          <p className="mt-1 text-sm text-slate-500">外贸询盘 · 客户跟进 · 产品匹配 · 报价辅助</p>
        </div>
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
      </div>
    </div>
  );
}
