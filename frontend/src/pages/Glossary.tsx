import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get } from "../api/client";
import { Card, EmptyState, Loading, PageHeader } from "../components/ui";

interface Term { term: string; zh: string; en: string }

export default function Glossary() {
  const [q, setQ] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["glossary", q],
    queryFn: () => get<{ items: Term[]; disclaimer: string }>(`/glossary?q=${encodeURIComponent(q)}`),
  });
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="外贸术语助手" desc="业务辅助说明，帮助新手快速理解 EXW / FOB / CIF / MOQ 等概念" />
      <input className="input mb-4" placeholder="搜索术语，如 FOB、MOQ、提单…" value={q} onChange={(e) => setQ(e.target.value)} />
      {isLoading ? <Loading /> : !data?.items.length ? <EmptyState icon="📖" text="没有匹配的术语" /> : (
        <div className="space-y-3">
          {data.items.map((t) => (
            <Card key={t.term} title={<span className="font-mono text-brand-600">{t.term}</span>}>
              <p className="text-sm leading-6 text-slate-700">{t.zh}</p>
              <p className="mt-1 text-xs leading-5 text-slate-400">{t.en}</p>
            </Card>
          ))}
          <div className="rounded-lg bg-amber-50 px-4 py-3 text-xs text-amber-700">ℹ️ {data.disclaimer}</div>
        </div>
      )}
    </div>
  );
}
