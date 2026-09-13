"""CSV/Excel product import: parse -> map fields -> validate -> preview -> commit.

Import is a two-step, human-in-the-loop flow:
  1. preview(file, mapping) -> normalized rows + per-row errors + duplicates
  2. commit(preview_token)   -> only valid rows are written, errors reported
"""
from __future__ import annotations

import csv
import re
import io
import json
import uuid
from dataclasses import dataclass, field as dc_field

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product, Supplier
from . import normalization as norm

STANDARD_FIELDS = [
    "sku", "name_zh", "name_en", "category", "description", "material", "spec",
    "size", "color", "packaging", "moq", "price_tiers", "currency", "stock_status",
    "lead_time_days", "customization", "certifications", "supplier_name", "image_url",
    "markets", "unit_weight_kg",
]

# header aliases (lowercased, stripped) -> standard field
HEADER_ALIASES = {
    "sku": "sku", "货号": "sku", "编码": "sku", "型号": "sku", "item no": "sku", "item no.": "sku", "item": "sku",
    "中文名称": "name_zh", "中文名": "name_zh", "品名": "name_zh", "产品名称": "name_zh", "名称": "name_zh",
    "name(中文)": "name_zh", "name": "name_en", "name_en": "name_en", "英文名称": "name_en",
    "产品英文名称": "name_en", "product name": "name_en", "英文品名": "name_en",
    "类别": "category", "分类": "category", "category": "category", "品类": "category", "产品类别": "category",
    "描述": "description", "description": "description", "详情": "description", "产品描述": "description",
    "材质": "material", "material": "material", "材料": "material",
    "规格": "spec", "spec": "spec", "specification": "spec", "容量": "spec",
    "尺寸": "size", "size": "size", "外箱尺寸": "size",
    "颜色": "color", "color": "color", "colour": "color", "可选颜色": "color",
    "包装": "packaging", "packaging": "packaging", "包装方式": "packaging", "装箱": "packaging",
    "起订量": "moq", "moq": "moq", "最小起订量": "moq", "最小订单量": "moq",
    "阶梯价": "price_tiers", "阶梯价格": "price_tiers", "价格": "price_tiers", "price": "price_tiers",
    "单价": "price_tiers", "price tiers": "price_tiers", "price tier": "price_tiers", "单价(usd)": "price_tiers",
    "币种": "currency", "currency": "currency",
    "库存": "stock_status", "库存状态": "stock_status", "stock": "stock_status", "stock status": "stock_status",
    "交期": "lead_time_days", "生产周期": "lead_time_days", "货期": "lead_time_days", "lead time": "lead_time_days",
    "lead_time": "lead_time_days", "交货期": "lead_time_days",
    "定制": "customization", "支持定制": "customization", "customization": "customization", "工艺": "customization",
    "认证": "certifications", "certification": "certifications", "certifications": "certifications", "证书": "certifications",
    "供应商": "supplier_name", "supplier": "supplier_name", "supplier name": "supplier_name", "工厂": "supplier_name",
    "图片": "image_url", "image": "image_url", "image_url": "image_url", "photo": "image_url", "图片链接": "image_url",
    "市场": "markets", "markets": "markets", "可售市场": "markets",
    "单重": "unit_weight_kg", "重量": "unit_weight_kg", "单件重量": "unit_weight_kg", "weight": "unit_weight_kg",
    "unit weight(kg)": "unit_weight_kg", "weight(kg)": "unit_weight_kg",
}


@dataclass
class ImportRow:
    row_no: int
    data: dict = dc_field(default_factory=dict)
    errors: list = dc_field(default_factory=list)
    warnings: list = dc_field(default_factory=list)
    duplicate_of: int | None = None  # existing product id

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class ImportPreview:
    token: str
    file_name: str
    mapping: dict
    columns: list
    rows: list  # ImportRow
    total: int
    valid_count: int
    error_count: int
    duplicate_count: int

    def summary(self) -> dict:
        return {"token": self.token, "file_name": self.file_name, "columns": self.columns,
                "mapping": self.mapping, "total": self.total,
                "valid": self.valid_count, "errors": self.error_count,
                "duplicates": self.duplicate_count,
                "rows": [{"row_no": r.row_no, "data": r.data, "errors": r.errors,
                          "warnings": r.warnings, "duplicate_of": r.duplicate_of,
                          "valid": r.valid} for r in self.rows]}


