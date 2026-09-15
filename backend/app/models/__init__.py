"""Import all models so Base.metadata and Alembic see the full schema."""
from .base import Base, OrgMixin, TZDateTime, TimestampMixin, utcnow
from .org import Organization, Role, User
from .customer import Contact, Customer
from .inquiry import ConversationMessage, ConversationThread, Inquiry
from .requirement import ClarificationLog, RequirementHistory, RequirementSlot, RequirementState
from .product import Certification, Product, ProductVariant, Supplier, SupplierProduct
from .quote import PriceRule, Quote, QuoteItem, QuoteSheet
from .matching import MatchResult
from .followup import FollowUpTask
from .reply import ReplyDraft
from .connector import ConnectorAccount, ExternalMessage, SyncCursor, SyncLog
from .misc import AuditEvent, KnowledgeDocument
from .import_preview import ImportPreview, purge_expired
from .shipment import (Shipment, Document, DocumentField, ShipmentIssue,
                        DocumentFieldChange, DocRuleConfig, SHIPMENT_STATUSES,
                        DOC_TYPES, RULE_CODES, DEFAULT_REQUIRED_DOCS)

__all__ = [
    "Base", "OrgMixin", "TimestampMixin", "utcnow",
    "Organization", "Role", "User",
    "Customer", "Contact",
    "Inquiry", "ConversationThread", "ConversationMessage",
    "RequirementState", "RequirementSlot", "RequirementHistory", "ClarificationLog",
    "Product", "ProductVariant", "Supplier", "SupplierProduct", "Certification",
    "Quote", "QuoteItem", "QuoteSheet", "PriceRule",
    "MatchResult",
    "FollowUpTask",
    "ReplyDraft",
    "ConnectorAccount", "ExternalMessage", "SyncCursor", "SyncLog",
    "KnowledgeDocument", "AuditEvent", "ImportPreview", "purge_expired",
    "Shipment", "Document", "DocumentField", "ShipmentIssue", "DocumentFieldChange",
    "DocRuleConfig",
    "SHIPMENT_STATUSES", "DOC_TYPES", "RULE_CODES", "DEFAULT_REQUIRED_DOCS",
]
