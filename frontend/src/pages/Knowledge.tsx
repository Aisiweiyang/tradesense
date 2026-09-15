import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { del, get, post, patch } from "../api/client";
import { Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";

interface KnowledgeItem {
  id: number;
  title: string;
  content: string;
  tags: string;
}

const emptyForm = { title: "", content: "", tags: "" };

export default function Knowledge() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<KnowledgeItem | "new" | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["knowledge", q],
    queryFn: () => get<{ items: KnowledgeItem[] }>(`/knowledge?q=${encodeURIComponent(q)}`),
  });

  const remove = useMutation({
    mutationFn: (id: number) => del(`/knowledge/${id}`),
    onSuccess: () => {
      setConfirmId(null);
      qc.invalidateQueries({ queryKey: ["knowledge"] });
    },
  });

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="知识库"
        desc="团队沉淀的外贸常识、认证与合规要点；生成回复草稿时可以引用"
        actions={<button className="btn-primary" onClick={() => setEditing("new")}>新建条目</button>}
      />

      <input
        className="input mb-4"
        placeholder="搜标题、内容或标签，如 LFGB、木包装、付款…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      {isLoading ? <Loading /> : error ? <ErrorState message={(error as Error).message} onRetry={refetch} /> :
        !data?.items.length ? (
          <EmptyState icon="📚" text={q ? "没有匹配的条目，换个关键词试试" : "知识库还是空的，点右上角新建第一条"} />
        ) : (
          <div className="space-y-3">
            {data.items.map((k) => (
              <Card
                key={k.id}
                title={k.title}
                extra={
                  <div className="flex items-center gap-1.5 text-xs">
                    <button className="btn-ghost px-2 py-0.5" onClick={() => setEditing(k)}>编辑</button>
                    {confirmId === k.id ? (
                      <>
                        <button className="btn-danger px-2 py-0.5" disabled={remove.isPending}
                                onClick={() => remove.mutate(k.id)}>确认删除</button>
                        <button className="btn-ghost px-2 py-0.5" onClick={() => setConfirmId(null)}>取消</button>
                      </>
                    ) : (
                      <button className="btn-ghost px-2 py-0.5 text-red-500 hover:bg-red-50"
                              onClick={() => setConfirmId(k.id)}>删除</button>
                    )}
                  </div>
                }
              >
                <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{k.content}</p>
                {k.tags && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {k.tags.split(",").filter(Boolean).map((tag) => (
                      <button key={tag}
                              className="rounded-full bg-brand-50 px-2 py-0.5 text-xs text-brand-600 hover:bg-brand-100"
                              onClick={() => setQ(tag.trim())} title={`搜索标签「${tag.trim()}」`}>
                        {tag.trim()}
                      </button>
                    ))}
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}

      {editing && (
        <EditorModal
          item={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function EditorModal({ item, onClose }: { item: KnowledgeItem | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(item ?? emptyForm);
  const [err, setErr] = useState("");

  const save = useMutation({
    mutationFn: () =>
      item ? patch(`/knowledge/${item.id}`, form) : post("/knowledge", form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["knowledge"] });
      onClose();
    },
    onError: (e) => setErr((e as Error).message),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
         onClick={onClose} data-testid="knowledge-editor">
      <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4 text-base font-bold text-slate-800">{item ? "编辑条目" : "新建知识条目"}</h2>
        <div className="space-y-3">
          <input className="input" placeholder="标题 *" value={form.title}
                 onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <textarea className="input min-h-40" placeholder="正文：写清楚适用场景和要点，回复草稿会引用这里的原文"
                    value={form.content}
                    onChange={(e) => setForm({ ...form, content: e.target.value })} />
          <input className="input" placeholder="标签（逗号分隔），如：欧盟,认证,LFGB" value={form.tags}
                 onChange={(e) => setForm({ ...form, tags: e.target.value })} />
        </div>
        {err && <p className="mt-2 text-xs text-red-500">{err}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>取消</button>
          <button className="btn-primary" disabled={!form.title.trim() || save.isPending}
                  onClick={() => save.mutate()}>
            {save.isPending ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
