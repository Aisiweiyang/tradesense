"""Reply draft generator: 10 template kinds, EN body + ZH parallel text,
tone selection, editable variables, fact provenance and explicit
human-confirmation checklist. Drafts are never sent automatically.
"""
from __future__ import annotations

from ..models import Inquiry

CONTEXT_DEFAULTS = {
    "our_name": "TradeSense Sales Team",
    "company_zh": "我方公司",
}


def _tone_greeting(tone: str) -> tuple[str, str]:
    if tone == "formal":
        return ("Dear {customer_name},", "尊敬的{customer_name_zh}：")
    if tone == "concise":
        return ("Hi {customer_name},", "{customer_name_zh}，您好：")
    return ("Dear {customer_name},\n\nHope this email finds you well.", "尊敬的{customer_name_zh}：\n\n您好！")


def _tone_closing(tone: str) -> tuple[str, str]:
    if tone == "formal":
        return ("We look forward to your reply.\n\nBest regards,\n{our_name}",
                "期待您的回复。\n\n此致\n商祺\n{our_name}")
    if tone == "concise":
        return ("Thanks!\n{our_name}", "谢谢！\n{our_name}")
    return ("Please feel free to reach out with any questions. We look forward to working with you.\n\n"
            "Best regards,\n{our_name}",
            "如有任何问题欢迎随时联系我们，期待与您合作。\n\n祝好\n{our_name}")


def build_variables(inquiry: Inquiry, values: dict, extra: dict | None = None) -> dict:
    def v(fld):
        s = values.get(fld) or {}
        return s.get("value") or ""

    def n(fld):
        s = values.get(fld) or {}
        return s.get("normalized") or ""

    vars_ = {
        "customer_name": extra.get("customer_name", "there") if extra else "there",
        "customer_name_zh": extra.get("customer_name", "客户") if extra else "客户",
        "our_name": extra.get("our_name", CONTEXT_DEFAULTS["our_name"]) if extra else CONTEXT_DEFAULTS["our_name"],
        "product_en": v("product") or "the items",
        "product_zh": v("product") or "相关产品",
        "quantity": n("quantity") or "TBD",
        "color": v("color") or "-",
        "material": v("material") or "-",
        "destination": v("destination_port") or v("destination_country") or "-",
        "incoterm": v("incoterm") or "FOB",
        "lead_time": v("lead_time") or "about 30-35 days after order confirmation",
        "spec": v("spec") or "-",
        "certification": v("certification") or "-",
        "quote_price": extra.get("quote_price", "") if extra else "",
        "quote_validity": extra.get("quote_validity", "30 days") if extra else "30 days",
        "questions_en": extra.get("questions_en", "") if extra else "",
        "questions_zh": extra.get("questions_zh", "") if extra else "",
        "product_list": extra.get("product_list", "several suitable models") if extra else "several suitable models",
        "delay_reason": extra.get("delay_reason", "a production scheduling issue") if extra else "a production scheduling issue",
        "new_date": extra.get("new_date", "the revised date below") if extra else "the revised date below",
        "alternative_product": extra.get("alternative_product", "a similar model") if extra else "a similar model",
        "last_quote_ref": extra.get("last_quote_ref", "our previous quotation") if extra else "our previous quotation",
    }
    return vars_


# ---------------------------------------------------------------- templates
def _first_reply(vars_, tone):
    g, gz = _tone_greeting(tone)
    c, cz = _tone_closing(tone)
    qty = f"for a quantity of {vars_['quantity']} pcs" if vars_["quantity"] not in ("TBD", "") else ""
    body = f"""{g}

Thank you for your inquiry about {vars_['product_en']} {qty}. We are a professional manufacturer and would be glad to support you.

To prepare an accurate quotation, could you kindly confirm:
{vars_['questions_en']}

In the meantime, please see our key details:
- Product: {vars_['product_en']}
- Specification: {vars_['spec']}
- Material: {vars_['material']}
- Customization: logo printing / OEM available

{c}"""
    zh = f"""{gz}

感谢您关于{vars_['product_zh']}的询盘（数量：{vars_['quantity']}）。我们是专业生产厂家，很乐意为您服务。

为提供准确报价，请您确认以下信息：
{vars_['questions_zh']}

同时提供我方关键信息供参考：
- 产品：{vars_['product_zh']}
- 规格：{vars_['spec']}
- 材质：{vars_['material']}
- 定制：支持 Logo 印刷 / OEM

{cz}"""
    return "Re: Your Inquiry – " + vars_["product_en"], body, zh


def _ask_missing_info(vars_, tone):
    g, gz = _tone_greeting(tone)
    c, cz = _tone_closing(tone)
    body = f"""{g}

Thank you for your message. To move forward with {vars_['product_en']}, we still need a few details:

{vars_['questions_en']}

Once we receive the above, we will send you a full quotation within 24 hours.

{c}"""
    zh = f"""{gz}

感谢您的来信。为推进{vars_['product_zh']}的事宜，我们还需要确认以下信息：

{vars_['questions_zh']}

收到上述信息后，我们将在 24 小时内提供完整报价。

{cz}"""
    return "A Few Details Needed to Quote – " + vars_["product_en"], body, zh


