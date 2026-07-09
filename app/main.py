"""
Texas Worksheet Generator – FastAPI application
================================================
Routes
  GET  /              → serve SPA frontend
  POST /api/generate  → return worksheet (hybrid: DB or LLM)
  POST /api/rate      → rate a question
  GET  /api/stats     → library statistics
  GET  /health        → uptime probe
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db import init_db, migrate_db
from app.routers.worksheets import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("worksheets")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    migrate_db()
    logger.info("Database ready")
    yield


app = FastAPI(
    title="Texas Worksheet Generator",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(router)
