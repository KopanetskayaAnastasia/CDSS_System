"""
Подключение к PostgreSQL
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import logging

from .models import Base
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# PostgreSQL
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "cdss_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Создание всех таблиц и инициализация справочных данных"""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        from .models import Role
        if db.query(Role).count() == 0:
            roles = [
                Role(role_name="Doctor",
                     description="Врач - формулировка запросов, просмотр ответов, ведение диалогов"),
                Role(role_name="Admin",
                     description="Администратор - загрузка PDF КР, управление версиями, просмотр логов")
            ]
            db.add_all(roles)
            db.commit()
            logger.info("Роли инициализированы")
            print("Роли инициализированы")
    except Exception as e:
        logger.error(f"Ошибка при инициализации ролей: {e}")
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    """Dependency для FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()