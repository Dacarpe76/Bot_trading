from fastapi import FastAPI, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core import security, database
from app.models import Base
from app.services.bot_engine import bot_engine
import uvicorn
import asyncio

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# DB Init
Base.metadata.create_all(bind=database.engine)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(bot_engine.start())

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Retrieve data from bot_engine/db
    return templates.TemplateResponse("dashboard.html", {"request": request, "positions": bot_engine.active_positions})

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
