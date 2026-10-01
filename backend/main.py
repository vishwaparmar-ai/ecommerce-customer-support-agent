from __future__ import annotations

import logging
from fastapi import FastAPI

from backend.api.auth import router as auth_router
from backend.api.chat import router as conversations_router
from backend.api.orders import router as order_router
from backend.api.products import router as products_router
from backend.api.refund import router as refund_router
from backend.api.returns import router as return_router
from backend.api.support import router as support_router
from backend.core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ShopFlow AI - E-commerce Customer Support Agent",
    description="Deterministic backend and AI agent system for e-commerce customer support.",
    version="1.0.0",
)

# Core Business & Auth Routers (Phase 1)
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(order_router)
app.include_router(return_router)
app.include_router(refund_router)
app.include_router(support_router)

# AI Conversation Router
app.include_router(conversations_router)


@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for container orchestrators and uptime checks."""
    return {"status": "healthy"}