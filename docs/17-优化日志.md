# TradeSense 优化日志（三轮有记录的迭代）

> 每轮记录：发现的问题 → 修改内容 → 修改前后的测试/指标 → 是否引入新风险。
> 全程遵守：不删测试、不降断言、不隐藏错误。

---

## 第 1 轮：核心链路正确性 + 界面可用性

**发现的问题（冒烟测试 + 无头截图走查）**

| # | 问题 | 严重度 | 修改前 | 修改后 |
| --- | --- | --- | --- | --- |
| 1 | `routes/followups.py` 漏导入 `Inquiry` → `GET /followups/workload` 500，「今日待办」页挂 | 高 | 500 internal_error | 正常返回，测试覆盖 |
| 2 | `dashboard/workbench` 的 workload 只返回 ID 数组 → 工作台「高意向询盘」卡片渲染成空环+孤立的 % | 高 | `[14,5,4,...]` | `workload_enriched()` 返回含标题/完整度的对象（截图确认） |
| 3 | 询盘详情页 Overview 组件在两个 useQuery 之间提前 return → 违反 Hooks 规则，**整页白屏**（截图 5.8KB 空白） | 高 | 白屏 | 概览/摘要/完整度/风险全部渲染（截图确认 94KB） |
| 4 | 报价计算器在 USD→USD（汇率=1.0）时也套 2% 汇率缓冲 → 成本虚高 2%（3.51→3.58） | 高 | unit_cost 3.5802 | 仅真实跨币种加缓冲，3.51（确定性测试锁定） |
| 5 | 徽章/交期列文字换行（"启用"两字分行） | 低 | 表格挤压错位 | `whitespace-nowrap`（截图确认） |
| 6 | 摘要数量重复："5,000 pcs（约 5000 pcs）" | 低 | 信息冗余 | 只保留展示值 |
| 7 | Recharts 默认入场动画导致无头/慢环境图表空白 | 中 | 看板只有坐标轴 | `isAnimationActive={false}`（截图确认柱/饼图渲染） |

**修改前后的测试/指标**

- 后端：57 → 66 通过（新增：FX 缓冲边界、hash 语义、同步日志 flush 等）；
- 前端：11 个测试通过；`tsc -b` 零错误；
- 截图：详情页 5.8KB(空白) → 94KB(完整)；analytics 63KB(无图) → 73KB(有图)。

**引入新风险？** 无。全部修复均有回归测试或截图验证。

---

## 第 2 轮：真实场景走查（10 大演示场景）

**做法**：新增 `tests/test_demo_scenarios.py`，在真实种子数据库上逐场景断言期望行为。

**发现的问题**

| # | 问题 | 修改 |
| --- | --- | --- |
| 1 | 重复 Webhook 检测会**改写原始消息**的 `process_status` 为 duplicate（原始记录应保持 processed） | 去重仅返回结果，不再篡改首条记录 |
| 2 | 演示数据报价只有 4 份（规格要求 ≥5） | S4 补充一份 FOB 草稿报价（现 5 份） |
| 3 | S9 断言按标题子串匹配误中 WhatsApp 询盘（"hi" ⊂ "Hi, we need..."） | 测试改为精确标题匹配（属于测试修正，非产品缺陷） |

**场景走查结论（全部符合预期）**

- S1 多轮修改：`color: blue→black`、`quantity: 500→1,000`、Hamburg/FOB/LFGB ✓
- S5 目标价低于成本：报价带亏损风险、保持 draft ✓
- S6 食品接触缺认证：追问推荐第一位=certification，理由提及 FDA/LFGB ✓
- S7 无完全匹配：TS-VB-007 被目的国硬条件（markets 不含 FI）**淘汰且原因可见**，仍给出 8 个可售候选 ✓
- S8 报价后未回复：正确出现在 quoted_no_reply 与 long_silence 清单 ✓
- S10 同一 Webhook 消息推两次：仅入库一条，日志记录 second_duplicate=true ✓
- S11 "any color"→unconstrained；S12 两种颜色→conflicting 且摘要风险提示 ✓

**修改前后的测试/指标**

- 后端：66 → **79 通过**（+13 场景用例）；
- 修复 #1 后 `test_connectors.py` 全部保持通过（未弱化任何断言）。

**引入新风险？** 无。重复检测行为变化仅影响状态标记，幂等结果（不重复建询盘）不变且有测试。

---

## 第 3 轮：启动可靠性与交付验证

**发现的问题**

| # | 问题 | 修改 |
| --- | --- | --- |
| 1 | `alembic` 不在 PATH 时 init_db 静默跳过迁移 | 改为 `sys.executable -m alembic`；失败时 `create_all + stamp head` 兜底（两种路径都实测） |
| 2 | 演示邮箱 `*.local` 被 email-validator 拒绝（保留域），演示账号无法登录 | 改为 `demo@tradesense-demo.cn`，重新种子验证 |
| 3 | SQLite 读取的 datetime 丢时区 → 多处 `aware - naive` TypeError（workbench 500） | 自定义 `TZDateTime` TypeDecorator，全部时间列统一（含 TimestampMixin），读写双向兜底 |
| 4 | `vite preview`（生产构建预览）没有 /api 代理 | vite.config 增加 preview.proxy |
| 5 | 前端缺少截图自动化用的免登录通道 | 增加 **localhost-only** `#token=` 引导（生产域名不生效），配套 `scripts/capture_pages.py` |

**干净启动验证（模拟新用户，删除 DB 后从头执行）**

```
rm tradesense.db → python scripts/init_db.py
  [init_db] alembic upgrade head: ok
  [init_db] demo seed done
启动 uvicorn → /api/health ok → login ok → 前端 /api 代理 ok
```

**修改前后的测试/指标**

- 后端 79 通过、前端 11 通过（每轮修改后全量回归）；
- 10+ 页面无头截图视觉检查通过（工作台/详情工作台/产品/连接器/看板/今日待办/导入/术语/跟进/询盘列表）；
- Alembic 迁移：0 状态 → head 实测成功。

**引入新风险？** `TZDateTime` 改变了 SQLite 时间读写行为，属全局变更——已由 79 个测试（含时间敏感的 workload/超期判定）回归覆盖；`#token=` 引导限定 localhost 且已写入已知限制。
