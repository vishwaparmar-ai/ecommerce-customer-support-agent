from fastapi import FastAPI
from api.auth import router as auth_router

app=FastAPI(title="Customer Support Agent")

app.include_router(auth_router)

@app.get("/")
def check_status():
    return {"status":"healthy"}