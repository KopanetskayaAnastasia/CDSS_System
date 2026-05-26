"""
Модуль семантического поиска (гибридный: ChromaDB + BM25 + Cross-Encoder)
"""

import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from sklearn.preprocessing import minmax_scale
import numpy as np
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path

from .config import config

logger = logging.getLogger(__name__)


class BM25Index:
    def __init__(self):
        self.documents = []
        self.doc_lengths = []
        self.avg_doc_length = 0
        self.idf = {}
        self.corpus_size = 0

    def _tokenize(self, text: str) -> List[str]:
        return text.lower().split()

    def fit(self, documents: List[str]):
        if not documents:
            return
        self.documents = documents
        self.corpus_size = len(documents)
        self.doc_lengths = [len(self._tokenize(doc)) for doc in documents]
        self.avg_doc_length = sum(self.doc_lengths) / self.corpus_size if self.corpus_size else 0

        term_freq_in_docs = {}
        for doc in documents:
            terms = set(self._tokenize(doc))
            for term in terms:
                term_freq_in_docs[term] = term_freq_in_docs.get(term, 0) + 1

        for term, freq in term_freq_in_docs.items():
            self.idf[term] = np.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1)

    def search(self, query: str, k: int = 10) -> List[Dict[str, Any]]:
        if not self.documents:
            return []

        query_terms = self._tokenize(query)
        scores = []

        for i, doc in enumerate(self.documents):
            doc_terms = self._tokenize(doc)
            score = 0
            doc_len = self.doc_lengths[i]

            for term in query_terms:
                if term not in self.idf:
                    continue
                term_freq = doc_terms.count(term)
                if term_freq == 0:
                    continue

                numerator = term_freq * (self.idf[term] + 1)
                denominator = term_freq + self.idf[term] * (1 - 0.75 + 0.75 * doc_len / self.avg_doc_length)
                score += numerator / denominator

            scores.append(score)

        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in indexed[:k]:
            results.append({
                "text": self.documents[idx],
                "score": score,
                "index": idx
            })

        return results


class HybridMedicalRetriever:
    def __init__(self):
        self.alpha = config.ALPHA
        self.k = config.SEARCH_K
        self.chunk_size = config.CHUNK_SIZE

        logger.info(f"Loading embedding model: {config.EMBEDDING_MODEL}")
        self.embedder = SentenceTransformer(config.EMBEDDING_MODEL)

        logger.info(f"Loading cross-encoder model: {config.CROSS_ENCODER_MODEL}")
        self.cross_encoder = CrossEncoder(config.CROSS_ENCODER_MODEL)

        chroma_path = Path(config.CHROMA_PATH)
        chroma_path.mkdir(parents=True, exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(path=str(chroma_path))

        try:
            self.collection = self.chroma_client.get_collection(config.CHROMA_COLLECTION)
            logger.info(f"Connected to existing collection: {config.CHROMA_COLLECTION}")
        except ValueError:
            self.collection = self.chroma_client.create_collection(
                name=config.CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Created new collection: {config.CHROMA_COLLECTION}")

        self.bm25_index = BM25Index()
        self._bm25_initialized = False
        self._all_texts = []
        self._all_metadatas = []

    def refresh_bm25(self):
        try:
            all_data = self.collection.get(include=["documents", "metadatas"])
            if all_data and all_data["documents"]:
                self._all_texts = all_data["documents"]
                self._all_metadatas = all_data["metadatas"]
                self.bm25_index.fit(self._all_texts)
                self._bm25_initialized = True
                logger.info(f"BM25 refreshed with {len(self._all_texts)} documents")
                print("BM25 refreshed successfully")
                print("FHIR integration: refresh called")
        except Exception as e:
            logger.error(f"BM25 refresh failed: {e}")

    def _embed_query(self, query: str) -> List[float]:
        embedded = self.embedder.encode(f"query: {query}", normalize_embeddings=True)
        return embedded.tolist()

    def _normalize_scores(self, scores: List[float]) -> List[float]:
        if len(scores) <= 1:
            return scores
        if max(scores) == min(scores):
            return [0.5] * len(scores)
        return minmax_scale(scores)

    def hybrid_search(
        self,
        query: str,
        k: Optional[int] = None,
        alpha: Optional[float] = None,
        use_bm25: bool = True
    ) -> List[Dict[str, Any]]:
        k = k or self.k
        alpha = alpha or self.alpha

        if not query or not query.strip():
            return []

        if self.collection.count() == 0:
            logger.warning("ChromaDB collection is empty")
            return []

        logger.info(f"Processing query: {query[:100]}...")

        query_embedding = self._embed_query(query)

        try:
            chroma_results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=10,
                include=["documents", "metadatas", "distances"]
            )

            if not chroma_results or not chroma_results['documents'] or not chroma_results['documents'][0]:
                return []

            chroma_scores = [1 - d for d in chroma_results['distances'][0]]
            chroma_texts = chroma_results['documents'][0]
            chroma_metadatas = chroma_results['metadatas'][0]

        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            return []

        bm25_scores = []
        if use_bm25 and self._bm25_initialized:
            try:
                bm25_results = self.bm25_index.search(query, k=10)
                bm25_score_dict = {r.get("index", i): r["score"] for i, r in enumerate(bm25_results)}
                bm25_scores = [bm25_score_dict.get(i, 0.0) for i in range(len(chroma_texts))]
            except Exception as e:
                logger.warning(f"BM25 search failed: {e}")
                bm25_scores = [0.5] * len(chroma_texts)
        else:
            bm25_scores = [0.5] * len(chroma_texts)

        chroma_norm = self._normalize_scores(chroma_scores)
        bm25_norm = self._normalize_scores(bm25_scores) if bm25_scores else [0.5] * len(chroma_scores)

        hybrid_scores = alpha * np.array(chroma_norm) + (1 - alpha) * np.array(bm25_norm)
        candidates = list(zip(chroma_texts, chroma_metadatas, hybrid_scores))

        try:
            pairs = [(query, text) for text, _, _ in candidates]
            cross_scores = self.cross_encoder.predict(pairs)
            for i, cross_score in enumerate(cross_scores):
                candidates[i] = (candidates[i][0], candidates[i][1], float(cross_score))
        except Exception as e:
            logger.warning(f"Cross-encoder reranking failed: {e}")

        candidates.sort(key=lambda x: x[2], reverse=True)
        top_k = candidates[:k]

        result = []
        for i, (text, metadata, score) in enumerate(top_k):
            chunk_id = metadata.get("chunk_id") or metadata.get("id") or f"chunk_{hash(text)}_{i}"
            result.append({
                "text": text,
                "score": score,
                "chunk_id": chunk_id,
                "metadata": {
                    "source": metadata.get("source_title", metadata.get("source", "Unknown")),
                    "year": metadata.get("year", 0),
                    "section": metadata.get("section", ""),
                    "page": metadata.get("page_number", 0),
                    "guideline_id": metadata.get("guideline_id", 0)
                }
            })

        if result:
            logger.info(f"Found {len(result)} relevant chunks, top score: {result[0]['score']:.3f}")

        return result


retriever = HybridMedicalRetriever()