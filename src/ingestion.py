"""
Модуль ингейстинга (F1): загрузка PDF, парсинг, фрагментация
Поддерживает пакетную загрузку
"""

import hashlib
import os
from typing import List, Dict, Any, Tuple
from pathlib import Path
import logging

from .config import config

logger = logging.getLogger(__name__)


class PDFIngestionPipeline:
    """Пайплайн обработки PDF документов"""

    def __init__(self):
        self.chunk_size = config.CHUNK_SIZE
        self.chunk_overlap = config.CHUNK_OVERLAP
        self._tokenizer = None

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            try:
                import tiktoken
                self._tokenizer = tiktoken.get_encoding("cl100k_base")
                logger.info("TikToken tokenizer loaded")
            except ImportError:
                logger.warning("TikToken not available, using word-based chunking")
                self._tokenizer = None
        return self._tokenizer

    def calculate_md5(self, file_path: str) -> str:
        """Вычисление MD5-хэша файла для контроля дублей"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def extract_text_from_pdf(self, file_path: str) -> str:
        """Извлечение текста из PDF (использует pypdf)"""
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            text = ""
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
        except ImportError:
            logger.error("pypdf not installed")
            raise
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise

    def extract_text_with_pages(self, file_path: str) -> List[Tuple[int, str]]:
        """Извлечение текста с номерами страниц"""
        pages_text = []
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            for page_num, page in enumerate(reader.pages, 1):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    pages_text.append((page_num, page_text.strip()))
        except Exception as e:
            logger.error(f"Failed to extract text with pages: {e}")
            raise
        logger.info(f"Extracted {len(pages_text)} pages from {file_path}")
        return pages_text

    def split_into_chunks_by_tokens(self, text: str) -> List[Dict[str, Any]]:
        """Разбивка текста на чанки по токенам"""
        if self.tokenizer is None:
            return self.split_into_chunks(text)

        tokens = self.tokenizer.encode(text)
        chunks = []
        step = self.chunk_size - self.chunk_overlap
        if step <= 0:
            step = self.chunk_size

        for i in range(0, len(tokens), step):
            chunk_tokens = tokens[i:i + self.chunk_size]
            if len(chunk_tokens) < self.chunk_size // 4:
                continue
            chunk_text = self.tokenizer.decode(chunk_tokens)
            chunks.append({
                "text": chunk_text,
                "index": len(chunks),
                "token_start": i,
                "token_end": i + len(chunk_tokens)
            })

        logger.info(f"Split text into {len(chunks)} chunks by tokens (total tokens: {len(tokens)})")
        return chunks

    def split_into_chunks_with_pages(self, pages_text: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
        """Разбивка текста на чанки с сохранением номеров страниц"""
        if not pages_text:
            return []

        chunks = []
        current_chunk = ""
        current_start_page = pages_text[0][0]
        current_chunk_index = 0

        for page_num, page_text in pages_text:
            temp_chunk = current_chunk + " " + page_text if current_chunk else page_text
            if self.tokenizer:
                temp_len = len(self.tokenizer.encode(temp_chunk))
            else:
                temp_len = len(temp_chunk.split())

            if temp_len > self.chunk_size:
                if current_chunk:
                    chunks.append({
                        "text": current_chunk,
                        "page_number": current_start_page,
                        "chunk_index": current_chunk_index
                    })
                    current_chunk_index += 1
                    current_chunk = page_text
                    current_start_page = page_num
                else:
                    if self.tokenizer:
                        tokens = self.tokenizer.encode(page_text)
                        step = self.chunk_size - self.chunk_overlap
                        for j in range(0, len(tokens), step):
                            chunk_tokens = tokens[j:j + self.chunk_size]
                            if len(chunk_tokens) < self.chunk_size // 4:
                                continue
                            chunks.append({
                                "text": self.tokenizer.decode(chunk_tokens),
                                "page_number": page_num,
                                "chunk_index": current_chunk_index
                            })
                            current_chunk_index += 1
                        current_chunk = ""
                    else:
                        words = page_text.split()
                        for j in range(0, len(words), self.chunk_size):
                            chunk_words = words[j:j + self.chunk_size]
                            chunks.append({
                                "text": " ".join(chunk_words),
                                "page_number": page_num,
                                "chunk_index": current_chunk_index
                            })
                            current_chunk_index += 1
                        current_chunk = ""
            else:
                current_chunk = temp_chunk

        if current_chunk:
            chunks.append({
                "text": current_chunk,
                "page_number": current_start_page,
                "chunk_index": current_chunk_index
            })

        logger.info(f"Split into {len(chunks)} chunks")
        return chunks

    def extract_text_with_docling(self, file_path: str):
        try:
            from docling.document_converter import DocumentConverter
            converter = DocumentConverter()
            result = converter.convert(file_path)
            text = result.document.export_to_text()
            total_pages = len(result.document.pages) if hasattr(result.document, 'pages') else 0
            return text, total_pages
        except ImportError:
            text = self.extract_text_from_pdf(file_path)
            return text, 0

    def split_into_chunks(self, text: str) -> List[Dict[str, Any]]:
        """Разбивка текста на чанки (по словам, для совместимости)"""
        if not text or not text.strip():
            return []

        chunks = []
        words = text.split()
        step = self.chunk_size - self.chunk_overlap
        if step <= 0:
            step = self.chunk_size

        for i in range(0, len(words), step):
            chunk_words = words[i:i + self.chunk_size]
            if len(chunk_words) < self.chunk_size // 4:
                continue

            chunks.append({
                "text": " ".join(chunk_words),
                "index": len(chunks),
                "start_word": i,
                "end_word": i + len(chunk_words)
            })

        logger.info(f"Split text into {len(chunks)} chunks by words")
        return chunks

    def process_pdf(
        self,
        file_path: str,
        metadata: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], str, int]:
        """Полный цикл обработки PDF"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        md5_hash = self.calculate_md5(file_path)
        logger.info(f"Processing PDF: {file_path}, MD5: {md5_hash}")

        try:
            pages_text = self.extract_text_with_pages(file_path)
            total_pages = len(pages_text)
            raw_chunks = self.split_into_chunks_with_pages(pages_text)
        except Exception as e:
            logger.warning(f"Page extraction failed: {e}, falling back to simple extraction")
            text, total_pages = self.extract_text_with_docling(file_path)
            raw_chunks = self.split_into_chunks_by_tokens(text)

        if not raw_chunks:
            raise ValueError(f"Text could not be split into chunks from: {file_path}")

        chunks = []
        base_id = f"{metadata['title']}_{metadata['version']}".replace(" ", "_").replace("/", "_")

        for i, chunk in enumerate(raw_chunks):
            chunks.append({
                "chunk_id": f"{base_id}_{i}",
                "text": chunk["text"],
                "page_number": chunk.get("page_number"),
                "metadata": {
                    "source_title": metadata["title"],
                    "version": metadata["version"],
                    "year": metadata["year"],
                    "uploaded_by": metadata["uploaded_by"],
                    "chunk_index": i,
                    "total_chunks": len(raw_chunks),
                    "page_number": chunk.get("page_number")
                }
            })

        logger.info(f"Processed {file_path}: {len(chunks)} chunks, {total_pages} pages")
        return chunks, md5_hash, total_pages

def process_and_index(file_path: str, uploaded_by: int, title: str, version: str, year: str, db):
    """Функция для переиндексации КР (используется в фоновых задачах)"""
    from .indexing import indexing_service
    from .models import ClinicalGuideline, ChunkMetadata

    chunks, md5_hash, total_pages = ingestion_pipeline.process_pdf(
        file_path,
        {"title": title, "version": version, "year": year, "uploaded_by": uploaded_by}
    )

    guideline = db.query(ClinicalGuideline).filter(ClinicalGuideline.md5_hash == md5_hash).first()
    if not guideline:
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

    indexing_service.delete_chunks_by_guideline(guideline.id)
    db.query(ChunkMetadata).filter(ChunkMetadata.guideline_id == guideline.id).delete()
    indexing_service.index_chunks(chunks, guideline.id)

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

    guideline.total_pages = total_pages
    guideline.total_chunks = len(chunks)
    db.commit()

    return guideline.id, len(chunks), total_pages
ingestion_pipeline = PDFIngestionPipeline()