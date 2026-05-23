"""
CDSS - Clinical Decision Support System
"""

__version__ = "1.0.0"
__author__ = "Kopanetskaya A.K."

from .config import config
from .database import init_db, get_db
from .models import Base
from .retriever import retriever, HybridMedicalRetriever
from .generator import Generator
from .memory import memory_manager, MemoryManager
from .ingestion import ingestion_pipeline, PDFIngestionPipeline
from .indexing import indexing_service, IndexingService
from .admin import admin_service, AdminService
from .auth import auth_handler, AuthHandler
from .utils import log_audit

__all__ = [
    "config",
    "init_db",
    "get_db",
    "Base",
    "retriever",
    "HybridMedicalRetriever",
    "Generator",
    "memory_manager",
    "MemoryManager",
    "ingestion_pipeline",
    "PDFIngestionPipeline",
    "indexing_service",
    "IndexingService",
    "admin_service",
    "AdminService",
    "auth_handler",
    "AuthHandler",
    "log_audit",
]