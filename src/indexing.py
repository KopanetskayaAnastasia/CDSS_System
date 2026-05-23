"""
Модуль индексации (F1): векторизация и запись в ChromaDB
"""

import chromadb
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path

from .config import config

logger = logging.getLogger(__name__)


class IndexingService:
    """Сервис для индексации фрагментов в ChromaDB"""

    def __init__(self):
        self.chroma_path = Path(config.CHROMA_PATH)
        self.chroma_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Connecting to ChromaDB at {self.chroma_path}")
        self.client = chromadb.PersistentClient(path=str(self.chroma_path))

        try:
            self.collection = self.client.get_collection(config.CHROMA_COLLECTION)
            logger.info(f"Using existing collection: {config.CHROMA_COLLECTION}")
        except ValueError:
            self.collection = self.client.create_collection(
                name=config.CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Created new collection: {config.CHROMA_COLLECTION}")

        logger.info(f"Loading embedding model: {config.EMBEDDING_MODEL}")
        self.embedder = SentenceTransformer(config.EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")

    def _embed_chunks(self, texts: List[str]) -> List[List[float]]:
        """Векторизация текстов с префиксом 'passage: ' для E5"""
        if not texts:
            return []
        prefixed_texts = [f"passage: {text}" for text in texts]
        embeddings = self.embedder.encode(prefixed_texts, normalize_embeddings=True)
        return embeddings.tolist()

    def index_chunks(
        self,
        chunks: List[Dict[str, Any]],
        guideline_id: int,
        batch_size: int = 100
    ) -> List[str]:
        """
        Индексация чанков в ChromaDB с пакетной обработкой
        """
        if not chunks:
            logger.warning("No chunks to index")
            return []

        chunk_ids = [chunk["chunk_id"] for chunk in chunks]
        texts = [chunk["text"] for chunk in chunks]

        metadatas = []
        for chunk in chunks:
            meta = chunk.get("metadata", {}).copy()
            meta["guideline_id"] = guideline_id
            metadatas.append(meta)

        logger.info(f"Embedding {len(chunks)} chunks...")
        try:
            embeddings = self._embed_chunks(texts)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

        try:
            existing = self.collection.get(where={"guideline_id": guideline_id})
            if existing["ids"]:
                self.collection.delete(ids=existing["ids"])
                logger.info(f"Deleted {len(existing['ids'])} old chunks for guideline {guideline_id}")

            for i in range(0, len(chunks), batch_size):
                batch_end = min(i + batch_size, len(chunks))
                self.collection.add(
                    ids=chunk_ids[i:batch_end],
                    embeddings=embeddings[i:batch_end],
                    metadatas=metadatas[i:batch_end],
                    documents=texts[i:batch_end]
                )
                logger.debug(f"Indexed batch {i//batch_size + 1}: {i+1}-{batch_end} of {len(chunks)}")

            logger.info(f"Indexed {len(chunks)} chunks for guideline {guideline_id}")

        except Exception as e:
            logger.error(f"ChromaDB indexing failed: {e}")
            raise

        return chunk_ids

    def delete_chunks_by_guideline(self, guideline_id: int) -> int:
        """Удаление всех чанков, связанных с КР"""
        try:
            existing = self.collection.get(where={"guideline_id": guideline_id})
            if existing["ids"]:
                self.collection.delete(ids=existing["ids"])
                deleted_count = len(existing["ids"])
                logger.info(f"Deleted {deleted_count} chunks for guideline {guideline_id}")
                return deleted_count
            return 0
        except Exception as e:
            logger.error(f"Deletion failed: {e}")
            return 0

    def delete_chunk_by_id(self, chunk_id: str) -> bool:
        """Удаление одного чанка по ID"""
        try:
            self.collection.delete(ids=[chunk_id])
            logger.info(f"Deleted chunk {chunk_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete chunk {chunk_id}: {e}")
            return False

    def get_chunk_count(self) -> int:
        """Получение общего количества чанков в базе"""
        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"Failed to get chunk count: {e}")
            return 0

    def get_chunk_count_by_guideline(self, guideline_id: int) -> int:
        """Получение количества чанков для конкретной КР"""
        try:
            result = self.collection.get(where={"guideline_id": guideline_id})
            return len(result["ids"]) if result and "ids" in result else 0
        except Exception:
            return 0

    def collection_exists(self) -> bool:
        """Проверка существования коллекции"""
        try:
            self.client.get_collection(config.CHROMA_COLLECTION)
            return True
        except ValueError:
            return False

    def clear_collection(self) -> bool:
        """Очистка всей коллекции (для тестов)"""
        try:
            self.client.delete_collection(config.CHROMA_COLLECTION)
            self.collection = self.client.create_collection(
                name=config.CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"}
            )
            logger.warning(f"Cleared collection: {config.CHROMA_COLLECTION}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            return False

    def refresh_bm25(self, retriever) -> bool:
        """Обновление BM25 индекса в ретривере"""
        try:
            if retriever and hasattr(retriever, 'refresh_bm25'):
                retriever.refresh_bm25()
                logger.info("BM25 index refreshed")
                return True
        except Exception as e:
            logger.error(f"BM25 refresh failed: {e}")
        return False


indexing_service = IndexingService()