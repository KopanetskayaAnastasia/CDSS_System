import re
import logging
import requests
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class GigaChatClient:
    def __init__(self):
        from .config import config
        self.authorization_key = config.GIGACHAT_CREDENTIALS
        self.scope = config.GIGACHAT_SCOPE
        self.auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self.api_url = "https://gigachat.devices.sberbank.ru/api/v1"
        self.rquid = "027bb905-645e-4909-8e4c-abe601a83f99"
        self._access_token = None
        self._token_expires_at = 0

    def _get_access_token(self):
        if self._access_token and datetime.now().timestamp() < self._token_expires_at:
            return self._access_token
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'RqUID': self.rquid,
            'Authorization': f'Basic {self.authorization_key}'
        }
        data = {'scope': self.scope}
        try:
            response = requests.post(self.auth_url, headers=headers, data=data, verify=False, timeout=30)
            if response.status_code != 200:
                logger.error(f"Token error: {response.status_code}")
                return None
            token_data = response.json()
            self._access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 1200)
            self._token_expires_at = datetime.now().timestamp() + expires_in - 60
            return self._access_token
        except Exception as e:
            logger.error(f"Failed to get token: {e}")
            return None

    def chat_completion(self, messages: List[Dict[str, str]]) -> str:
        token = self._get_access_token()
        if not token:
            raise Exception("No access token available")
        url = f"{self.api_url}/chat/completions"
        payload = {"model": "GigaChat", "messages": messages, "temperature": 0.3, "max_tokens": 2000}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=60)
            if response.status_code != 200:
                raise Exception(f"API error: {response.status_code}")
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"GigaChat API error: {e}")
            raise


class Generator:
    def __init__(self):
        self.client = GigaChatClient()
        self.system_prompt = "Ты — ассистент врача. Отвечай ТОЛЬКО на русском языке на основе контекста. Будь краток."

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace('', '-').replace('•', '-')
        text = re.sub(r' +', ' ', text)
        return text.strip()

    def generate_answer(self, query, context_chunks, history, facts, search_confidence=0.0):
        if not context_chunks:
            return {"answer": "Не найдено релевантных фрагментов.", "citations": [], "confidence": 0.0}

        try:
            messages = [{"role": "system", "content": self.system_prompt}]

            context_text = ""
            for i, chunk in enumerate(context_chunks, 1):
                text = self._clean_text(chunk.get("text", "")[:500])
                context_text += f"[{i}] {text}\n\n"

            if context_text:
                messages.append({"role": "user", "content": f"Вот контекст:\n\n{context_text}"})

            messages.append({"role": "user", "content": query})

            raw_answer = self.client.chat_completion(messages)
            raw_answer = self._clean_text(raw_answer)

            citations = []
            for i, chunk in enumerate(context_chunks[:5], 1):
                metadata = chunk.get("metadata", {})
                citations.append({
                    "citation_order": i,
                    "source_title": metadata.get("source_title", "Источник"),
                    "source_year": metadata.get("year"),
                    "page_number": metadata.get("page_number", 0),
                    "guideline_id": metadata.get("guideline_id"),
                    "cited_text": self._clean_text(chunk.get("text", "")[:200]),
                    "cosine_similarity": chunk.get("score", 0.5)
                })

            return {
                "answer": raw_answer,
                "citations": citations,
                "confidence": round(search_confidence, 2) if search_confidence else 0.7
            }
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            answer = "**На основе клинических рекомендаций:**\n\n"
            citations = []
            for i, chunk in enumerate(context_chunks[:5], 1):
                text = self._clean_text(chunk.get("text", "")[:300])
                answer += f"{i}. {text}...\n\n"
                metadata = chunk.get("metadata", {})
                citations.append({
                    "citation_order": i,
                    "source_title": metadata.get("source_title", "Источник"),
                    "source_year": metadata.get("year"),
                    "page_number": metadata.get("page_number", 0),
                    "guideline_id": metadata.get("guideline_id"),
                    "cited_text": self._clean_text(chunk.get("text", "")[:200]),
                    "cosine_similarity": chunk.get("score", 0.5)
                })
            return {"answer": answer, "citations": citations, "confidence": 0.5}