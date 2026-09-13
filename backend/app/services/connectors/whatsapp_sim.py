"""WhatsApp Cloud API connector — webhook-driven, with simulated mode.

Webhook payload (Meta format) is normalized to the common PulledMessage shape.
Without real platform credentials the account stays clearly marked simulated.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .base import BaseConnector, PulledMessage, connector_meta


def normalize_whatsapp_payload(payload: dict) -> list[dict]:
    """Extract text messages from a WhatsApp Cloud API webhook payload."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = value.get("contacts", [])
            name = (contacts[0] or {}).get("profile", {}).get("name", "") if contacts else ""
            for msg in value.get("messages", []):
                if msg.get("type") == "text":
                    out.append({
                        "external_message_id": msg.get("id", ""),
                        "thread_external_id": f"wa:{msg.get('from', name)}",
                        "sender": f"{name} <wa:{msg.get('from', '')}>".strip(),
                        "text": (msg.get("text") or {}).get("body", ""),
                        "timestamp": msg.get("timestamp"),
                        "raw": msg,
                    })
    return out


@connector_meta("whatsapp_cloud", label="WhatsApp Cloud API", channel="whatsapp",
                required_config=["phone_number_id", "waba_id"],
                env_keys=["WHATSAPP_TOKEN", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET"],
                live_supported=True,
                description="WhatsApp Cloud API Webhook 接入；缺少平台凭据时使用模拟连接器。")
class SimulatedWhatsAppConnector(BaseConnector):
    connector_type = "whatsapp_cloud"

    def health_check(self) -> dict:
        base = super().health_check()
        if self.account.mode == "simulated":
            base["note"] = "模拟 WhatsApp 连接器：未配置 WHATSAPP_TOKEN，仅支持 Webhook 模拟测试"
        return base

    def pull_messages(self, cursor: str | None) -> tuple[list[PulledMessage], str]:
        # WhatsApp is webhook-push; pull returns nothing in live mode.
        return [], cursor or "0"

    def handle_webhook(self, payload: dict) -> list[dict]:
        """Normalize a webhook body into ingest payloads (called by the route)."""
        msgs = normalize_whatsapp_payload(payload)
        results = []
        for m in msgs:
            ts = m.get("timestamp")
            received = (datetime.fromtimestamp(int(ts), tz=timezone.utc)
                        if ts and str(ts).isdigit() else datetime.now(timezone.utc))
            results.append({
                "external_message_id": m["external_message_id"],
                "thread_external_id": m["thread_external_id"],
                "sender": m["sender"], "text": m["text"],
                "received_at": received, "attachments": [],
                "raw_json": {"webhook": m["raw"], "simulated": self.account.mode == "simulated"},
            })
        return results

    def normalize_message(self, raw: dict) -> PulledMessage:
        return PulledMessage(
            external_message_id=raw.get("external_message_id", ""),
            thread_external_id=raw.get("thread_external_id", ""),
            sender=raw.get("sender", ""), text=raw.get("text", ""),
            received_at=datetime.now(timezone.utc), raw=raw,
        )
