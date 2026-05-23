"""
Модуль администрирования (F5): управление КР, пользователями
"""

import os
import hashlib
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from .models import ClinicalGuideline, ChunkMetadata, Doctor
from .ingestion import ingestion_pipeline
from .indexing import indexing_service
from .config import config

logger = logging.getLogger(__name__)


class AdminService:
    """Сервис административных функций"""

    def _calculate_md5_from_bytes(self, content: bytes) -> str:
        """Вычисление MD5 из содержимого файла"""
        return hashlib.md5(content).hexdigest()

    def get_all_guidelines(self, db: Session) -> List[Dict[str, Any]]:
        """Получение всех клинических рекомендаций"""
        guidelines = db.query(ClinicalGuideline).order_by(ClinicalGuideline.id.desc()).all()
        return [
            {
                "id": g.id,
                "title": g.title,
                "version": g.version,
                "year": g.year,
                "is_active": g.is_active,
                "total_chunks": g.total_chunks,
                "total_pages": g.total_pages,
                "uploaded_at": g.uploaded_at.isoformat() if g.uploaded_at else None,
                "md5_hash": g.md5_hash[:8] + "..."
            }
            for g in guidelines
        ]

    def delete_guideline(self, db: Session, guideline_id: int) -> bool:
        """Удаление клинической рекомендации"""
        guideline = db.query(ClinicalGuideline).filter(ClinicalGuideline.id == guideline_id).first()
        if not guideline:
            return False

        # Удаление из ChromaDB
        indexing_service.delete_chunks_by_guideline(guideline_id)

        # Удаление метаданных
        db.query(ChunkMetadata).filter(ChunkMetadata.guideline_id == guideline_id).delete()

        # Удаление файла
        if guideline.file_path and os.path.exists(guideline.file_path):
            try:
                os.remove(guideline.file_path)
            except Exception as e:
                logger.warning(f"Could not delete file {guideline.file_path}: {e}")

        db.delete(guideline)
        db.commit()

        # Обновление BM25
        from .retriever import retriever
        retriever.refresh_bm25()

        return True

    def get_status(self, db: Session) -> Dict[str, Any]:
        """Получение статуса базы знаний"""
        active_guidelines = db.query(ClinicalGuideline).filter(ClinicalGuideline.is_active == True).count()
        total_guidelines = db.query(ClinicalGuideline).count()
        total_chunks = db.query(ChunkMetadata).count()
        chroma_chunk_count = indexing_service.get_chunk_count()

        return {
            "active_guidelines": active_guidelines,
            "total_guidelines": total_guidelines,
            "total_chunks": total_chunks,
            "chroma_chunk_count": chroma_chunk_count,
            "chroma_collection_exists": indexing_service.collection_exists()
        }

    def upload_guideline(
        self,
        db: Session,
        file_content: bytes,
        filename: str,
        title: str,
        version: str,
        year: int,
        uploaded_by: int
    ) -> Dict[str, Any]:
        """Загрузка новой КР"""
        md5_hash = self._calculate_md5_from_bytes(file_content)

        # Проверка дубля
        existing = db.query(ClinicalGuideline).filter(ClinicalGuideline.md5_hash == md5_hash).first()
        if existing:
            return {"success": False, "error": f"Duplicate: {existing.title} already exists"}

        # Сохранение файла
        upload_dir = config.UPLOAD_PATH
        os.makedirs(upload_dir, exist_ok=True)
        safe_filename = f"{md5_hash}_{filename}"
        file_path = os.path.join(upload_dir, safe_filename)

        with open(file_path, "wb") as f:
            f.write(file_content)

        try:
            # Обработка PDF
            chunks, _, total_pages = ingestion_pipeline.process_pdf(
                file_path,
                {"title": title, "version": version, "year": year, "uploaded_by": uploaded_by}
            )

            # Сохранение в БД
            guideline = ClinicalGuideline(
                title=title,
                version=version,
                year=year,
                md5_hash=md5_hash,
                file_path=file_path,
                uploaded_by=uploaded_by,
                role_id=2,
                is_active=True,
                total_pages=total_pages,
                total_chunks=len(chunks)
            )
            db.add(guideline)
            db.flush()

            # Индексация в ChromaDB
            indexing_service.index_chunks(chunks, guideline.id)

            # Сохранение метаданных
            for chunk in chunks:
                chunk_meta = ChunkMetadata(
                    chunk_id=chunk["chunk_id"],
                    guideline_id=guideline.id,
                    uploaded_by=uploaded_by,
                    role_id=2,
                    chunk_text=chunk["text"][:1000],
                    page_number=chunk.get("page_number"),
                    chunk_index=chunk.get("chunk_index", 0),
                    bm25_indexed=True
                )
                db.add(chunk_meta)

            db.commit()

            # Обновление BM25
            from .retriever import retriever
            retriever.refresh_bm25()

            return {"success": True, "guideline_id": guideline.id, "chunks": len(chunks)}

        except Exception as e:
            db.rollback()
            if os.path.exists(file_path):
                os.remove(file_path)
            return {"success": False, "error": str(e)}

    def reindex_guideline(self, db: Session, guideline_id: int) -> bool:
        """Переиндексация КР"""
        guideline = db.query(ClinicalGuideline).filter(ClinicalGuideline.id == guideline_id).first()
        if not guideline:
            return False

        from .ingestion import process_and_index
        try:
            process_and_index(
                guideline.file_path,
                guideline.uploaded_by,
                guideline.title,
                guideline.version,
                guideline.year,
                db
            )
            return True
        except Exception as e:
            logger.error(f"Reindex failed: {e}")
            return False

    def upload_multiple_guidelines(
        self,
        db: Session,
        files_content: List[bytes],
        filenames: List[str],
        uploaded_by: int
    ) -> Dict[str, Any]:
        """Пакетная загрузка КР"""
        results = []
        for content, filename in zip(files_content, filenames):
            title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")
            result = self.upload_guideline(
                db, content, filename, title, "1.0", datetime.now().year, uploaded_by
            )
            result["filename"] = filename
            results.append(result)

        return {"success": True, "results": results}


admin_service = AdminService()