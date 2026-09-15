"""Demo data seeding — close to a real small trading office.

Creates (idempotent: skipped when the demo org already exists):
  - demo organization + owner account  demo@tradesense.local / demo1234
  - 11 suppliers, 42+ products in 11 categories (varied MOQ/price/certs/lead time)
  - 15+ inquiries covering the 10 required demo scenarios, incl. multi-round
  - quotes (draft / below-cost / approved), follow-up tasks, reply drafts
  - 4 connector accounts (simulated email/WhatsApp + webform + generic webhook)
  - one real pipeline run of the simulated inbox + a duplicate webhook message
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (Contact, ConversationThread, Customer, FollowUpTask, Inquiry,
                      Organization, Product, Quote, ReplyDraft, Role, Supplier,
                      SupplierProduct, User, ConnectorAccount, SyncLog, SyncCursor)
from ..security import hash_password
from ..services.audit import audit
from ..services.imports import _parse_tiers
from ..services.ingestion import _utcnow, add_message, ingest_external_message
from ..services.matching import persist_match_results
from ..services.quotation import QuoteInput, compute_quote
from ..services.requirement_service import RequirementService

DEMO_ORG = "演示外贸公司（Demo）"
DEMO_EMAIL = "demo@tradesense-demo.cn"
DEMO_PASSWORD = "demo1234"


def ensure_seeded() -> bool:
    """Seed once; returns True when seeding actually ran."""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        exists = db.scalar(select(func.count(Organization.id)).where(
            Organization.name == DEMO_ORG))
        if exists:
            return False
        seed_demo(db)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _days(n: int) -> datetime:
    return _utcnow() + timedelta(days=n)


def _ago(n: int) -> datetime:
    return _utcnow() - timedelta(days=n)


# ----------------------------------------------------------------- products
# (sku, name_zh, name_en, category(concept), material, spec, colors, packaging,
#  moq, tiers, currency, lead_days, certs, customization, supplier_idx, weight, markets)
PRODUCTS = [
    # --- insulated bottles -------------------------------------------------
    ("TS-VB-001", "304不锈钢真空保温杯 500ml", "Vacuum Insulated Bottle 500ml", "insulated_bottle",
     "stainless steel 304", "500ml", "matte black, silver, white, blue", "color box", 500,
     "100:5.2;500:4.6;1000:4.2;5000:3.8", 25, ["FDA", "LFGB"], "logo, silk-print", 0, 0.32, "DE,FR,NL,GB,US"),
    ("TS-VB-002", "316不锈钢保温杯 600ml", "Premium 316 Steel Thermos 600ml", "insulated_bottle",
     "stainless steel 316", "600ml", "black, green, cream", "gift box", 300,
     "300:6.8;1000:6.2;3000:5.8", 28, ["FDA", "LFGB"], "logo, laser", 1, 0.38, ""),
    ("TS-VB-003", "便携迷你保温杯 350ml", "Mini Vacuum Flask 350ml", "insulated_bottle",
     "stainless steel 304", "350ml", "pink, blue, silver", "color box", 1000,
     "1000:3.4;3000:3.1", 22, ["LFGB"], "logo", 0, 0.24, ""),
    ("TS-VB-004", "大容量户外保温壶 1.5L", "Outdoor Vacuum Bottle 1.5L", "insulated_bottle",
     "stainless steel 201", "1.5L", "green, black", "poly bag + carton", 500,
     "500:7.5;2000:6.9", 30, [], "logo", 2, 0.85, ""),
    ("TS-VB-005", "儿童吸管保温杯 400ml", "Kids Straw Thermos 400ml", "insulated_bottle",
     "stainless steel 304", "400ml", "yellow, pink, blue", "color box", 1000,
     "1000:4.9;5000:4.3", 25, ["FDA", "LFGB", "BPA-free"], "logo, custom carton", 1, 0.30, ""),
    ("TS-VB-006", "弹盖保温杯 750ml", "Flip-lid Vacuum Bottle 750ml", "insulated_bottle",
     "stainless steel 201", "750ml", "black, red", "white box", 800,
     "800:4.1;2000:3.7", 26, ["FDA"], "logo", 2, 0.42, ""),
    # --- water bottles -------------------------------------------------------
    ("TS-WB-001", "Tritan运动水杯 800ml", "Tritan Sports Bottle 800ml", "water_bottle",
     "tritan", "800ml", "transparent, blue, green", "shrink wrap", 2000,
     "2000:1.35;10000:1.05;30000:0.92", 18, ["FDA", "BPA-free"], "logo, full wrap print", 3, 0.16, ""),
    ("TS-WB-002", "PP塑料水杯 600ml", "PP Plastic Water Bottle 600ml", "water_bottle",
     "pp plastic", "600ml", "any pantone", "poly bag", 5000,
     "5000:0.55;20000:0.48", 15, ["FDA", "food_grade"], "logo", 3, 0.11, ""),
    ("TS-WB-003", "摇摇杯 700ml 带搅拌球", "Shaker Bottle 700ml with Mixer Ball", "water_bottle",
     "pp plastic", "700ml", "black, blue, orange", "poly bag + color sleeve", 3000,
     "3000:0.95;10000:0.82", 16, ["FDA", "BPA-free"], "logo, custom mold cap", 3, 0.15, ""),
    ("TS-WB-004", "玻璃双层水杯 450ml", "Double-wall Glass Bottle 450ml", "water_bottle",
     "borosilicate glass", "450ml", "clear", "foam + box", 1000,
     "1000:2.4;3000:2.1", 20, ["LFGB", "food_grade"], "logo, sleeve", 4, 0.35, ""),
    # --- travel mugs ----------------------------------------------------------
    ("TS-TM-001", "汽车保温咖啡杯 450ml", "Insulated Travel Mug 450ml", "travel_mug",
     "stainless steel 304", "450ml", "black, silver, navy", "color box", 500,
     "500:4.8;1000:4.4", 24, ["FDA", "LFGB"], "logo", 0, 0.34, ""),
    ("TS-TM-002", "翻盖车载杯 500ml", "Flip-lid Car Tumbler 500ml", "travel_mug",
     "stainless steel 201", "500ml", "red, black", "white box", 1000,
     "1000:3.6;5000:3.2", 22, ["FDA"], "logo, full color print", 2, 0.36, ""),
    ("TS-TM-003", "随手杯 380ml 塑料内胆", "Light Travel Mug 380ml", "travel_mug",
     "pp plastic", "380ml", "white, green, orange", "poly bag", 2000,
     "2000:1.6;8000:1.4", 15, ["BPA-free"], "logo", 3, 0.14, ""),
    # --- mugs ------------------------------------------------------------------
    ("TS-MG-001", "陶瓷马克杯 350ml", "Ceramic Coffee Mug 350ml", "mug",
     "ceramic", "350ml", "white, black, custom", "white box + divider", 1000,
     "1000:1.15;3000:0.98;10000:0.88", 20, ["FDA", "CA Prop 65"], "print, laser, decal", 5, 0.42, "US,CA,GB,AU"),
    ("TS-MG-002", "亚光釉马克杯 400ml", "Matte Glaze Mug 400ml", "mug",
     "ceramic", "400ml", "gray, green, pink", "gift box", 1000,
     "1000:1.65;5000:1.45", 22, ["LFGB", "FDA"], "print, decal", 5, 0.48, ""),
    ("TS-MG-003", "变色马克杯 330ml", "Color-changing Magic Mug 330ml", "mug",
     "ceramic", "330ml", "black", "color box", 500,
     "500:2.2;2000:1.9", 25, ["FDA"], "photo print", 5, 0.40, ""),
    ("TS-MG-004", "搪瓷杯 360ml", "Enamel Camping Mug 360ml", "mug",
     "iron", "360ml", "white with rim, custom print", "poly foam", 2000,
     "2000:1.3;6000:1.15", 24, ["FDA", "food_grade"], "full print", 6, 0.30, ""),
    # --- glass cups -------------------------------------------------------------
    ("TS-GC-001", "高硼硅玻璃杯 320ml 六只装", "Borosilicate Glasses 320ml (6pc set)", "glass_cup",
     "borosilicate glass", "320ml", "clear", "color box", 500,
     "500:4.2;2000:3.7", 22, ["LFGB", "food_grade"], "logo on box", 4, 1.5, ""),
    ("TS-GC-002", "单层玻璃杯 280ml", "Soda-lime Glass Tumbler 280ml", "glass_cup",
     "glass", "280ml", "clear, amber", "bulk + divider", 3000,
     "3000:0.62;10000:0.55", 18, ["food_grade"], "logo", 4, 0.22, ""),
    ("TS-GC-003", "玻璃杯双层隔热 400ml", "Double-wall Heat-resistant Glass 400ml", "glass_cup",
     "borosilicate glass", "400ml", "clear", "gift box", 1000,
     "1000:2.9;3000:2.6", 20, ["LFGB"], "logo", 4, 0.38, ""),
    # --- food containers ----------------------------------------------------------
    ("TS-FC-001", "不锈钢保鲜盒三件套", "Stainless Steel Food Container Set (3pc)", "food_container",
     "stainless steel 304", "550ml/800ml/1200ml", "silver", "color box", 500,
     "500:6.5;1500:5.9", 28, ["FDA", "LFGB"], "logo, custom sleeve", 1, 0.95, ""),
    ("TS-FC-002", "玻璃保鲜盒 分隔 1L", "Glass Meal Prep Container 1L divider", "food_container",
     "borosilicate glass", "1L", "clear", "color box", 1000,
     "1000:3.3;3000:2.9", 24, ["FDA", "LFGB", "EC1935/2004"], "logo", 4, 0.85, ""),
    ("TS-FC-003", "PP便携饭盒 900ml", "PP Lunch Box 900ml", "food_container",
     "pp plastic", "900ml", "green, blue, pink", "poly bag", 3000,
     "3000:0.85;10000:0.72", 16, ["FDA", "food_grade"], "logo", 3, 0.18, ""),
    ("TS-FC-004", "竹纤维儿童餐盒", "Bamboo Fiber Kids Bento Box", "food_container",
     "bamboo", "5 compartments", "natural, 4 colors", "color box", 1000,
     "1000:2.6;3000:2.3", 26, ["FDA", "LFGB"], "logo, custom color", 7, 0.5, ""),
    # --- kettles / jugs ---------------------------------------------------------
    ("TS-KT-001", "家用保温壶 1.2L", "Household Vacuum Jug 1.2L", "kettle",
     "stainless steel 304", "1.2L", "white, champagne", "color box", 500,
     "500:7.8;2000:7.0", 30, ["LFGB", "FDA"], "logo", 1, 0.9, ""),
    ("TS-KT-002", "法压咖啡壶 600ml", "French Press 600ml", "coffee_maker",
     "borosilicate glass", "600ml", "clear + steel frame", "color box", 500,
     "500:4.5;2000:3.9", 25, ["LFGB", "food_grade"], "logo on frame", 4, 0.55, ""),
    ("TS-KT-003", "摩卡壶 3杯份", "Moka Pot 3-cup", "coffee_maker",
     "aluminum", "150ml", "silver", "gift box", 1000,
     "1000:3.8;3000:3.4", 26, ["food_grade"], "logo", 6, 0.45, ""),
    ("TS-KT-004", "手冲咖啡壶套装", "Pour-over Coffee Set", "coffee_maker",
     "glass", "600ml + dripper", "clear", "gift box", 500,
     "500:8.8;1500:8.0", 28, ["LFGB"], "logo, box design", 4, 0.8, ""),
    # --- gift sets -----------------------------------------------------------------
    ("TS-GS-001", "保温杯+马克杯礼盒套装", "Bottle & Mug Corporate Gift Set", "gift_set",
     "stainless steel 304 + ceramic", "500ml + 350ml", "black/white combos", "gift box + sleeve", 300,
     "300:9.8;1000:8.9", 30, ["FDA", "LFGB"], "logo on both, custom box", 8, 1.2, ""),
    ("TS-GS-002", "玻璃杯对杯礼盒", "Glass Pair Gift Box", "gift_set",
     "borosilicate glass", "2 x 300ml", "clear", "gift box", 500,
     "500:5.6;2000:5.0", 22, ["LFGB"], "logo, greeting card", 8, 0.9, ""),
    ("TS-GS-003", "咖啡具入门礼盒", "Coffee Lover Starter Gift Set", "gift_set",
     "glass + stainless", "press 350ml + 2 cups", "clear/black", "gift box", 300,
     "300:10.5;1000:9.6", 30, ["LFGB", "FDA"], "logo, custom box", 8, 1.4, ""),
    ("TS-GS-004", "保温杯+茶隔礼盒", "Thermos with Tea Infuser Gift Set", "gift_set",
     "stainless steel 316", "500ml + infuser", "navy, rose gold", "gift box", 300,
     "300:8.2;1000:7.5", 28, ["FDA", "LFGB"], "logo, laser", 1, 0.7, ""),
    # --- baby ----------------------------------------------------------------------
    ("TS-BB-001", "PPSU奶瓶 240ml", "PPSU Baby Bottle 240ml", "baby_bottle",
     "pp", "240ml", "transparent", "color box", 2000,
     "2000:2.8;8000:2.4", 30, ["FDA", "CPC", "BPA-free"], "logo, custom nipple", 9, 0.2, ""),
    ("TS-BB-002", "儿童学饮杯 300ml", "Toddler Sippy Cup 300ml", "baby_bottle",
     "tritan", "300ml", "blue, pink, yellow", "color box", 2000,
     "2000:1.9;8000:1.6", 25, ["FDA", "CPC", "BPA-free"], "logo", 3, 0.18, ""),
    # --- cooler bags ------------------------------------------------------------------
    ("TS-CB-001", "保温午餐包 6L", "Insulated Lunch Cooler Bag 6L", "cooler_bag",
     "pu", "6L", "gray, navy, custom", "poly bag", 1000,
     "1000:2.4;5000:2.0", 20, [], "full print, custom zipper", 10, 0.3, ""),
    ("TS-CB-002", "大号野餐冰包 20L", "Large Picnic Cooler 20L", "cooler_bag",
     "polyester", "20L", "green, black", "poly bag", 500,
     "500:5.5;2000:4.8", 25, [], "logo, custom fabric", 10, 0.7, ""),
    # --- misc / odd SKUs for import & edge cases -------------------------------------
    ("TS-VB-007", "电加热智能保温杯 450ml", "Smart Heated Bottle 450ml", "insulated_bottle",
     "stainless steel 304", "450ml + LED display", "black", "gift box", 1000,
     "1000:12.8;3000:11.5", 35, ["CE", "FCC", "RoHS", "FDA"], "logo", 1, 0.5, "DE,FR,IT,ES,NL,GB,US,JP,KR"),
    ("TS-WB-005", "折叠硅胶水杯 500ml", "Collapsible Silicone Bottle 500ml", "water_bottle",
     "silicone", "500ml", "blue, green, pink", "poly bag", 2000,
     "2000:2.0;6000:1.75", 20, ["FDA", "LFGB"], "logo", 3, 0.2, ""),
    ("TS-GC-004", "玻璃水烟杯 500ml", "Hookah Glass 500ml", "glass_cup",
     "glass", "500ml", "clear, smoky", "bulk", 1000,
     "1000:1.8;3000:1.6", 20, ["food_grade"], "print", 4, 0.4, "AE,SA,QA,KW,OM,BH,TR"),
    ("TS-FC-005", "保温饭盒双层 1.1L", "Thermal Lunch Box 2-tier 1.1L", "food_container",
     "stainless steel 201", "1.1L", "steel + color band", "color box", 1000,
     "1000:5.2;3000:4.7", 26, ["FDA"], "logo", 2, 0.65, ""),
    ("TS-TM-004", "不锈钢随行杯 590ml", "Steel Tumbler 590ml with Straw", "travel_mug",
     "stainless steel 304", "590ml", "matte colors", "color box", 1000,
     "1000:5.5;5000:4.9", 24, ["FDA", "LFGB"], "logo, full wrap", 0, 0.4, "US,CA,GB,AU,DE"),
    ("TS-VB-008", "保温杯贴纸款 500ml", "Sticker-deco Vacuum Bottle 500ml", "insulated_bottle",
     "stainless steel 201", "500ml", "white DIY", "color box", 2000,
     "2000:3.3;8000:2.9", 22, ["FDA"], "DIY stickers", 2, 0.32, ""),
]

SUPPLIERS = [
    ("永康市金泰五金制品厂", "浙江 永康", 0.85, ["insulated_bottle", "travel_mug", "kettle"]),
    ("武义县康源杯业有限公司", "浙江 金华", 0.9, ["insulated_bottle", "food_container", "gift_set"]),
    ("永康市奥盛工贸有限公司", "浙江 永康", 0.72, ["insulated_bottle", "travel_mug", "food_container"]),
    ("宁波迅腾塑业科技有限公司", "浙江 宁波", 0.88, ["water_bottle", "baby_bottle", "food_container"]),
    ("祁东县玻璃制品厂", "湖南 衡阳", 0.8, ["glass_cup", "coffee_maker", "food_container"]),
    ("潮州市潮安区陶瓷二厂", "广东 潮州", 0.83, ["mug", "coffee_maker"]),
    ("潮州市枫溪区华光瓷厂", "广东 潮州", 0.68, ["mug", "coffee_maker"]),
    ("泉州礼盒包装制品有限公司", "福建 泉州", 0.86, ["gift_set"]),
    ("东莞贝比亲母婴用品厂", "广东 东莞", 0.91, ["baby_bottle"]),
    ("温州优帆箱包厂", "浙江 温州", 0.75, ["cooler_bag"]),
    ("临汾玻晶器皿有限公司", "山西 临汾", 0.78, ["glass_cup", "gift_set"]),
]


def seed_demo(db: Session) -> None:
    # ------------------------------------------------------------- org & user
    org = Organization(name=DEMO_ORG, default_locale="zh-CN", default_currency="USD")
    db.add(org)
    db.flush()
    db.add(Role(org_id=org.id, code="owner", name="管理员"))
    db.add(Role(org_id=org.id, code="member", name="业务员"))
    user = User(org_id=org.id, email=DEMO_EMAIL, name="张外贸（演示管理员）",
                password_hash=hash_password(DEMO_PASSWORD), role="owner")
    db.add(user)
    db.add(User(org_id=org.id, email="member@tradesense-demo.cn", name="李业务（演示成员）",
                password_hash=hash_password(DEMO_PASSWORD), role="member"))
    db.flush()

    # ------------------------------------------------------------- suppliers
    suppliers: list[Supplier] = []
    for name, region, rel, cats in SUPPLIERS:
        s = Supplier(org_id=org.id, name=name, region=region, reliability_score=rel,
                     categories_json=json.dumps(cats, ensure_ascii=False),
                     contact_name="李经理", email=f"sales{len(suppliers) + 1}@supplier-demo.cn")
        db.add(s)
        suppliers.append(s)
    db.flush()

    # ------------------------------------------------------------- products
    for row in PRODUCTS:
        (sku, name_zh, name_en, concept, material, spec, colors, packaging, moq,
         tiers, lead, certs, customization, sup_idx, weight, markets) = row
        db.add(Product(
            org_id=org.id, sku=sku, name_zh=name_zh, name_en=name_en, category=concept,
            description=f"{name_zh}；{spec}；可定制：{customization}",
            material=material, spec=spec, color=colors, packaging=packaging, moq=moq,
            price_tiers_json=json.dumps(_parse_tiers(tiers)),
            currency="USD", stock_status="made_to_order", lead_time_days=lead,
            customization=customization,
            certifications_json=json.dumps(certs),
            supplier_id=suppliers[sup_idx].id,
            keywords=f"{name_en} {concept.replace('_', ' ')} {material}",
            markets=markets, unit_weight_kg=weight,
            data_source="seed", last_verified_at=_ago(10),
        ))
    db.flush()

    # ------------------------------------------------------------- connectors
    email_acct = ConnectorAccount(org_id=org.id, connector_type="email_imap",
                                  name="演示邮箱 sales@demo-trade.cn", mode="simulated",
                                  status="disconnected", auth_state="not_authorized_simulated",
                                  config_json=json.dumps({"mailbox": "sales@demo-trade.cn",
                                                          "host": "imap.example.com", "port": 993}))
    wa_acct = ConnectorAccount(org_id=org.id, connector_type="whatsapp_cloud",
                               name="演示 WhatsApp +86138****0000", mode="simulated",
                               status="disconnected", auth_state="not_authorized_simulated",
                               config_json=json.dumps({"phone_number_id": "SIM-123", "waba_id": "SIM-WABA"}))
    form_acct = ConnectorAccount(org_id=org.id, connector_type="webform",
                                 name="独立站 demo-trade.cn 询盘表单", mode="live",
                                 status="connected", auth_state="authorized",
                                 config_json=json.dumps({"site_name": "demo-trade.cn"}))
    hook_acct = ConnectorAccount(org_id=org.id, connector_type="generic_webhook",
                                 name="n8n / 飞书 自动化 Webhook", mode="live",
                                 status="connected", auth_state="authorized",
                                 config_json=json.dumps({"note": "供自动化平台推送"}))
    db.add_all([email_acct, wa_acct, form_acct, hook_acct])
    db.flush()
    for acct in (email_acct, wa_acct, form_acct, hook_acct):
        db.add(SyncCursor(org_id=org.id, connector_account_id=acct.id, cursor_value="0"))

    # ------------------------------------------------------------- inquiries
    from .inquiries import seed_inquiries
    seed_inquiries(db, org.id, user.id)

    # ------------------------------------- run the simulated inbox pipeline once
    from ..services.connectors import run_sync

    def ingest(payload: dict) -> dict:
        from ..services.ingestion import ingest_external_message
        res = ingest_external_message(db, org.id, email_acct, payload)
        db.flush()
        return res

    run_sync(db, email_acct, ingest)
    db.add(SyncLog(org_id=org.id, connector_account_id=email_acct.id, level="info",
                   event="demo_note",
                   detail_json=json.dumps({"note": "模拟邮箱已拉取第 1 封演示邮件；再点同步可拉取第 2 封"},
                                          ensure_ascii=False)))
    db.flush()

    # ------------------------------ webhook duplicate demonstration (idempotency)
    hook_payload = {
        "external_message_id": "n8n-msg-fixed-42",
        "thread_external_id": "n8n:line@topgift-sa.com",
        "sender": "Omar Al-Farsi <omar@topgift-sa.com>",
        "text": ("Subject: Corporate gift mugs\n\nSalam, we need 3,000 ceramic mugs with our "
                 "logo for a bank event in Riyadh, DDP, budget USD 1.8/pc. What certs do you have?"),
        "received_at": _ago(2), "raw_json": {"source": "n8n demo"},
    }
    res1 = ingest_external_message(db, org.id, hook_acct, hook_payload)
    db.flush()
    res2 = ingest_external_message(db, org.id, hook_acct, dict(hook_payload))
    db.flush()
    db.add(SyncLog(org_id=org.id, connector_account_id=hook_acct.id, level="info",
                   event="webhook_demo",
                   detail_json=json.dumps({"first_ingested": not res1.get("duplicate"),
                                           "second_duplicate": bool(res2.get("duplicate")),
                                           "reason": res2.get("reason", "")}, ensure_ascii=False)))
    db.flush()

    # ------------------------------------- 比价数据（第五阶段：8 个产品第二供应商）
    second_suppliers = [
        ("TS-VB-001", 0, "永康市金泰五金制品厂", 4.15, 28),
        ("TS-VB-002", 1, "武义县康源杯业有限公司", 6.05, 26),
        ("TS-TM-001", 0, "永康市金泰五金制品厂", 4.55, 22),
        ("TS-MG-001", 6, "潮州市枫溪区华光瓷厂", 0.92, 24),
        ("TS-GC-001", 10, "临汾玻晶器皿有限公司", 3.95, 20),
        ("TS-FC-002", 4, "祁东县玻璃制品厂", 3.15, 22),
        ("TS-WB-001", 3, "宁波迅腾塑业科技有限公司", 0.98, 16),
        ("TS-GS-001", 8, "泉州礼盒包装制品有限公司", 9.25, 28),
    ]
    for sku, sup_idx, sup_name, cost, lead in second_suppliers:
        prod = db.scalar(select(Product).where(Product.org_id == org.id,
                                               Product.sku == sku))
        sup = db.scalar(select(Supplier).where(Supplier.org_id == org.id,
                                               Supplier.name == sup_name))
        if prod and sup:
            db.add(SupplierProduct(org_id=org.id, product_id=prod.id,
                                   supplier_id=sup.id, cost_price=cost,
                                   currency="CNY", moq=prod.moq,
                                   lead_time_days=lead))
    db.flush()

    # ------------------------------------------------- 货件与单证（第四阶段演示）
    from .shipments_seed import seed_shipments
    seed_shipments(db, org.id, user.id)

    # ------------------------------------------------- 漏斗阶段事件回填（第六阶段演示）
    _backfill_stage_events(db, org.id)

    audit(db, org.id, user.id, "demo.seed", "organization", org.id, {"products": len(PRODUCTS)})


def _backfill_stage_events(db: Session, org_id: int) -> None:
    """演示询盘按当前阶段回填阶段事件：new 起步沿主链推进，lost/dormant 走 quoted 分支，
    时间在 created_at 与现在之间均匀分布，让漏斗报表有真实的分布可看。"""
    from ..models import FUNNEL_NEXT, InquiryStageEvent

    now = _utcnow()
    inquiries = db.scalars(select(Inquiry).where(Inquiry.org_id == org_id)).all()
    for inq in inquiries:
        target = inq.stage or "new"
        chain = ["new"]
        if target in ("lost", "dormant"):
            chain += ["qualified", "clarifying", "quoted", target]
        else:
            while chain[-1] != target and FUNNEL_NEXT.get(chain[-1]):
                chain.append(FUNNEL_NEXT[chain[-1]])
        start = inq.created_at or now
        elapsed = max((now - start).total_seconds(), 0.0)
        step = elapsed * 0.9 / max(len(chain) - 1, 1)
        for i, stage in enumerate(chain):
            db.add(InquiryStageEvent(
                org_id=org_id, inquiry_id=inq.id,
                from_stage=chain[i - 1] if i else "",
                to_stage=stage,
                occurred_at=start + timedelta(seconds=step * i)))
    db.flush()


def _thread(db: Session, org_id: int, inq: Inquiry, channel: str = "manual"):
    t = ConversationThread(org_id=org_id, inquiry_id=inq.id, channel=channel)
    db.add(t)
    db.flush()
    return t


def _mk_inquiry(db: Session, org_id: int, user_id: int, customer: Customer | None,
                contact: Contact | None, title: str, channel: str = "manual",
                status_: str = "open", stage: str = "new", quality: str = "normal",
                created_days_ago: int = 0) -> Inquiry:
    inq = Inquiry(org_id=org_id, customer_id=customer.id if customer else None,
                  contact_id=contact.id if contact else None, title=title,
                  status=status_, stage=stage, source_channel=channel,
                  quality_flag=quality, owner_user_id=user_id)
    if created_days_ago:
        inq.created_at = _ago(created_days_ago)
    db.add(inq)
    db.flush()
    _thread(db, org_id, inq, channel)
    return inq


def _cust(db: Session, org_id: int, company: str, country: str, channel: str,
          contact_name: str, email: str, stage: str = "new", days_since_contact: int = 0) -> tuple[Customer, Contact]:
    c = Customer(org_id=org_id, company_name=company, country=country,
                 source_channel=channel, stage=stage,
                 last_contact_at=_ago(days_since_contact) if days_since_contact else None)
    db.add(c)
    db.flush()
    ct = Contact(org_id=org_id, customer_id=c.id, name=contact_name, email=email, is_primary=True)
    db.add(ct)
    db.flush()
    return c, ct


def _say(db: Session, org_id: int, inq: Inquiry, text: str, direction: str = "in",
         days_offset: int = 0, sender: str = "") -> None:
    thread = db.scalar(select(ConversationThread).where(ConversationThread.inquiry_id == inq.id))
    sent = _ago(3 + days_offset)
    add_message(db, org_id, inq, thread.id, direction=direction,
                sender=sender or ("customer" if direction == "in" else "sales"),
                text=text, sent_at=sent)


def _match(db: Session, org_id: int, inq: Inquiry) -> None:
    svc = RequirementService(db, org_id)
    persist_match_results(db, org_id, inq.id, svc.active_values(inq.id))


def _quote(db: Session, org_id: int, inq: Inquiry, sku: str, qty: int, incoterm: str,
           margin: float = 0.15, approve: bool = False, printing: bool = False,
           dest_iso: str = "", target: float | None = None, days_ago: int = 0) -> Quote:
    p = db.scalar(select(Product).where(Product.org_id == org_id, Product.sku == sku))
    out = compute_quote(QuoteInput(product=p, quantity=qty, incoterm=incoterm,
                                   margin_rate=margin, printing=printing,
                                   destination_iso=dest_iso, target_price=target))
    from ..api.routes.quotes import _next_version  # reuse version logic
    version = db.scalar(select(func.max(Quote.version)).where(
        Quote.org_id == org_id, Quote.inquiry_id == inq.id, Quote.product_id == p.id)) or 0
    version += 1
    q = Quote(org_id=org_id, inquiry_id=inq.id, product_id=p.id,
              version=version, status="draft", incoterm=incoterm, currency="USD",
              quantity=qty, unit_cost=out.unit_cost, unit_price=out.unit_price,
              customer_price=out.unit_price, total_amount=round(out.unit_price * qty, 2),
              margin_rate=margin,
              breakdown_json=json.dumps(out.breakdown, ensure_ascii=False),
              assumptions_json=json.dumps(out.assumptions, ensure_ascii=False),
              missing_json=json.dumps(out.missing, ensure_ascii=False),
              risks_json=json.dumps(out.risks, ensure_ascii=False),
              exchange_rate_json=json.dumps(out.exchange, ensure_ascii=False),
              valid_until=out.valid_until, notes=f"SKU {p.sku} {p.name_en}")
    if days_ago:
        q.created_at = _ago(days_ago)
    if target and out.unit_price > target:
        q.risks_json = json.dumps(list(out.risks) + [f"客户目标价 {target} 低于建议报价 {out.unit_price}"],
                                  ensure_ascii=False)
    db.add(q)
    db.flush()
    if approve:
        q.status = "approved"
        q.is_formal = True
        q.approved_at = _ago(days_ago) if days_ago else _utcnow()
        inq.status = "quoted"
        inq.stage = "quoted"
    return q


