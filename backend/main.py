from fastapi import FastAPI
from backend.api.auth import router as auth_router
from backend.api.orders import router as order_router
from backend.api.returns import router as return_router
from backend.api.refund import router as refund_router
from backend.api.ticket import router as ticket_router
from backend.api.chat import router as conversations_router
import logging
from backend.core.logging import setup_logging


setup_logging()

app = FastAPI()

logger = logging.getLogger(__name__)

app=FastAPI(title="Customer Support Agent")

app.include_router(auth_router)
app.include_router(order_router)
app.include_router(return_router)
app.include_router(refund_router)
app.include_router(ticket_router)
app.include_router(conversations_router)

@app.get("/")
def check_status():
    return {"status":"healthy"}