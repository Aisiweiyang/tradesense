"""Connector registry package."""
from ...models import ConnectorAccount
from .base import BaseConnector, CONNECTOR_REGISTRY, PulledMessage, connector_meta, run_sync
from .email_sim import SimulatedEmailConnector
from .whatsapp_sim import SimulatedWhatsAppConnector, normalize_whatsapp_payload
from .webform import WebFormConnector, GenericWebhookConnector, normalize_generic_payload

__all__ = [
    "BaseConnector", "CONNECTOR_REGISTRY", "PulledMessage", "connector_meta", "run_sync",
    "SimulatedEmailConnector", "SimulatedWhatsAppConnector",
    "WebFormConnector", "GenericWebhookConnector", "normalize_generic_payload",
    "normalize_whatsapp_payload", "get_connector", "registry_meta",
]


def get_connector(db, account: ConnectorAccount) -> BaseConnector:
    meta = CONNECTOR_REGISTRY.get(account.connector_type)
    if meta is None:
        raise ValueError(f"未知连接器类型: {account.connector_type}")
    return meta["class"](db, account)


def registry_meta() -> list[dict]:
    """Public description of all supported connector types."""
    out = []
    for ctype, meta in CONNECTOR_REGISTRY.items():
        out.append({
            "type": ctype, "label": meta["label"], "channel": meta["channel"],
            "required_config": meta["required_config"], "env_keys": meta["env_keys"],
            "live_supported": meta["live_supported"], "description": meta["description"],
        })
    return out
