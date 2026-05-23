"""
Модуль управления памятью диалога (без Redis, только PostgreSQL)
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from .models import MedicalFact

logger = logging.getLogger(__name__)


class MemoryManager:
    """Управление памятью диалога (только долговременная память)"""

    def __init__(self):
        logger.info("MemoryManager initialized (PostgreSQL only, no Redis)")

    def get_patient_facts(
        self,
        db: Session,
        patient_id: int,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Получение долговременных фактов о пациенте из PostgreSQL"""
        if patient_id is None:
            return []

        query = db.query(MedicalFact).filter(MedicalFact.patient_id == patient_id)

        if active_only:
            query = query.filter(MedicalFact.is_active == True)

        facts = query.order_by(MedicalFact.extracted_at.desc()).limit(20).all()

        return [
            {
                "fact_type": f.fact_type,
                "fact_value": f.fact_value,
                "icd10_code": f.icd10_code,
                "confidence": f.confidence,
                "extracted_at": f.extracted_at.isoformat() if f.extracted_at else None
            }
            for f in facts
        ]

    def save_medical_fact(
        self,
        db: Session,
        patient_id: int,
        fact_type: str,
        fact_value: str,
        icd10_code: Optional[str] = None,
        source_message_id: Optional[int] = None,
        confidence: float = 0.8
    ) -> Optional[MedicalFact]:
        """Сохранение медицинского факта"""
        if patient_id is None:
            return None

        fact = MedicalFact(
            patient_id=patient_id,
            fact_type=fact_type,
            fact_value=fact_value,
            icd10_code=icd10_code,
            source_message_id=source_message_id,
            confidence=confidence,
            is_active=True
        )
        db.add(fact)
        db.flush()
        return fact


memory_manager = MemoryManager()