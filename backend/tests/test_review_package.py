"""复核包导出：zip 内容、PDF 合法性、报告含异常处理记录、无内部成本、组织隔离与权限。"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers
from tests.test_shipments_api import _pdf_bytes
from tests.test_shipments_api import shipment as shipment_fixture  # noqa: F401


@pytest.fixture()
def member_headers(client):
    from sqlalchemy import select
    from app.models import Organization, User
    from app.security import hash_password
    db = client.app.state.test_db
    org = db.scalar(select(Organization))
    db.add(User(org_id=org.id, email="member2@test.cn", name="小成员",
                password_hash=hash_password("password123"), role="member"))
    db.commit()
    token = client.post("/api/auth/login", json={
        "email": "member2@test.cn", "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_full_shipment(client, shipment_fixture) -> None:
    """上传发票 + 装箱单，处理一条异常，制造完整复核场景。"""
    h = auth_headers(client)
    sid = shipment_fixture["id"]
    client.post(f"/api/shipments/{sid}/documents",
                files={"file": ("invoice.pdf", _pdf_bytes("invoice.pdf"),
                                "application/pdf")}, headers=h)
    client.post(f"/api/shipments/{sid}/documents",
                files={"file": ("packing.pdf", _pdf_bytes("packing.pdf"),
                                "application/pdf")}, headers=h)
    detail = client.get(f"/api/shipments/{sid}", headers=h).json()
    for issue in detail["issues"]:
        client.post(f"/api/shipments/issues/{issue['id']}/action",
                    json={"action": "ignore", "note": "客户书面豁免，见邮件 09-12"}, headers=h)


def test_zip_contains_pdfs_report_manifest(client, shipment_fixture):
    _seed_full_shipment(client, shipment_fixture)
    h = auth_headers(client)
    r = client.get(f"/api/shipments/{shipment_fixture['id']}/review-package", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert {"invoice_v1.pdf", "packing_list_v1.pdf",
            "verification-report.md", "manifest.json"} <= names
    for name in names:
        if name.endswith(".pdf"):
            assert zf.read(name)[:5] == b"%PDF-", f"{name} 不是合法 PDF"


def test_report_includes_issues_and_resolution(client, shipment_fixture):
    _seed_full_shipment(client, shipment_fixture)
    h = auth_headers(client)
    r = client.get(f"/api/shipments/{shipment_fixture['id']}/review-package", headers=h)
    report = zipfile.ZipFile(io.BytesIO(r.content)).read("verification-report.md").decode("utf-8")
    assert "货件单证复核报告" in report
    assert "字段对照总表" in report
    assert "异常与处理记录" in report
    # 异常标题、处理状态与理由都要出现
    assert "已忽略" in report
    assert "客户书面豁免" in report
    # 处理人是 owner 的名字
    assert "测试员" in report


def test_manifest_checksums_match_content(client, shipment_fixture):
    _seed_full_shipment(client, shipment_fixture)
    h = auth_headers(client)
    r = client.get(f"/api/shipments/{shipment_fixture['id']}/review-package", headers=h)
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["shipment_no"] == shipment_fixture["shipment_no"]
    listed = {f["name"]: f for f in manifest["files"]}
    for name, meta in listed.items():
        raw = zf.read(name)
        assert meta["size"] == len(raw)
        assert meta["sha256"] == hashlib.sha256(raw).hexdigest()


def test_package_has_no_internal_cost_fields(client, shipment_fixture):
    _seed_full_shipment(client, shipment_fixture)
    h = auth_headers(client)
    r = client.get(f"/api/shipments/{shipment_fixture['id']}/review-package", headers=h)
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    report = zf.read("verification-report.md").decode("utf-8")
    for banned in ("unit_cost", "margin_rate", "利润", "成本价", "内部成本", "base_cost"):
        assert banned not in report, f"复核包报告泄漏内部成本关键词：{banned}"


def test_member_cannot_export_review_package(client, shipment_fixture, member_headers):
    _seed_full_shipment(client, shipment_fixture)
    r = client.get(f"/api/shipments/{shipment_fixture['id']}/review-package",
                   headers=member_headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
    # manager+ 导出成功且写审计
    h = auth_headers(client)
    ok = client.get(f"/api/shipments/{shipment_fixture['id']}/review-package", headers=h)
    assert ok.status_code == 200
    events = client.get("/api/audit?action=review_package", headers=h).json()["items"]
    assert any(e["action"] == "review_package.export" for e in events)


def test_review_package_org_isolation(client, shipment_fixture, other_org, db):
    from app.models import User
    from app.security import hash_password
    h = auth_headers(client)
    _seed_full_shipment(client, shipment_fixture)
    db.add(User(org_id=other_org.id, email="owner2c@test.cn", name="他司",
                password_hash=hash_password("password123")))
    db.commit()
    h2 = auth_headers(client, email="owner2c@test.cn")
    r = client.get(f"/api/shipments/{shipment_fixture['id']}/review-package", headers=h2)
    assert r.status_code == 404
