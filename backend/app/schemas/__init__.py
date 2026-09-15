"""Pydantic v2 API schemas (I/O validation layer)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


def _orm(v: Any) -> Any:
    return v


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ common
class Page(BaseModel):
    items: list = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


# ------------------------------------------------------------------ auth
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class BootstrapIn(BaseModel):
    org_name: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(ORMModel):
    id: int
    email: str
    name: str
    role: str
    locale: str
    org_id: int


class AuthStatus(BaseModel):
    needs_bootstrap: bool


# ------------------------------------------------------------------ customers
class ContactIn(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    whatsapp: str = ""
    position: str = ""
    is_primary: bool = False


class ContactOut(ContactIn, ORMModel):
    id: int
    customer_id: int


class CustomerIn(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    country: str = ""
    source_channel: str = "manual"
    tags: str = ""
    priority: str = "normal"
    stage: str = "new"
    notes: str = ""
    next_follow_up_at: Optional[datetime] = None
    contacts: list[ContactIn] = []


class CustomerUpdate(BaseModel):
    company_name: Optional[str] = None
    country: Optional[str] = None
    tags: Optional[str] = None
    priority: Optional[str] = None
    stage: Optional[str] = None
    notes: Optional[str] = None
    next_follow_up_at: Optional[datetime] = None


class CustomerOut(ORMModel):
    id: int
    company_name: str
    country: str
    source_channel: str
    tags: str
    priority: str
    stage: str
    notes: str
    lead_score: int
    lead_score_factors: str
    last_contact_at: Optional[datetime] = None
    next_follow_up_at: Optional[datetime] = None
    created_at: datetime
    contacts: list[ContactOut] = []


# ------------------------------------------------------------------ inquiries
class InquiryCreate(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    title: str = ""
    customer_id: Optional[int] = None
    source_channel: str = "manual"
    sender: str = ""


class InquiryOut(ORMModel):
    id: int
    customer_id: Optional[int] = None
    title: str
    status: str
    stage: str
    language: str
    completeness: int
    quality_flag: str
    source_channel: str
    summary_json: str
    created_at: datetime
    updated_at: datetime


class InquiryDetail(InquiryOut):
    raw_text: str


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    direction: str = "in"  # in=来自客户, out=我方发出(仅记录)


class MessageOut(ORMModel):
    id: int
    inquiry_id: int
    direction: str
    sender: str
    sent_at: Optional[datetime] = None
    raw_content: str
    parse_json: str
    process_status: str


class SlotOut(ORMModel):
    field: str
    value: str
    raw_value: str
    normalized_value: str
    unit: str
    status: str
    confidence: float
    locked: bool
    confirmed: bool
    source_message_id: Optional[int] = None
    history_values: str


class SlotSetIn(BaseModel):
    field: str
    value: str = Field(min_length=1, max_length=2000)
    lock: bool = False


# ------------------------------------------------------------------ products
class PriceTier(BaseModel):
    min_qty: int = 1
    unit_price: float


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name_zh: str = ""
    name_en: str = ""
    category: str = ""
    description: str = ""
    material: str = ""
    spec: str = ""
    size: str = ""
    color: str = ""
    packaging: str = ""
    moq: int = Field(default=1, ge=1)
    price_tiers: list[PriceTier] = []
    currency: str = "USD"
    stock_status: str = "made_to_order"
    lead_time_days: int = Field(default=30, ge=0)
    customization: str = ""
    certifications: list[str] = []
    supplier_id: Optional[int] = None
    image_url: str = ""
    keywords: str = ""
    markets: str = ""
    unit_weight_kg: Optional[float] = None


class ProductUpdate(BaseModel):
    name_zh: Optional[str] = None
    name_en: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    material: Optional[str] = None
    spec: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    packaging: Optional[str] = None
    moq: Optional[int] = Field(default=None, ge=1)
    price_tiers: Optional[list[PriceTier]] = None
    currency: Optional[str] = None
    stock_status: Optional[str] = None
    lead_time_days: Optional[int] = Field(default=None, ge=0)
    customization: Optional[str] = None
    certifications: Optional[list[str]] = None
    supplier_id: Optional[int] = None
    image_url: Optional[str] = None
    keywords: Optional[str] = None
    markets: Optional[str] = None
    unit_weight_kg: Optional[float] = None
    is_active: Optional[bool] = None


class ProductOut(ORMModel):
    id: int
    sku: str
    name_zh: str
    name_en: str
    category: str
    description: str
    material: str
    spec: str
    size: str
    color: str
    packaging: str
    moq: int
    price_tiers_json: str
    currency: str
    stock_status: str
    lead_time_days: int
    customization: str
    certifications_json: str
    supplier_id: Optional[int] = None
    image_url: str
    keywords: str
    markets: str
    unit_weight_kg: Optional[float] = None
    is_active: bool
    data_source: str
    updated_at: datetime


class BulkIds(BaseModel):
    ids: list[int]
    is_active: bool


# ------------------------------------------------------------------ quotes
class QuoteCreateIn(BaseModel):
    inquiry_id: int
    product_id: int
    quantity: int = Field(gt=0)
    incoterm: str = "FOB"
    currency: str = "USD"
    margin_rate: float = Field(default=0.15, ge=0, lt=1)
    destination_iso: str = ""
    printing: bool = False
    mold_lump: float = Field(default=0.0, ge=0)
    packaging_unit: Optional[float] = None
    # None=未显式指定：按成本币种→报价币种查汇率表（未配置回退 1.0）；显式传入则优先于汇率表
    exchange_rate: Optional[float] = Field(default=None, gt=0)
    customer_price: Optional[float] = None
    valid_days: int = Field(default=30, ge=1, le=180)
    supplier_product_id: Optional[int] = None


class QuoteOut(ORMModel):
    id: int
    inquiry_id: int
    product_id: Optional[int] = None
    version: int
    status: str
    incoterm: str
    currency: str
    quantity: int
    unit_cost: float
    unit_price: float
    customer_price: float
    total_amount: float
    margin_rate: float
    breakdown_json: str
    assumptions_json: str
    missing_json: str
    risks_json: str
    exchange_rate_json: str
    valid_until: Optional[datetime] = None
    is_formal: bool
    approved_by_user_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: datetime


class QuotePriceIn(BaseModel):
    customer_price: float = Field(gt=0)
    notes: str = ""


# ------------------------------------------------------------------ replies
class ReplyGenerateIn(BaseModel):
    kind: str
    tone: str = "friendly"
    extra: dict = {}


class ReplyOut(ORMModel):
    id: int
    inquiry_id: int
    kind: str
    tone: str
    subject_en: str
    body_en: str
    body_zh: str
    variables_json: str
    facts_used_json: str
    needs_confirmation_json: str
    status: str
    updated_at: datetime


class ReplyUpdateIn(BaseModel):
    subject_en: Optional[str] = None
    body_en: Optional[str] = None
    body_zh: Optional[str] = None
    tone: Optional[str] = None
    status: Optional[str] = None


# ------------------------------------------------------------------ follow-ups
class FollowUpIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    inquiry_id: Optional[int] = None
    customer_id: Optional[int] = None
    description: str = ""
    task_type: str = "follow_up"
    due_at: Optional[datetime] = None
    priority: str = "normal"
    reason: dict = {}


class FollowUpOut(ORMModel):
    id: int
    inquiry_id: Optional[int] = None
    customer_id: Optional[int] = None
    title: str
    description: str
    task_type: str
    due_at: Optional[datetime] = None
    status: str
    priority: str
    reason_json: str
    created_at: datetime


class FollowUpStatusIn(BaseModel):
    status: str  # done/snoozed/cancelled/pending
    due_at: Optional[datetime] = None


# ------------------------------------------------------------------ connectors
class ConnectorAccountIn(BaseModel):
    connector_type: str
    name: str = Field(min_length=1, max_length=200)
    config: dict = {}


class ConnectorAccountOut(ORMModel):
    id: int
    connector_type: str
    name: str
    mode: str
    status: str
    auth_state: str
    last_sync_at: Optional[datetime] = None
    last_error: str
    created_at: datetime


class SyncResult(BaseModel):
    ok: bool
    ingested: int = 0
    skipped_duplicates: int = 0
    error: str = ""


# ------------------------------------------------------------------ misc
class MatchOut(ORMModel):
    id: int
    product_id: int
    rank: int
    total_score: float
    scores_json: str
    met_json: str
    unmet_json: str
    excluded: bool
    exclude_reason: str
    is_alternative: bool
    data_snapshot_json: str


class HistoryOut(ORMModel):
    id: int
    field: str
    change_type: str
    old_value: str
    new_value: str
    old_status: str
    new_status: str
    actor: str
    note: str
    source_message_id: Optional[int] = None
    created_at: datetime


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    region: str = ""
    contact_name: str = ""
    phone: str = ""
    email: str = ""
    reliability_score: float = Field(default=0.8, ge=0, le=1)
    notes: str = ""


class SupplierOut(SupplierIn, ORMModel):
    id: int
    is_active: bool


TokenOut.model_rebuild()


# ------------------------------------------------------------------ knowledge
class KnowledgeIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = ""
    tags: str = ""  # 逗号分隔，如 "欧盟,认证,LFGB"


class KnowledgeOut(ORMModel):
    id: int
    title: str
    content: str
    tags: str


TokenOut.model_rebuild()