_PREVIEW_CACHE: dict[str, ImportPreview] = {}


def parse_table(file_bytes: bytes, file_name: str) -> tuple[list[str], list[list[str]]]:
    """Return (headers, rows) from CSV or XLSX bytes."""
    name = (file_name or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        rows = [[("" if c is None else str(c)) for c in r] for r in rows]
        rows = [r for r in rows if any(str(c).strip() for c in r)]
        if not rows:
            return [], []
        return [h.strip() for h in rows[0]], rows[1:]
    # CSV: try utf-8 then gbk (common for Chinese Excel exports)
    text = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("无法识别文件编码，请另存为 UTF-8 CSV 或 XLSX")
    reader = list(csv.reader(io.StringIO(text)))
    reader = [r for r in reader if any(str(c).strip() for c in r)]
    if not reader:
        return [], []
    return [h.strip() for h in reader[0]], reader[1:]


def auto_map(headers: list[str]) -> dict:
    """Best-effort header -> standard field mapping (user adjustable in UI)."""
    mapping = {}
    for h in headers:
        key = h.strip().lower()
        if key in HEADER_ALIASES:
            mapping[h] = HEADER_ALIASES[key]
        else:
            for alias, std in HEADER_ALIASES.items():
                if alias and (alias in key or key in alias):
                    mapping[h] = std
                    break
    return mapping


def build_preview(db: Session, org_id: int, file_bytes: bytes, file_name: str,
                  mapping: dict | None = None) -> ImportPreview:
    headers, raw_rows = parse_table(file_bytes, file_name)
    mapping = mapping if mapping is not None else auto_map(headers)

    existing_skus = {p.sku.strip().upper(): p.id for p in db.scalars(
        select(Product).where(Product.org_id == org_id)).all()}

    preview_rows: list[ImportRow] = []
    seen_skus: dict[str, int] = {}
    for i, raw in enumerate(raw_rows, start=2):  # excel-style row numbers
        data = {std: "" for std in STANDARD_FIELDS}
        for col_idx, h in enumerate(headers):
            std = mapping.get(h)
            if std and col_idx < len(raw):
                data[std] = str(raw[col_idx]).strip()
        row = ImportRow(row_no=i, data=data)

        # ---- validation ----------------------------------------------------
        if not data["sku"]:
            row.errors.append("缺少 SKU（货号）")
        if not (data["name_zh"] or data["name_en"]):
            row.errors.append("缺少产品名称（中英文名称至少填一个）")
        if data["moq"]:
            moq_val = norm.parse_number(data["moq"])
            if moq_val is None or moq_val < 0:
                row.errors.append(f"MOQ 无法解析: {data['moq']}")
            else:
                data["moq"] = str(int(moq_val))
        else:
            data["moq"] = "1"
        tiers = _parse_tiers(data["price_tiers"])
        if data["price_tiers"] and not tiers:
            row.errors.append(f"阶梯价格无法解析: {data['price_tiers']}（示例: 100:2.5; 500:2.2 或 2.5）")
        if tiers:
            data["price_tiers"] = json.dumps(tiers, ensure_ascii=False)
        if data["lead_time_days"]:
            lead = norm.parse_number(data["lead_time_days"])
            if lead is None or lead < 0:
                row.warnings.append(f"交期无法解析为天数: {data['lead_time_days']}，将按 30 天处理")
                data["lead_time_days"] = "30"
            else:
                data["lead_time_days"] = str(int(lead))
        else:
            data["lead_time_days"] = "30"
        if data["currency"]:
            cur = norm.normalize_currency(data["currency"]) or ""
            if not cur:
                row.warnings.append(f"币种无法识别: {data['currency']}，按 USD 处理")
            data["currency"] = cur or "USD"
        else:
            data["currency"] = "USD"
        if data["unit_weight_kg"]:
            w = norm.parse_number(data["unit_weight_kg"])
            data["unit_weight_kg"] = "" if w is None else str(w)
        # normalize cert & category enrichments (never silently discard source text)
        certs = norm.normalize_certifications(data["certifications"])
        data["_certs"] = json.dumps(certs)
        concept = norm.canonical_product(" ".join([data["name_en"], data["name_zh"], data["category"]]))
        data["_concept"] = concept["concept"] if concept else (data["category"] or "").strip().lower().replace(" ", "_")

        # ---- duplicates -----------------------------------------------------
        sku_key = data["sku"].strip().upper()
        if sku_key:
            if sku_key in seen_skus:
                row.errors.append(f"文件内 SKU 重复（与第 {seen_skus[sku_key]} 行冲突）")
            elif sku_key in existing_skus:
                row.warnings.append("SKU 已存在于产品库，提交时将更新该产品")
                row.duplicate_of = existing_skus[sku_key]
            seen_skus.setdefault(sku_key, i)

        preview_rows.append(row)

    preview = ImportPreview(
        token=uuid.uuid4().hex, file_name=file_name, mapping=mapping, columns=headers,
        rows=preview_rows, total=len(preview_rows),
        valid_count=sum(1 for r in preview_rows if r.valid and not r.errors),
        error_count=sum(1 for r in preview_rows if r.errors),
        duplicate_count=sum(1 for r in preview_rows if r.duplicate_of),
    )
    _PREVIEW_CACHE[preview.token] = preview
    # keep cache bounded
    if len(_PREVIEW_CACHE) > 50:
        for k in list(_PREVIEW_CACHE)[: -50]:
            _PREVIEW_CACHE.pop(k, None)
    return preview


def _parse_tiers(raw: str) -> list[dict]:
    """Parse '100:2.5;500:2.2' / '100,2.5|500,2.2' / plain '2.5' -> tiers JSON."""
    raw = (raw or "").strip()
    if not raw:
        return []
    tiers = []
    parts = [p for p in re.split(r"[;；\n|｜]", raw) if p.strip()] or [raw]
    for part in parts:
        m = None
        for sep in (":", "：", ",", "，", "="):
            if sep in part:
                a, b = part.split(sep, 1)
                qty, price = norm.parse_number(a), norm.parse_number(b)
                m = (qty, price)
                break
        if m is None:
            price = norm.parse_number(part)
            m = (None, price)
        qty, price = m
        if price is None or price <= 0:
            return []
        tiers.append({"min_qty": int(qty or 1), "unit_price": price})
    tiers.sort(key=lambda t: t["min_qty"])
    return tiers


def commit_preview(db: Session, org_id: int, token: str,
                   supplier_cache: dict[str, int] | None = None) -> dict:
    preview = _PREVIEW_CACHE.get(token)
    if preview is None:
        raise ValueError("预览令牌不存在或已过期，请重新上传")
    created, updated, failed = 0, 0, []
    for row in preview.rows:
        if not row.valid:
            failed.append({"row": row.row_no, "errors": row.errors})
            continue
        d = row.data
        supplier_id = None
        sup_name = d.get("supplier_name", "")
        if sup_name:
            sup = db.scalar(select(Supplier).where(Supplier.org_id == org_id,
                                                   Supplier.name == sup_name))
            if sup is None:
                sup = Supplier(org_id=org_id, name=sup_name)
                db.add(sup)
                db.flush()
            supplier_id = sup.id
        values = dict(
            sku=d["sku"], name_zh=d.get("name_zh", ""), name_en=d.get("name_en", ""),
            category=d.get("_concept", ""), description=d.get("description", ""),
            material=d.get("material", ""), spec=d.get("spec", ""), size=d.get("size", ""),
            color=d.get("color", ""), packaging=d.get("packaging", ""),
            moq=int(d.get("moq") or 1), price_tiers_json=d.get("price_tiers") or "[]",
            currency=d.get("currency", "USD"), stock_status=d.get("stock_status") or "made_to_order",
            lead_time_days=int(d.get("lead_time_days") or 30),
            customization=d.get("customization", ""),
            certifications_json=d.get("_certs", "[]"),
            supplier_id=supplier_id, image_url=d.get("image_url", ""),
            markets=d.get("markets", ""),
            unit_weight_kg=float(d["unit_weight_kg"]) if d.get("unit_weight_kg") else None,
            data_source=f"import:{preview.file_name}",
        )
        if row.duplicate_of:
            existing = db.get(Product, row.duplicate_of)
            for k, v in values.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(Product(org_id=org_id, **values))
            created += 1
    db.flush()
    _PREVIEW_CACHE.pop(token, None)
    return {"created": created, "updated": updated, "failed": failed}


