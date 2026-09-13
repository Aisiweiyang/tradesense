"""Standalone website inquiry form + generic webhook connectors (push model)."""
from __future__ import annotations

from .base import BaseConnector, PulledMessage, connector_meta


@connector_meta("webform", label="独立站询盘表单", channel="webform",
                required_config=["site_name"], live_supported=True,
                description="独立站表单 POST 接口 + 可嵌入聊天组件；来源追踪与防重复提交内置。")
class WebFormConnector(BaseConnector):
    connector_type = "webform"

    def health_check(self) -> dict:
        base = super().health_check()
        base["form_endpoint"] = f"/api/public/webform/{self.account.id}"
        base["widget_endpoint"] = f"/api/public/widget/{self.account.id}.js"
        return base

    def pull_messages(self, cursor):
        return [], cursor or "0"

    def normalize_message(self, raw: dict) -> PulledMessage:
        raise NotImplementedError("webform messages arrive via push endpoint")


@connector_meta("generic_webhook", label="通用 Webhook（n8n/Zapier/Make 等）", channel="webhook",
                required_config=[], live_supported=True,
                description="通用入站 Webhook，可对接 n8n、Zapier、Make、飞书、钉钉或内部 CRM。")
class GenericWebhookConnector(BaseConnector):
    connector_type = "generic_webhook"

    def health_check(self) -> dict:
        base = super().health_check()
        base["webhook_endpoint"] = f"/api/webhooks/generic/{self.account.id}"
        return base

    def pull_messages(self, cursor):
        return [], cursor or "0"

    def normalize_message(self, raw: dict) -> PulledMessage:
        raise NotImplementedError("webhook messages arrive via push endpoint")


def normalize_generic_payload(payload: dict) -> dict:
    """Accept common shapes: {text|message|body|content}, optional sender/email."""
    text = payload.get("text") or payload.get("message") or payload.get("body") or payload.get("content") or ""
    if not isinstance(text, str):
        text = str(text)
    sender = (payload.get("sender") or payload.get("email") or payload.get("from")
              or payload.get("name") or "")
    ext_id = str(payload.get("id") or payload.get("message_id") or payload.get("external_message_id") or "")
    return {"text": text, "sender": str(sender), "external_message_id": ext_id,
            "raw_json": payload}
