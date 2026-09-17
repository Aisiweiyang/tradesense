# 23 · AI Intake（询盘自动解析）

第十步引入的能力：让邮件原文、附件里的需求自动变成结构化字段，人从"录入员"变成"确认员"。

## 定位与红线

AI 只**提议**字段，`requirement_engine.apply_updates` 是唯一裁决者——与消息解析走完全相同的路径：

- 锁定字段不被覆盖（引擎产生 `locked_ignored` 记录）；
- 矛盾标记 conflicting、低置信（<0.75）进待确认；
- 价格 100% 程序计算，AI 不参与定价；系统永不自动发送；
- AI 不可用/超时/返回垃圾：回退纯规则提取，一切功能照旧。

## 管线

```
文本来源（三选一或合并）
  ├─ 新建询盘粘贴的正文
  ├─ 渠道收信（模拟邮箱/webhook，ingestion 钩子）
  └─ 附件（PDF 文本层 pdfplumber 提取；扫描件/图片无 AI 时"待人工"）
        ↓ services/ai/intake.propose_slots
   LLM 输出 JSON：字段白名单硬校验（17 类）、value 限长、
   evidence 必须是原文子串、confidence 截断到 [0,1]
        ↓ requirement_service.apply_ai_proposals
   状态机裁决 → 落库（历史 actor=ai:<provider>，来源可审计）
        ↓
   摘要 {applied, needs_confirmation, conflicts, skipped_locked}
```

触发时机：新建询盘后、渠道收信后、上传附件后（自动，AI 可用且开关开启时）；询盘详情"需求"页「🤖 AI 解析」按钮（手动）。

## 开关与权限

- org 级开关 `organizations.settings_json.ai_intake`，默认开启；
- 设置页 AI 卡片展示 provider/状态，owner 可启用/关闭（`settings.manage` 权限）；
- 关闭后全部走规则解析，行为与 v0.8.0 完全一致。

## 金标集与评估

- `backend/eval/golden/intake_golden.json`：32 条样本（清晰表达 / 口语化 / 多意图 / 中英混排 / 否定改口）；
- `backend/scripts/eval_intake.py --pipeline rules|ai [--out 文件]`：字段级准确率（命中=归一化值一致），AI 无 provider 时跳过不失败（CI 安全）；
- **规则基线：88.2%**（110 个字段命中 97）。评估过程中顺手修了一个价格锚定真 bug：`budget 4 usd each` 这类币种后置句式曾被解析成数量 1200 当单价（`normalization.parse_target_price` 改为"候选匹配选离价格关键词最近或自带币种"），六种语序均有断言；
- 剩余规则盲区（AI 的目标区，docs/17 第廿一轮详列）：口语中文数量词、英文数字词（five thousand）、否定表达（NOT stainless steel）、改口（navy now, not blue）、非港口城市目的地、付款条款归一化（30/70 定金 → T/T）；
- AI 直出得分需配置 provider 后用同一脚本测量（`--pipeline ai`），结论写入本节——**先测再默认开**。

## 已知边界

- 图片/扫描件的视觉提取依赖 provider 的多模态能力，无 AI 时附件状态为"待人工"；
- 限速：LLM 调用超时 10s、单次最多提议 12 个字段、value ≤300 字符；
- 审计：`ai.intake` 事件记录提议/裁决摘要；`ai.settings` 记录开关变更。
