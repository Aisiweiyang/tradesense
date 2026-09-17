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

        {/* 右：登录表单 */}
        <div className="p-8">
          <div className="mb-6 text-center md:hidden">
            <div className="text-4xl">🌊</div>
            <h1 className="mt-2 text-2xl font-bold text-slate-800">TradeSense</h1>
          </div>
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
        </div>
      </div>
    </div>
  );
}
