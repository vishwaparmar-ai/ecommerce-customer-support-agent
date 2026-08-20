from fastapi import FastAPI
from api.auth import router as auth_router
from api.orders import router as order_router

app=FastAPI(title="Customer Support Agent")

app.include_router(auth_router)
app.include_router(order_router)

@app.get("/")
def check_status():
    return {"status":"healthy"}