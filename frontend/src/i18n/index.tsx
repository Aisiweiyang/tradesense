import { createContext, useContext, useState, type ReactNode } from "react";

// Lightweight i18n infrastructure: zh-CN default, English toggle.
// Keys live in one flat dictionary per locale; missing keys fall back to zh-CN.

const zh = {
  appName: "TradeSense",
  appTagline: "外贸询盘 · 客户跟进 · 产品匹配 · 报价辅助",
  nav_dashboard: "工作台",
  nav_today: "今日待办",
  nav_inquiries: "询盘",
  nav_customers: "客户",
  nav_products: "产品",
  nav_import: "产品导入",
  nav_suppliers: "供应商",
  nav_quotes: "报价",
  nav_followups: "跟进任务",
  nav_connectors: "渠道连接",
  nav_synclogs: "同步日志",
  nav_audit: "审计日志",
  nav_settings: "设置",
  nav_analytics: "数据看板",
  nav_glossary: "术语助手",
  login: "登录",
  logout: "退出",
  email: "邮箱",
  password: "密码",
  login_failed: "登录失败",
  welcome: "欢迎使用 TradeSense",
  demo_account: "演示账号",
  search: "搜索",
  create: "新建",
  save: "保存",
  cancel: "取消",
  confirm: "确认",
  edit: "编辑",
  delete: "删除",
  loading: "加载中…",
  empty: "暂无数据",
  error: "出错了",
  retry: "重试",
  total: "共",
  items: "条",
  page: "页",
  status: "状态",
  completeness: "询盘完整度",
  confirmed: "已确认",
  pending_confirm: "待确认",
  missing: "缺失信息",
  conflicting: "矛盾字段",
  cannot_quote: "当前不能正式报价的原因",
  risk: "风险提示",
  next_step: "建议下一步",
  summary: "中文摘要",
  what_customer_wants: "客户要什么",
  quantity: "数量",
  destination: "目的国/港口",
  target_price: "目标价格",
  customization: "定制要求",
  certification: "认证要求",
  lead_time: "交期",
  known_info: "已知信息",
  recommend_question: "推荐追问",
  why: "为什么问这个",
  secondary_questions: "其他待确认",
  product_match: "产品匹配",
  match_score: "匹配分",
  met: "满足条件",
  unmet: "未满足",
  excluded_reason: "淘汰/风险原因",
  run_match: "运行匹配",
  quote: "报价",
  quote_calc: "报价计算",
  internal_cost: "内部成本",
  suggested: "建议报价",
  customer_price: "客户报价",
  approved: "已批准",
  approve: "批准",
  reject: "拒绝",
  breakdown: "计算明细",
  assumptions: "假设条件",
  valid_until: "有效期至",
  reply_draft: "回复草稿",
  generate_draft: "生成草稿",
  tone: "语气",
  tone_formal: "正式",
  tone_friendly: "友好",
  tone_concise: "简洁",
  facts_used: "使用的事实",
  needs_confirmation: "需要人工确认",
  copy: "复制",
  copied: "已复制",
  followup_task: "跟进任务",
  create_task: "创建任务",
  due_at: "截止时间",
  done: "完成",
  snooze: "延期",
  overdue: "已超期",
  today_due: "今日到期",
  quoted_no_reply: "报价后未回复",
  long_silence: "长期沉默",
  high_intent: "高意向",
  incomplete: "数据不完整",
  messages: "对话消息",
  add_message: "添加消息",
  history: "修改历史",
  lock: "锁定",
  locked: "已锁定",
  unlock: "解锁",
  manual_set: "人工确认",
  import_products: "导入产品",
  download_template: "下载模板",
  upload_file: "上传文件",
  preview: "预览",
  commit_import: "确认导入",
  field_mapping: "字段映射",
  row_errors: "行错误",
  duplicates: "重复",
  connector_test: "测试连接",
  sync_now: "立即同步",
  simulated: "模拟",
  live: "真实",
  not_authorized: "未真实授权",
  language: "界面语言",
  save_ok: "已保存",
} as const;

const en: Partial<Record<keyof typeof zh, string>> = {
  nav_dashboard: "Workbench",
  nav_today: "Today",
  nav_inquiries: "Inquiries",
  nav_customers: "Customers",
  nav_products: "Products",
  nav_import: "Import",
  nav_suppliers: "Suppliers",
  nav_quotes: "Quotes",
  nav_followups: "Follow-ups",
  nav_connectors: "Channels",
  nav_synclogs: "Sync logs",
  nav_audit: "Audit log",
  nav_settings: "Settings",
  nav_analytics: "Analytics",
  nav_glossary: "Glossary",
  login: "Sign in",
  logout: "Sign out",
  email: "Email",
  password: "Password",
  loading: "Loading…",
  empty: "No data yet",
  error: "Something went wrong",
  retry: "Retry",
  save: "Save",
  cancel: "Cancel",
  create: "New",
  search: "Search",
  completeness: "Completeness",
  language: "Language",
};

export type Locale = "zh-CN" | "en-US";
type Key = keyof typeof zh;

const dicts: Record<Locale, Partial<Record<Key, string>>> = { "zh-CN": zh, "en-US": en };

interface I18nCtx {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (k: Key) => string;
}

const Ctx = createContext<I18nCtx>({ locale: "zh-CN", setLocale: () => {}, t: (k) => zh[k] });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(
    () => (localStorage.getItem("tradesense_locale") as Locale) || "zh-CN",
  );
  const setLocale = (l: Locale) => {
    localStorage.setItem("tradesense_locale", l);
    setLocaleState(l);
  };
  const t = (k: Key) => dicts[locale][k] ?? zh[k];
  return <Ctx.Provider value={{ locale, setLocale, t }}>{children}</Ctx.Provider>;
}

export function useI18n() {
  return useContext(Ctx);
}
