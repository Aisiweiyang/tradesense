"""Demo inquiries covering the 10 required business scenarios (+ extras).

S1  德国客户定制保温杯（多轮：改色/改量/目的港 + FOB + LFGB）
S2  美国客户食品接触产品（FDA/BPA-free，寄样）
S3  中东客户带 Logo 礼品（DDP，Prop65/FDA）
S4  客户修改数量、颜色和目的港（多轮覆盖 + L/C）
S5  目标价格低于成本（亏损风险）
S6  缺少必要认证（食品接触未提认证 → 追问）
S7  没有完全匹配产品（替代方案/最近候选）
S8  报价后长期未回复（跟进提醒）
S9  询盘信息极少（低质量标记）
S10 同一消息被 Webhook 重复推送（幂等，见 run.py）
S11 "any color" → unconstrained
S12 同一消息两种颜色 → conflicting
S13 休眠客户重新激活
S14 CPC 认证儿童杯
S15 样品 + 付款方式多轮
S16 已成交（漏斗终点演示，含完整阶段链）
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Contact, Customer, FollowUpTask, Inquiry, ReplyDraft
from ..services.reply_drafts import build_variables, generate_draft
from ..services.requirement_service import RequirementService
from .run import _cust, _match, _mk_inquiry, _quote, _say


def _task(db: Session, org_id: int, user_id: int, title: str, inq: Inquiry | None,
          due: datetime, ttype: str, priority: str = "normal", reason: str = "") -> None:
    db.add(FollowUpTask(org_id=org_id, title=title,
                        inquiry_id=inq.id if inq else None,
                        customer_id=inq.customer_id if inq else None,
                        task_type=ttype, due_at=due, priority=priority,
                        reason_json=json.dumps({"reason": reason}, ensure_ascii=False),
                        created_by_user_id=user_id))


def seed_inquiries(db: Session, org_id: int, user_id: int) -> None:
    from .run import _ago
    svc = RequirementService(db, org_id)

    # ---- S1 德国保温杯：多轮修改（规格核心示例） ----------------------------
    c1, t1 = _cust(db, org_id, "HausKonzept GmbH", "Germany", "email",
                   "Anna Schmidt", "anna.schmidt@hauskonzept-gmbh.de", "clarifying", 4)
    i1 = _mk_inquiry(db, org_id, user_id, c1, t1, "Vacuum insulated bottles for German market",
                     channel="email", created_days_ago=5)
    _say(db, org_id, i1, "Hello, I need 500 blue stainless-steel bottles (vacuum insulated, 500ml) "
                         "for our kitchen brand.", days_offset=3)
    _say(db, org_id, i1, "Actually, make them black, increase the quantity to 1,000, "
                         "and ship to Hamburg.", days_offset=2)
    _say(db, org_id, i1, "Also quote on FOB basis please. LFGB certification is mandatory. "
                         "Target price around USD 4.5/pc.", days_offset=1)
    _match(db, org_id, i1)

    # ---- S2 美国 FDA 摇摇杯 ---------------------------------------------------
    c2, t2 = _cust(db, org_id, "KitchenDoor LLC", "United States", "webform",
                   "John Miller", "john.miller@kitchendoor-us.com", "clarifying", 6)
    i2 = _mk_inquiry(db, org_id, user_id, c2, t2, "FDA tritan shaker bottles 10k",
                     channel="webform", status_="clarifying", stage="clarifying",
                     created_days_ago=7)
    _say(db, org_id, i2, "We are looking for 10,000 pcs of 700ml tritan shaker bottles, "
                         "FDA food grade and BPA free, ship to Los Angeles, FOB. "
                         "Budget 1.2 USD/pc. Need samples before order.", days_offset=4)
    _match(db, org_id, i2)

    # ---- S3 中东 DDP 礼品马克杯 ----------------------------------------------
    c3, t3 = _cust(db, org_id, "TopGift Trading", "Saudi Arabia", "email",
                   "Omar Al-Farsi", "omar@topgift-sa.com", "negotiating", 3)
    i3 = _mk_inquiry(db, org_id, user_id, c3, t3, "Corporate gift mugs with logo 3000 DDP",
                     channel="email", status_="clarifying", stage="negotiating",
                     created_days_ago=8)
    _say(db, org_id, i3, "Salam, we need 3,000 ceramic mugs (350ml) with our logo for a bank "
                         "event, gift box packaging, DDP Dubai. Target price USD 1.8/pc.",
         days_offset=6)
    _say(db, org_id, i3, "What certifications do you have? Prop 65 is fine, FDA preferred.",
         days_offset=5)
    _match(db, org_id, i3)
    _quote(db, org_id, i3, "TS-MG-001", 3000, "DDP", margin=0.18, approve=False,
           printing=True, dest_iso="AE", target=1.8, days_ago=4)

    # ---- S4 多轮修改数量/颜色/目的港 ------------------------------------------
    c4, t4 = _cust(db, org_id, "Vitrine Home BV", "Netherlands", "email",
                   "Pieter Janssen", "pieter@vitrinehome.nl", "clarifying", 2)
    i4 = _mk_inquiry(db, org_id, user_id, c4, t4, "Glass cups — updated order",
                     channel="email", status_="clarifying", created_days_ago=6)
    _say(db, org_id, i4, "Please quote your borosilicate glass cups 320ml set, quantity 500.",
         days_offset=4)
    _say(db, org_id, i4, "Change of plan: quantity to 2,000 sets, clear color, deliver to "
                         "Rotterdam by end of October.", days_offset=3)
    _say(db, org_id, i4, "Payment by L/C at sight is acceptable for us.", days_offset=2)
    _match(db, org_id, i4)
    _quote(db, org_id, i4, "TS-GC-001", 2000, "FOB", margin=0.18,
           dest_iso="NL", days_ago=1)

    # ---- S5 目标价低于成本 ------------------------------------------------------
    c5, t5 = _cust(db, org_id, "BudgetLine Wholesale", "United Kingdom", "email",
                   "Harry Wilson", "harry@budgetline.co.uk", "new", 1)
    i5 = _mk_inquiry(db, org_id, user_id, c5, t5, "50k cheap thermal bottles — very low target",
                     channel="email", created_days_ago=3)
    _say(db, org_id, i5, "Looking for 50,000 pcs vacuum flask 500ml, target price 1.2 USD FOB, "
                         "bulk packing ok, no cert needed. Ship to Felixstowe.", days_offset=1)
    _match(db, org_id, i5)
    _quote(db, org_id, i5, "TS-VB-006", 50000, "FOB", margin=0.15, target=1.2, days_ago=2)

    # ---- S6 缺认证 ---------------------------------------------------------------
    c6, t6 = _cust(db, org_id, "BergSport Outfitters", "Germany", "email",
                   "Lena Fischer", "lena@bergsport-outfitters.de", "new", 1)
    i6 = _mk_inquiry(db, org_id, user_id, c6, t6, "Hiking vacuum flasks 750ml EXW",
                     channel="email", created_days_ago=2)
    _say(db, org_id, i6, "We want 3,000 pcs hiking vacuum flasks 750ml, EXW, gold color, "
                         "delivery within 60 days.", days_offset=0)
    _match(db, org_id, i6)

    # ---- S7 无完全匹配 -----------------------------------------------------------
    c7, t7 = _cust(db, org_id, "Aurora Gifts OY", "Finland", "webform",
                   "Mikko Virtanen", "mikko@auroragifts.fi", "new", 1)
    i7 = _mk_inquiry(db, org_id, user_id, c7, t7, "Smart heated bottle with speaker?",
                     channel="webform", created_days_ago=2)
    _say(db, org_id, i7, "Hello, I am looking for a 1.2 liter smart heated bottle with bluetooth "
                         "speaker and temperature display, quantity 800 pcs, destination Helsinki.",
         days_offset=0)
    _match(db, org_id, i7)

    # ---- S8 报价后未回复 ----------------------------------------------------------
    c8, t8 = _cust(db, org_id, "Casa Verde SRL", "Italy", "email",
                   "Giulia Romano", "giulia@casaverde.it", "quoted", 25)
    i8 = _mk_inquiry(db, org_id, user_id, c8, t8, "Enamel mugs 6000pcs — quoted, silent",
                     channel="email", status_="quoted", stage="quoted", created_days_ago=30)
    _say(db, org_id, i8, "We need 6,000 enamel camping mugs 360ml with full print, FOB, "
                         "delivery 40 days.", days_offset=26)
    _quote(db, org_id, i8, "TS-MG-004", 6000, "FOB", margin=0.2, approve=True,
           printing=True, dest_iso="IT", days_ago=22)
    # backdate so "quoted-no-reply" detection triggers in the demo workload
    i8.updated_at = _ago(21)
    db.flush()

    # ---- S9 低质量询盘 -------------------------------------------------------------
    c9, t9 = _cust(db, org_id, "win", "", "webform", "win", "win88@qq.com", "new", 1)
    i9 = _mk_inquiry(db, org_id, user_id, c9, t9, "hi", channel="webform",
                     quality="low_quality", created_days_ago=1)
    _say(db, org_id, i9, "hi", days_offset=0)

    # ---- S11 any color → unconstrained ---------------------------------------------
    c11, t11 = _cust(db, org_id, "MetroRetail Group", "United Kingdom", "email",
                     "Sarah Chen", "sarah.chen@metroretail.co.uk", "clarifying", 3)
    i11 = _mk_inquiry(db, org_id, user_id, c11, t11, "Travel mugs 1000 FOB Felixstowe",
                      channel="email", status_="clarifying", created_days_ago=4)
    _say(db, org_id, i11, "Quote for 1,000 travel mugs 450ml please, FOB Felixstowe. "
                          "Any color is fine.", days_offset=2)
    _say(db, org_id, i11, "If plastic parts are used, they must be BPA free.", days_offset=1)
    _match(db, org_id, i11)

    # ---- S12 颜色冲突 ---------------------------------------------------------------
    c12, t12 = _cust(db, org_id, "NordicHome AS", "Norway", "email",
                     "Erik Berg", "erik@nordichome.no", "clarifying", 2)
    i12 = _mk_inquiry(db, org_id, user_id, c12, t12, "Lunch boxes — color question",
                      channel="email", status_="clarifying", created_days_ago=3)
    _say(db, org_id, i12, "Please quote 5,000 pcs PP lunch box 900ml. For the color we are torn "
                          "between green and navy blue, need your advice.", days_offset=1)
    _match(db, org_id, i12)

    # ---- S13 休眠客户 -----------------------------------------------------------------
    c13, t13 = _cust(db, org_id, "AlNoor Trading EST", "Saudi Arabia", "email",
                     "Faisal Al-Harbi", "faisal@alnoor-trading.sa", "dormant", 40)
    i13 = _mk_inquiry(db, org_id, user_id, c13, t13, "Gift sets Ramadan campaign",
                      channel="email", status_="quoted", stage="dormant", created_days_ago=45)
    _say(db, org_id, i13, "For our Ramadan campaign: 2,000 gift sets (bottle + mug), "
                          "DDP Dammam, target USD 9/pc.", days_offset=42)
    _quote(db, org_id, i13, "TS-GS-001", 2000, "DDP", margin=0.16, approve=True,
           printing=True, dest_iso="SA", target=9.0, days_ago=40)

    # ---- S14 CPC 儿童杯 ----------------------------------------------------------------
    c14, t14 = _cust(db, org_id, "TinySteps Pty", "Australia", "email",
                     "Emma Walker", "emma@tinysteps.au", "clarifying", 2)
    i14 = _mk_inquiry(db, org_id, user_id, c14, t14, "Toddler sippy cups with CPC",
                      channel="email", status_="clarifying", created_days_ago=2)
    _say(db, org_id, i14, "Interested in 8,000 toddler sippy cups 300ml, must have CPC and FDA, "
                          "destination Melbourne, need quote within 30 days.", days_offset=0)
    _match(db, org_id, i14)

    # ---- S15 样品 + 付款 ----------------------------------------------------------------
    c15, t15 = _cust(db, org_id, "Maison du Thé", "France", "email",
                     "Claire Dubois", "claire@maisonuthe.fr", "sample", 5)
    i15 = _mk_inquiry(db, org_id, user_id, c15, t15, "Glass tea cups with sample request",
                      channel="email", status_="clarifying", stage="sample",
                      created_days_ago=6)
    _say(db, org_id, i15, "Bonjour, we would like 3,000 double-wall glass cups 400ml for our "
                          "tea shops, CIF Le Havre. Please arrange samples first.", days_offset=3)
    _say(db, org_id, i15, "Payment terms: we usually do 30% deposit and 70% against B/L copy.",
         days_offset=2)
    _match(db, org_id, i15)

    # ---- S16 已成交（漏斗终点演示） --------------------------------------------------
    c16, t16 = _cust(db, org_id, "GiftingHouse Ltd", "United Kingdom", "email",
                     "Oliver Grant", "oliver@giftinghouse.co.uk", "won", 12)
    i16 = _mk_inquiry(db, org_id, user_id, c16, t16, "Travel mugs 1200pcs — corporate gift order",
                      channel="email", status_="won", stage="won", created_days_ago=40)
    _say(db, org_id, i16, "We need 1,200 insulated travel mugs 450ml with our logo, FOB Felixstowe, "
                          "delivery within 45 days of order.", days_offset=38)
    _match(db, org_id, i16)
    _quote(db, org_id, i16, "TS-TM-001", 1200, "FOB", margin=0.18, approve=True,
           printing=True, dest_iso="GB", days_ago=30)
    inq_status = db.get(Inquiry, i16.id)
    inq_status.status = "won"
    inq_status.stage = "won"
    db.flush()

    # ------------------------------------------------------------ 回复草稿
    for inq, kind, tone in ((i1, "first_reply", "formal"),
                            (i2, "ask_missing_info", "friendly"),
                            (i5, "polite_rejection", "formal"),
                            (i9, "ask_missing_info", "concise")):
        values = svc.active_values(inq.id)
        variables = build_variables(inq, values, {"customer_name": "there"})
        data = generate_draft(kind, tone, variables, values)
        db.add(ReplyDraft(org_id=org_id, inquiry_id=inq.id, kind=kind, tone=tone,
                          subject_en=data["subject_en"], body_en=data["body_en"],
                          body_zh=data["body_zh"],
                          variables_json=json.dumps(variables, ensure_ascii=False),
                          facts_used_json=json.dumps(data["facts_used"], ensure_ascii=False),
                          needs_confirmation_json=json.dumps(data["needs_confirmation"],
                                                             ensure_ascii=False)))

    # ------------------------------------------------------------ 跟进任务
    _task(db, org_id, user_id, "回复 Anna：已改黑色/1000pcs/汉堡港，发送 FOB 报价", i1,
          _ago(-1), "quote", "high", "需求已基本齐全，客户等待报价")
    _task(db, org_id, user_id, "John：寄送 Tritan 摇摇杯样品（FDA/BPA-free 型号）", i2,
          _ago(-2), "sample", "high", "客户明确要求先寄样")
    _task(db, org_id, user_id, "向 Omar 提供 DDP 迪拜含税拆解（认证清单待补）", i3,
          _ago(0), "quote", "high", "DDP 报价需人工核实税率")
    _task(db, org_id, user_id, "Erik：确认午餐盒颜色（绿色 vs 藏青）", i12,
          _ago(-1), "follow_up", "normal", "客户对颜色犹豫，需给出建议")
    _task(db, org_id, user_id, "Giulia：报价已 3 周未回复，发送报价跟进邮件", i8,
          _ago(-3), "quote_follow_up", "high", "报价后长期未回复")
    _task(db, org_id, user_id, "Lena：确认保温壶是否需要 FDA/LFGB 食品级认证", i6,
          _ago(0), "check_cert", "high", "食品接触类产品缺少认证要求")
    _task(db, org_id, user_id, "Faisal：斋月项目重新激活（客户 40 天未联系）", i13,
          _ago(-1), "reactivate", "normal", "休眠客户，季度性活动可能在准备")
    _task(db, org_id, user_id, "Claire：安排双层玻璃杯样品并确认 30/70 付款", i15,
          _ago(-2), "sample", "normal", "客户要求先打样")
    _task(db, org_id, user_id, "Harry：低价 5 万只订单——先内部核算是否可做", i5,
          _ago(0), "review_quality", "high", "目标价低于成本，需要管理层决策")
    _task(db, org_id, user_id, "Pieter：确认 10 月底交期能否达成", i4,
          _ago(0), "follow_up", "normal", "客户要求 end of October 交期")

    db.flush()
