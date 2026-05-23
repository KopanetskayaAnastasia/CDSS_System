"""
FastAPI приложение – главная точка входа
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db, engine
from .api import router as api_router  # ← ИСПРАВЛЕНО: правильный импорт

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("Starting CDSS API...")
    init_db()
    print("✅ CDSS API started")
    yield
    logger.info("Shutting down CDSS API...")
    engine.dispose()
    logger.info("Connections closed")


app = FastAPI(
    title="CDSS API",
    version="1.0.0",
    description="Система поддержки принятия врачебных решений (RAG-based)",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(api_router)


@app.get("/")
def root():
    return {
        "message": "CDSS API is running",
        "version": "1.0.0",
        "status": "ok"
    }


@app.get("/ping")
def ping():
    return {"ping": "pong"}