def _product_recommend(vars_, tone):
    g, gz = _tone_greeting(tone)
    c, cz = _tone_closing(tone)
    body = f"""{g}

Based on your requirements ({vars_['product_en']}, qty {vars_['quantity']}, destination: {vars_['destination']}), we recommend the following options:

{vars_['product_list']}

All of them can be customized with your logo. Free samples of stock colors are available; freight collected.

{c}"""
    zh = f"""{gz}

根据您的需求（{vars_['product_zh']}、数量 {vars_['quantity']}、目的地：{vars_['destination']}），我们推荐以下型号：

{vars_['product_list']}

以上型号均可加印贵司 Logo。现货颜色可提供免费样品，运费到付。

{cz}"""
    return "Recommended Models – " + vars_["product_en"], body, zh


def _sample(vars_, tone):
    g, gz = _tone_greeting(tone)
    c, cz = _tone_closing(tone)
    body = f"""{g}

Thank you for your interest in samples of {vars_['product_en']}.

- Sample cost: free for existing models (1-2 pcs)
- Courier freight: collected or prepaid (approx. USD 25-40 by DHL/FedEx)
- Lead time: samples within 3-5 working days

Please confirm your courier account number or let us know if you prefer prepaid freight.

{c}"""
    zh = f"""{gz}

感谢您对{vars_['product_zh']}样品的兴趣。

- 样品费用：现有型号免费提供 1-2 件
- 快递运费：到付或预付（DHL/FedEx 约 25-40 美元）
- 样品时间：3-5 个工作日内寄出

请确认您的快递账号，或告知是否需要预付运费。

{cz}"""
    return "Sample Arrangement – " + vars_["product_en"], body, zh


def _quote_send(vars_, tone):
    g, gz = _tone_greeting(tone)
    c, cz = _tone_closing(tone)
    body = f"""{g}

Please find our quotation for {vars_['product_en']} below:

- Product: {vars_['product_en']} ({vars_['spec']})
- Quantity: {vars_['quantity']} pcs
- Unit price: {vars_['quote_price']} {vars_['incoterm']}
- Payment: T/T (30% deposit, 70% against copy of B/L)
- Delivery: {vars_['lead_time']}
- Validity: {vars_['quote_validity']}

The price is calculated based on current material and freight costs.

{c}"""
    zh = f"""{gz}

以下是{vars_['product_zh']}的报价：

- 产品：{vars_['product_zh']}（{vars_['spec']}）
- 数量：{vars_['quantity']} 件
- 单价：{vars_['quote_price']}（{vars_['incoterm']} 口径）
- 付款：T/T（30% 定金，70% 见提单副本）
- 交期：{vars_['lead_time']}
- 有效期：{vars_['quote_validity']}

以上价格基于当前原材料与运费成本核算。

{cz}"""
    return f"Quotation – {vars_['product_en']} ({vars_['quantity']} pcs)", body, zh


def _quote_follow_up(vars_, tone):
    g, gz = _tone_greeting(tone)
    c, cz = _tone_closing(tone)
    body = f"""{g}

I am following up on {vars_['last_quote_ref']} for {vars_['product_en']} sent recently.

May I know if the price and specification work for you? If any adjustment is needed (quantity, packaging, or trade term), we are happy to fine-tune the offer.

{c}"""
    zh = f"""{gz}

想跟进一下此前发给您的{vars_['product_zh']}报价（{vars_['last_quote_ref']}）。

请问价格和规格是否符合您的预期？如需调整（数量、包装或贸易条款），我们很乐意为您优化方案。

{cz}"""
    return "Follow-up: Our Quotation – " + vars_["product_en"], body, zh


def _delay_notice(vars_, tone):
    g, gz = _tone_greeting(tone)
    c, cz = _tone_closing(tone)
    body = f"""{g}

We are writing to inform you that, due to {vars_['delay_reason']}, the delivery of your order for {vars_['product_en']} will be delayed. The new estimated delivery date is {vars_['new_date']}.

We sincerely apologize for the inconvenience and are doing everything possible to expedite production.

{c}"""
    zh = f"""{gz}

很抱歉地通知您，由于{vars_['delay_reason']}，您的{vars_['product_zh']}订单将延期交付，新预计交期为{vars_['new_date']}。

对此给您带来的不便我们深表歉意，正全力加快生产进度。

{cz}"""
    return "Delivery Schedule Update – " + vars_["product_en"], body, zh


