"""API router aggregation."""
from fastapi import APIRouter

from .routes import auth, connectors, customers, dashboard, followups, imports, inquiries, products, quotes, replies, shipments

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(inquiries.router)
api_router.include_router(products.router)
api_router.include_router(imports.router)
api_router.include_router(quotes.router)
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
