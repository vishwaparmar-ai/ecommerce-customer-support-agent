from fastapi import FastAPI
from api.auth import router as auth_router
from api.orders import router as order_router
from api.returns import router as return_router
import logging
from core.logging import setup_logging


setup_logging()

app = FastAPI()

logger = logging.getLogger(__name__)

app=FastAPI(title="Customer Support Agent")

app.include_router(auth_router)
app.include_router(order_router)
app.include_router(return_router)

@app.get("/")
def check_status():
    return {"status":"healthy"}