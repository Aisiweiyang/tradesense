"""复核包导出：把一个货件的全部单证（最新版）打包成 zip，附带中文核验报告
和带 SHA-256 校验和的清单。只含单证本身的事实数据——报价成本、利润率等
内部经营数据不进入本包（有测试锁定）。"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, DocumentField, DocumentFieldChange, Shipment, ShipmentIssue, User

ISSUE_STATUS_ZH = {
    "open": "待处理", "adopted": "已采纳建议", "manual_fixed": "已人工修改",
    "ignored": "已忽略", "resolved": "已解决",
}
SEVERITY_ZH = {"high": "高", "medium": "中", "low": "低"}
DOC_TYPE_ZH = {
    "invoice": "商业发票", "packing_list": "装箱单", "bill_of_lading": "提单",
    "customs_declaration": "报关单", "letter_of_credit": "信用证",
    "origin_certificate": "原产地证", "other": "其他",
}


def _latest_docs(db: Session, shipment: Shipment) -> list[Document]:
    """每个 doc_type 只取版本号最大的一份。"""
    docs = db.scalars(select(Document).where(
        Document.shipment_id == shipment.id).order_by(
        Document.doc_type, Document.version)).all()
    latest: dict[str, Document] = {}
    for d in docs:
        latest[d.doc_type] = d  # 升序遍历，后写覆盖 → 留下最高版本
    return sorted(latest.values(), key=lambda d: d.doc_type)


def _field_rows(db: Session, docs: list[Document]) -> list[tuple[Document, DocumentField]]:
    rows: list[tuple[Document, DocumentField]] = []
    for d in docs:
        for f in db.scalars(select(DocumentField).where(
                DocumentField.document_id == d.id).order_by(DocumentField.field_name)):
            rows.append((d, f))
    return rows


def build_report(db: Session, org_id: int, shipment: Shipment,
                 docs: list[Document], handler_names: dict[int, str],
                 generated_by: str, generated_at: datetime) -> str:
    lines: list[str] = []
    lines.append("# 货件单证复核报告")
    lines.append("")
    lines.append(f"- 货件号：{shipment.shipment_no}")
    lines.append(f"- 订单号：{shipment.order_no or '—'}")
    lines.append(f"- 航线：{shipment.port_of_loading or '—'} → {shipment.port_of_discharge or '—'}（{shipment.incoterm}）")
    lines.append(f"- 运输方式：{shipment.transport_mode}")
    if shipment.cutoff_at:
        lines.append(f"- 截单时间：{shipment.cutoff_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"- 生成时间：{generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"- 生成人：{generated_by}")
    lines.append("")

    lines.append("## 一、单证清单（每类取最新版本）")
    lines.append("")
    lines.append("| 类型 | 版本 | 原文件名 | 状态 | 页数 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for d in docs:
        lines.append(f"| {DOC_TYPE_ZH.get(d.doc_type, d.doc_type)} | v{d.version} | "
                     f"{d.original_filename} | {d.status} | {d.pages} |")
    lines.append("")

    lines.append("## 二、字段对照总表")
    lines.append("")
    lines.append("| 单证 | 字段 | 值 | 来源 | 证据页 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for d, f in _field_rows(db, docs):
        src = "人工录入" if f.source == "manual" else f"提取({f.confidence:.0%})"
        lines.append(f"| {DOC_TYPE_ZH.get(d.doc_type, d.doc_type)} v{d.version} | {f.field_name} | "
                     f"{f.value} | {src} | {f.evidence_page or '—'} |")
    if not docs:
        lines.append("| — | 无单证 | — | — | — |")
    lines.append("")

    lines.append("## 三、版本差异摘要")
    lines.append("")
    changes = db.scalars(select(DocumentFieldChange).where(
        DocumentFieldChange.shipment_id == shipment.id).order_by(
        DocumentFieldChange.changed_at, DocumentFieldChange.id)).all()
    if changes:
        lines.append("| 单证字段 | 类型 | 旧值（来源版本） | 新值 | 变更时间（UTC） |")
        lines.append("| --- | --- | --- | --- | --- |")
        for c in changes:
            doc = db.get(Document, c.document_id)
            label = f"{DOC_TYPE_ZH.get(doc.doc_type if doc else '', doc.doc_type if doc else '?')}·{c.field_name}"
            kind = {"changed": "变更", "added": "新增", "removed": "移除"}.get(c.change_type, c.change_type)
            at = c.changed_at.strftime("%m-%d %H:%M") if c.changed_at else "—"
            lines.append(f"| {label} | {kind} | {c.old_value or '—'}（v{c.prev_version}） | "
                         f"{c.new_value or '—'} | {at} |")
    else:
        lines.append("无版本差异记录。")
    lines.append("")

    lines.append("## 四、异常与处理记录")
    lines.append("")
    issues = db.scalars(select(ShipmentIssue).where(
        ShipmentIssue.shipment_id == shipment.id).order_by(
        ShipmentIssue.severity, ShipmentIssue.id)).all()
    if issues:
        lines.append("| 严重度 | 标题 | 期望值 | 实际值 | 状态 | 处理人 | 处理时间（UTC） | 处理说明 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for i in issues:
            handler = handler_names.get(i.handler_user_id, "—") if i.handler_user_id else "—"
            at = i.resolved_at.strftime("%Y-%m-%d %H:%M") if i.resolved_at else "—"
            lines.append(f"| {SEVERITY_ZH.get(i.severity, i.severity)} | {i.title} | "
                         f"{i.expected_value or '—'} | {i.actual_value or '—'} | "
                         f"{ISSUE_STATUS_ZH.get(i.status, i.status)} | {handler} | {at} | "
                         f"{i.resolution_note or '—'} |")
    else:
        lines.append("本货件无异常记录。")
    lines.append("")
    lines.append("> 本报告由系统按单证数据自动汇总，导出后请人工复核再对外提供。")
    return "\n".join(lines)


def build_review_package(db: Session, org_id: int, shipment: Shipment,
                         generated_by: str) -> tuple[bytes, str]:
    """返回 (zip 字节, 建议文件名)。"""
    now = datetime.now(timezone.utc)
    docs = _latest_docs(db, shipment)
    users = {u.id: u.name for u in db.scalars(select(User).where(User.org_id == org_id)).all()}

    buf = io.BytesIO()
    manifest_files: list[dict] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            from pathlib import Path
            path = Path(d.file_path)
            if not path.exists():
                continue
            arcname = f"{d.doc_type}_v{d.version}.pdf"
            data = path.read_bytes()
            zf.writestr(arcname, data)
            manifest_files.append({"name": arcname, "size": len(data),
                                   "sha256": hashlib.sha256(data).hexdigest()})
        report = build_report(db, org_id, shipment, docs, users, generated_by, now)
        zf.writestr("verification-report.md", report)
        manifest_files.append({"name": "verification-report.md",
                               "size": len(report.encode("utf-8")),
                               "sha256": hashlib.sha256(report.encode("utf-8")).hexdigest()})
        manifest = {
            "shipment_no": shipment.shipment_no,
            "generated_at": now.isoformat(),
            "generated_by": generated_by,
            "files": manifest_files,
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return buf.getvalue(), f"review-{shipment.shipment_no}.zip"
