"""Demo scenario validation on a REAL seeded database.

Walks the 10 required demo scenarios end-to-end against seed data, verifying
requirement state, clarifications, matching, quotes and follow-ups behave as
the product spec expects.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
os.environ["DATABASE_URL"] = "sqlite:///./test_seed.db"
os.environ["SEED_DEMO_DATA"] = "0"


@pytest.fixture(scope="module")
def seeded():
    """One seeded file DB for the whole module."""
    for suffix in ("", "-wal", "-shm"):
        Path(f"./test_seed.db{suffix}").unlink(missing_ok=True)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base
    import app.seed.run as seed_run

    engine = create_engine(f"sqlite:///./test_seed.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    db = Session()
    seed_run.seed_demo(db)
    db.commit()

    yield db

    db.close()
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        Path(f"./test_seed.db{suffix}").unlink(missing_ok=True)


def _inquiry_by_title(db, title_part: str):
    from sqlalchemy import select  # noqa: F401

    from app.models import Inquiry

    return db.scalar(select(Inquiry).where(
        Inquiry.org_id == _org(db).id, Inquiry.title.contains(title_part)))


def _org(db):
    from sqlalchemy import select

    from app.models import Organization

    return db.scalar(select(Organization).where(
        Organization.name == seed_org_name()))


def seed_org_name():
    from app.seed.run import DEMO_ORG

    return DEMO_ORG


def _values(db, inq):
    from app.services.requirement_service import RequirementService

    return RequirementService(db, _org(db).id).active_values(inq.id)


def _summary(db, inq) -> dict:
    return json.loads(inq.summary_json or "{}")


# ---------------------------------------------------------------- S1 多轮修改
def test_s1_multi_round_correction(seeded):
    from sqlalchemy import select

    inq = _inquiry_by_title(seeded, "Vacuum insulated bottles for German market")
    assert inq, "S1 询盘存在"
    v = _values(seeded, inq)
    assert v["color"]["value"] == "black" and v["color"]["status"] == "active"
    assert v["quantity"]["normalized"] == "1000"
    assert v["destination_port"]["value"] == "Hamburg"
    assert v["incoterm"]["value"] == "FOB"
    assert v["certification"]["value"] == "LFGB"
    # history preserves the original blue / 500 values
    from app.models import RequirementHistory

    rows = seeded.scalars(select(RequirementHistory).where(
        RequirementHistory.inquiry_id == inq.id)).all()
    color_rows = [r for r in rows if r.field == "color" and r.change_type == "update"]
    assert color_rows and color_rows[0].old_value == "blue" and color_rows[0].new_value == "black"
    qty_rows = [r for r in rows if r.field == "quantity" and r.change_type == "update"]
    assert qty_rows and "500" in qty_rows[0].old_value
    assert inq.completeness >= 70


# ---------------------------------------------------------------- S2 美国 FDA
def test_s2_us_fda_request(seeded):
    inq = _inquiry_by_title(seeded, "FDA tritan shaker bottles")
    v = _values(seeded, inq)
    assert "FDA" in v["certification"]["value"]
    assert v["destination_country"]["value"] == "United States"
    assert v["quantity"]["normalized"] == "10000"
    s = _summary(seeded, inq)
    assert "样品" in s["next_step"] or s["completeness"] >= 60


# ---------------------------------------------------------------- S3 中东 DDP 礼品
def test_s3_ddp_gift_with_low_target(seeded):
    from sqlalchemy import select

    from app.models import Quote

    inq = _inquiry_by_title(seeded, "Corporate gift mugs with logo 3000 DDP")
    v = _values(seeded, inq)
    assert v["incoterm"]["value"] == "DDP"
    assert "logo" in v["customization"]["value"].lower()
    quote = seeded.scalar(select(Quote).where(Quote.inquiry_id == inq.id))
    assert quote, "S3 已生成报价"
    risks = json.loads(quote.risks_json)
    assert any("目标价" in r for r in risks), "报价必须提示目标价低于建议价"
    assert quote.is_formal is False, "含风险报价不得自动成为正式报价"


# ---------------------------------------------------------------- S4 修改数量/颜色/目的港
def test_s4_update_flow(seeded):
    inq = _inquiry_by_title(seeded, "Glass cups — updated order")
    v = _values(seeded, inq)
    assert v["quantity"]["normalized"] == "2000"
    assert v["destination_port"]["value"] == "Rotterdam"
    assert v["color"]["value"] in ("transparent", "clear")
    assert v["payment_terms"]["status"] == "active"


# ---------------------------------------------------------------- S5 目标价低于成本
def test_s5_below_cost_quote(seeded):
    from sqlalchemy import select

    from app.models import Quote

    inq = _inquiry_by_title(seeded, "50k cheap thermal bottles")
    quote = seeded.scalar(select(Quote).where(Quote.inquiry_id == inq.id))
    assert quote
    risks = json.loads(quote.risks_json)
    assert any("低于成本" in r or "目标价" in r for r in risks)
    assert quote.status == "draft"


# ---------------------------------------------------------------- S6 缺认证 → 追问认证
def test_s6_missing_cert_asked_first(seeded):
    from app.services.clarification import recommend
    from app.services.requirement_service import RequirementService

    inq = _inquiry_by_title(seeded, "Hiking vacuum flasks 750ml EXW")
    svc = RequirementService(seeded, _org(seeded).id)
    result = recommend(seeded, _org(seeded).id, inq.id, svc.active_values(inq.id))
    assert result["primary"]["field"] == "certification"
    assert "FDA" in result["primary"]["reason"] or "LFGB" in result["primary"]["reason"]


# ---------------------------------------------------------------- S7 无完全匹配
def test_s7_no_exact_match_alternatives(seeded):
    from app.services.matching import match_products_for_inquiry

    inq = _inquiry_by_title(seeded, "Smart heated bottle with speaker?")
    result = match_products_for_inquiry(seeded, _org(seeded).id, _values(seeded, inq))
    assert result["viable"], "应给出可售的最近候选"
    # TS-VB-007 (smart heated bottle) is the closest product by text, but its
    # registered markets do not include FI → HARD-excluded with a visible reason
    smart = next(o for o in result["outcomes"] if o.product.sku == "TS-VB-007")
    assert smart.excluded and "不含目的国" in smart.exclude_reason
    assert any("FI" in smart.exclude_reason for _ in [1])


# ---------------------------------------------------------------- S8 报价后未回复
def test_s8_quoted_no_reply_detected(seeded):
    from app.services.followup import workload_lists

    inq = _inquiry_by_title(seeded, "Enamel mugs 6000pcs — quoted, silent")
    assert inq.status == "quoted"
    lists = workload_lists(seeded, _org(seeded).id)
    assert inq.id in lists["quoted_no_reply"], "必须出现在「报价后未回复」清单"
    assert inq.id in lists["long_silence"]


# ---------------------------------------------------------------- S9 低质量询盘
def test_s9_low_quality_flagged(seeded):
    from sqlalchemy import select

    from app.models import Inquiry

    inq = seeded.scalar(select(Inquiry).where(
        Inquiry.org_id == _org(seeded).id, Inquiry.title == "hi"))
    assert inq, "S9 询盘存在"
    assert inq.quality_flag == "low_quality"
    assert inq.completeness < 30


# ---------------------------------------------------------------- S10 webhook 幂等
def test_s10_webhook_duplicate_ingested_once(seeded):
    from sqlalchemy import select

    from app.models import ExternalMessage, SyncLog

    org = _org(seeded)
    exts = seeded.scalars(select(ExternalMessage).where(
        ExternalMessage.org_id == org.id,
        ExternalMessage.external_message_id == "n8n-msg-fixed-42")).all()
    assert len(exts) == 1, "同一 external_message_id 只入库一条"
    assert exts[0].process_status == "processed"
    logs = seeded.scalars(select(SyncLog).where(
        SyncLog.org_id == org.id, SyncLog.event == "webhook_demo")).all()
    assert logs and json.loads(logs[-1].detail_json)["second_duplicate"] is True


# ---------------------------------------------------------------- S11/S12 特殊状态
def test_s11_unconstrained_color(seeded):
    inq = _inquiry_by_title(seeded, "Travel mugs 1000 FOB Felixstowe")
    v = _values(seeded, inq)
    assert v["color"]["status"] == "unconstrained"
    assert "BPA-free" in v["certification"]["value"]


def test_s12_conflicting_color(seeded):
    inq = _inquiry_by_title(seeded, "Lunch boxes — color question")
    v = _values(seeded, inq)
    assert v["color"]["status"] == "conflicting"
    s = _summary(seeded, inq)
    assert any("颜色" in r for r in s["risks"]), "摘要必须提示颜色矛盾风险"


# ---------------------------------------------------------------- 种子完整性
def test_seed_inventory(seeded):
    from sqlalchemy import func, select

    from app.models import (ConnectorAccount, Customer, FollowUpTask, Inquiry,
                            Product, Quote, ReplyDraft, Supplier, SyncLog)

    org_id = _org(seeded).id
    assert seeded.scalar(select(func.count(Product.id)).where(Product.org_id == org_id)) >= 40
    assert seeded.scalar(select(func.count(Supplier.id)).where(Supplier.org_id == org_id)) >= 10
    assert seeded.scalar(select(func.count(Inquiry.id)).where(Inquiry.org_id == org_id)) >= 15
    assert seeded.scalar(select(func.count(Quote.id)).where(Quote.org_id == org_id)) >= 5
    assert seeded.scalar(select(func.count(FollowUpTask.id)).where(FollowUpTask.org_id == org_id)) >= 8
    assert seeded.scalar(select(func.count(Customer.id)).where(Customer.org_id == org_id)) >= 10
    assert seeded.scalar(select(func.count(ReplyDraft.id)).where(ReplyDraft.org_id == org_id)) >= 4
    assert seeded.scalar(select(func.count(ConnectorAccount.id)).where(ConnectorAccount.org_id == org_id)) == 4
    assert seeded.scalar(select(func.count(SyncLog.id)).where(SyncLog.org_id == org_id)) >= 4
