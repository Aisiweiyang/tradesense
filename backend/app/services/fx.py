"""手工汇率查询（不接外部 API，管理员在设置页维护）。

口径：
- 存储按币种 ISO 代码字母序规范化（USD/CNY=7.2 表示 1 USD 兑 7.2 CNY），
  每组织每币种对只保留一行（后写覆盖先写）。
- 反向查询（如存了 USD/CNY 再查 CNY/USD）读时取倒数 1/rate，
  不做二次舍入，展示层自行决定保留位数。
- 报价取用优先级：用户显式指定的汇率 > 汇率表 > 回退 1.0 并给 missing 提示。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExchangeRate

MISSING = "missing"


def normalize(a: str, b: str) -> tuple[str, str]:
    """币种对按字母序规范化，返回 (base, quote)。"""
    a, b = (a or "").upper(), (b or "").upper()
    return (a, b) if a <= b else (b, a)


def resolve(db: Session, org_id: int, from_ccy: str, to_ccy: str) -> tuple[float, str]:
    """返回 (rate, note)。note 以 "missing:" 开头表示未配置（rate 恒为 1.0）。"""
    src, dst = (from_ccy or "").upper(), (to_ccy or "").upper()
    if not src or not dst or src == dst:
        return 1.0, ""
    base, quote = normalize(src, dst)
    row = db.scalar(select(ExchangeRate).where(
        ExchangeRate.org_id == org_id,
        ExchangeRate.base_currency == base,
        ExchangeRate.quote_currency == quote))
    if row is None or not row.rate:
        return 1.0, f"{MISSING}:汇率表未配置 {src}/{dst}，按 1:1 折算；请在设置中录入后重算"
    rate = float(row.rate)
    if base != src:  # 请求方向与存储方向相反，取倒数，不做二次舍入
        return 1.0 / rate, f"按汇率表 {base}/{quote}={rate:g} 反向折算（1 {src} ≈ {1 / rate:g} {dst}）"
    return rate, f"按汇率表 {src}/{dst}={rate:g} 折算"
