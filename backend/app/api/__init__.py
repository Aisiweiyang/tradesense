"""API router aggregation."""
from fastapi import APIRouter

from .routes import ai, attachments, auth, connectors, customers, dashboard, followups, imports, inquiries, knowledge, products, quotes, quote_sheets, replies, shipments, fx

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(inquiries.router)
api_router.include_router(products.router)
api_router.include_router(imports.router)
api_router.include_router(quotes.router)
api_router.include_router(quote_sheets.router)
api_router.include_router(replies.router)
api_router.include_router(followups.router)
api_router.include_router(followups.suppliers_router)
api_router.include_router(shipments.router)
api_router.include_router(connectors.router)
api_router.include_router(connectors.webhooks_router)
api_router.include_router(connectors.public_router)
api_router.include_router(dashboard.router)
api_router.include_router(dashboard.audit_router)
api_router.include_router(dashboard.synclog_router)
api_router.include_router(dashboard.glossary_router)
api_router.include_router(dashboard.funnel_router)
api_router.include_router(knowledge.router)
api_router.include_router(fx.router)
api_router.include_router(ai.router)
api_router.include_router(attachments.router)
