"""
Конфигурация приложения из переменных окружения
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Централизованная конфигурация всех компонентов"""

    # ========== PostgreSQL ==========
    DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
    DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    DB_NAME = os.getenv("POSTGRES_DB", "cdss_db")
    DB_USER = os.getenv("POSTGRES_USER", "postgres")
    DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # ========== Redis ==========
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_SECONDS", "86400"))  # 24 часа

    # ========== ChromaDB ==========
    CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
    CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "clinical_guidelines")
    CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")  # для клиент-серверного режима
    CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))

    # ========== ML Models ==========
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
    CROSS_ENCODER_MODEL = os.getenv("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    # ========== Search Parameters ==========
    SEARCH_K = int(os.getenv("SEARCH_K", "5"))
    ALPHA = float(os.getenv("ALPHA", "0.7"))  # вес семантического поиска

    # ========== Chunking ==========
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "102"))

    # ========== GigaChat API ==========
    GIGACHAT_API_URL = os.getenv("GIGACHAT_API_URL", "https://gigachat.devices.sberbank.ru/api/v1")
    GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")
    GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    GIGACHAT_TIMEOUT = int(os.getenv("GIGACHAT_TIMEOUT", "120"))  # 2 минуты
    GIGACHAT_AUTH_URL = os.getenv("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
    GIGACHAT_RQUID = os.getenv("GIGACHAT_RQUID", "027bb905-645e-4909-8e4c-abe601a83f99")

    # ========== JWT Auth ==========
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

    # ========== Admin User ==========
    ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    ADMIN_FULL_NAME = os.getenv("ADMIN_FULL_NAME", "System Administrator")
    ADMIN_SPECIALTY = os.getenv("ADMIN_SPECIALTY", "Administrator")

    # ========== File Upload ==========
    UPLOAD_PATH = os.getenv("UPLOAD_PATH", "./docs/clinical_guidelines")
    LOGS_PATH = os.getenv("LOGS_PATH", "./logs")
    MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))  # 50 MB

    # ========== LLM Settings ==========
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))


config = Config()