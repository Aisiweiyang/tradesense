import { useQuery } from "@tanstack/react-query";
import { Badge, Card, KV, Loading, PageHeader } from "../components/ui";

interface Health {
  status: string;
  database: string;
  ai_provider: string;
  ai_available: boolean;
  note: string;
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