def _alternative_offer(vars_, tone):
    g, gz = _tone_greeting(tone)
    c, cz = _tone_closing(tone)
    body = f"""{g}

Thank you for your inquiry. Unfortunately, the exact specification you requested is currently beyond our production range.

However, we would like to suggest {vars_['alternative_product']}, which covers most of your requirements and is available at a competitive price. Would you like to see its details and samples?

{c}"""
    zh = f"""{gz}

感谢您的询盘。很遗憾，您要求的规格目前超出我们的生产范围。

不过我们建议参考{vars_['alternative_product']}，它可满足您的大部分需求且价格具有竞争力。是否需要我们提供详细资料和样品？

{cz}"""
    return "Alternative Proposal – " + vars_["product_en"], body, zh


def _polite_rejection(vars_, tone):
    g, gz = _tone_greeting(tone)
    c, cz = _tone_closing(tone)
    body = f"""{g}

Thank you for reaching out. After careful evaluation, we regret that we are unable to meet your current requirements (specification / price / compliance) at the quality level we stand for.

We truly appreciate your understanding, and we would be glad to cooperate on future projects where our capabilities fit better.

{c}"""
    zh = f"""{gz}

感谢您的垂询。经过谨慎评估，很抱歉我们目前无法在坚持质量标准的前提下满足您的要求（规格/价格/合规）。

感谢您的理解，期待未来在更匹配的项目上与您合作。

{cz}"""
    return "Re: Your Inquiry", body, zh


def _reactivation(vars_, tone):
    g, gz = _tone_greeting(tone)
    c, cz = _tone_closing(tone)
    body = f"""{g}

It has been a while since our last conversation about {vars_['product_en']}. I was wondering if the project is still ongoing?

If the previous offer needs adjustment or you have new requirements, just let me know — we keep all your specifications on file.

{c}"""
    zh = f"""{gz}

距离上次沟通{vars_['product_zh']}已经有一段时间了，想了解一下这个项目是否仍在进行？

如果之前的报价需要调整，或者您有新的需求，请随时告知——您的需求资料我们都已存档。

{cz}"""
    return "Checking In – " + vars_["product_en"], body, zh


TEMPLATES = {
    "first_reply": _first_reply,
    "ask_missing_info": _ask_missing_info,
    "product_recommend": _product_recommend,
    "sample": _sample,
    "quote_send": _quote_send,
    "quote_follow_up": _quote_follow_up,
    "delay_notice": _delay_notice,
    "alternative_offer": _alternative_offer,
    "polite_rejection": _polite_rejection,
    "reactivation": _reactivation,
}

# which facts each template consumes (provenance shown to the salesperson)
FACT_FIELDS = {
    "first_reply": ["product", "quantity", "spec", "material"],
    "ask_missing_info": ["product", "quantity"],
    "product_recommend": ["product", "quantity", "destination_country", "destination_port"],
    "sample": ["product"],
    "quote_send": ["product", "quantity", "spec", "incoterm", "lead_time"],
    "quote_follow_up": ["product"],
    "delay_notice": ["product", "lead_time"],
    "alternative_offer": ["product"],
    "polite_rejection": ["product"],
    "reactivation": ["product"],
}

# what MUST still be confirmed by a human before sending
NEEDS_CONFIRMATION = {
    "first_reply": ["公司介绍与产能描述需人工核实", "样品政策需按公司实际情况确认"],
    "ask_missing_info": ["承诺的报价时限（24 小时）需人工确认可达成"],
    "product_recommend": ["推荐型号与现货颜色需人工核对产品库", "免费样品政策需确认"],
    "sample": ["样品政策与快递费用需人工确认"],
    "quote_send": ["价格必须由人工批准后才算正式报价", "付款条件需按公司财务要求确认", "报价有效期需确认"],
    "quote_follow_up": ["引用的报价单号/内容需人工核对"],
    "delay_notice": ["延误原因与新交期必须由人工填写确认"],
    "alternative_offer": ["替代型号需人工确认可生产", "替代方案价格需人工确认"],
    "polite_rejection": ["拒绝原因需人工确认措辞与事实一致"],
    "reactivation": ["存档需求信息需人工确认仍然有效"],
}


def generate_draft(kind: str, tone: str, variables: dict, values: dict) -> dict:
    if kind not in TEMPLATES:
        raise ValueError(f"unknown reply kind: {kind}")
    subject, body_en, body_zh = TEMPLATES[kind](variables, tone)
    facts = []
    for f in FACT_FIELDS.get(kind, []):
        s = values.get(f) or {}
        if s.get("value") or s.get("normalized"):
            facts.append({"field": f, "value": s.get("value") or s.get("normalized"),
                          "source_message_id": s.get("source_message_id")})
    return {
        "kind": kind, "tone": tone, "subject_en": subject.format(**variables),
        "body_en": body_en, "body_zh": body_zh,
        "variables": variables, "facts_used": facts,
        # 副本：调用方会往里追加确认项，不能污染 NEEDS_CONFIRMATION 全局表
        "needs_confirmation": list(NEEDS_CONFIRMATION.get(kind, [])),
    }
