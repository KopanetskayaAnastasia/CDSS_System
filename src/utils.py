"""
Вспомогательные функции
"""

import json
import re
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional, Any, List, Dict

from .models import AuditLog


def log_audit(
        db: Session,
        doctor_id: int,
        action_type: str,
        action_details: Optional[dict] = None,
        patient_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        is_abnormal: bool = False,
        abnormal_reason: Optional[str] = None
) -> AuditLog:
    """
    Логирование действия пользователя в AuditLog
    """
    details_json = None
    if action_details:
        try:
            details_json = json.dumps(action_details, ensure_ascii=False, default=str)
        except Exception:
            details_json = json.dumps({"error": "Failed to serialize details"})

    log_entry = AuditLog(
        doctor_id=doctor_id,
        role_id=1,  # 1 = Doctor (по умолчанию)
        patient_id=patient_id,
        action_type=action_type,
        action_details=details_json,
        ip_address=ip_address,
        user_agent=user_agent,
        is_abnormal=is_abnormal,
        abnormal_reason=abnormal_reason
    )
    db.add(log_entry)
    db.flush()
    return log_entry


def format_citations_as_markdown(citations: List[Dict]) -> str:
    """
    Форматирование цитат для отображения в интерфейсе
    """
    if not citations:
        return ""

    result = "\n\n**📚 Источники:**\n"
    for c in citations:
        result += f"\n[{c.get('citation_order', '?')}] **{c.get('source_title', 'Неизвестный источник')}**"
        if c.get('section'):
            result += f", раздел «{c.get('section')}»"
        if c.get('page_number'):
            result += f", стр. {c.get('page_number')}"
        if c.get('cosine_similarity'):
            result += f" (сходство: {c.get('cosine_similarity')*100:.1f}%)"
    return result


def chunk_text_preview(text: str, max_length: int = 200) -> str:
    """
    Обрезка текста для предпросмотра
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def validate_login(login: str) -> bool:
    """
    Проверка валидности логина (только буквы, цифры, подчёркивание)
    """
    return bool(re.match(r'^[a-zA-Z0-9_]{3,50}$', login))


def validate_password_strength(password: str) -> bool:
    """
    Проверка сложности пароля (минимум 6 символов)
    """
    return len(password) >= 6


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Форматирование даты и времени
    """
    if dt is None:
        return ""
    return dt.strftime(fmt)


def generate_audit_summary(logs: List[AuditLog]) -> Dict[str, int]:
    """
    Генерация сводки по аудит-логам
    """
    summary = {}
    for log in logs:
        action = log.action_type
        summary[action] = summary.get(action, 0) + 1
    return summary