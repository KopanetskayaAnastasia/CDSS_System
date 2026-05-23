"""
SQLAlchemy ORM модели для PostgreSQL
Полностью соответствуют физической модели данных (11 таблиц)
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, Float,
    ForeignKey, CheckConstraint, Index, Date, CHAR, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
import uuid

Base = declarative_base()


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    role_name = Column(String(50), nullable=False, unique=True)
    description = Column(String(255))


class Doctor(Base):
    __tablename__ = "doctors"
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, default=1)
    login = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    specialty = Column(String(150))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime)

    # Индексы
    __table_args__ = (
        Index("idx_doctor_login", "login"),
        Index("idx_doctor_role", "role_id"),
        Index("idx_doctor_active", "is_active"),
    )


class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True)
    full_name = Column(String(255), nullable=False)
    date_of_birth = Column(Date)
    gender = Column(CHAR(1))
    snils = Column(String(14), unique=True)
    policy_number = Column(String(20))
    medical_record_number = Column(String(255), unique=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Индексы и ограничения
    __table_args__ = (
        CheckConstraint("gender IN ('M', 'F', 'O')", name="ck_patient_gender"),
        Index("idx_patient_snils", "snils"),
        Index("idx_patient_mrn", "medical_record_number"),
        Index("idx_patient_full_name", "full_name"),
    )


class Dialogue(Base):
    __tablename__ = "dialogues"
    id = Column(Integer, primary_key=True)
    session_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False, unique=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, default=1)
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="active")

    # Индексы и ограничения
    __table_args__ = (
        CheckConstraint("status IN ('active', 'closed', 'timeout')", name="ck_dialogue_status"),
        Index("idx_dialogue_doctor", "doctor_id"),
        Index("idx_dialogue_patient", "patient_id"),
        Index("idx_dialogue_session", "session_uuid"),
        Index("idx_dialogue_status", "status"),
    )


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    dialogue_id = Column(Integer, ForeignKey("dialogues.id"), nullable=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, default=1)
    sender = Column(String(20), nullable=False)
    message_text = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True)
    raw_context = Column(JSONB, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)  # ← ДОБАВЛЕНО (было в ЛР №3)
    processing_time_ms = Column(Integer, default=0)

    # Индексы и ограничения
    __table_args__ = (
        CheckConstraint("sender IN ('user', 'assistant')", name="ck_message_sender"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_message_confidence"),
        Index("idx_message_dialogue", "dialogue_id"),
        Index("idx_message_timestamp", "timestamp"),
        Index("idx_message_sender", "sender"),
        Index("idx_message_doctor", "doctor_id"),
        Index("idx_message_patient", "patient_id"),
    )


class MedicalFact(Base):
    __tablename__ = "medical_facts"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    fact_type = Column(String(50), nullable=False)
    fact_value = Column(Text, nullable=False)
    icd10_code = Column(String(10))
    source_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    confidence = Column(Float, default=0.5)
    extracted_at = Column(DateTime, server_default=func.now())
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)

    # Индексы и ограничения
    __table_args__ = (
        CheckConstraint(
            "fact_type IN ('diagnosis', 'allergy', 'medication', 'lab_result', 'symptom')",
            name="ck_medical_fact_type"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_medical_fact_confidence"),
        Index("idx_medical_fact_patient", "patient_id"),
        Index("idx_medical_fact_type", "fact_type"),
        Index("idx_medical_fact_active", "is_active"),
    )


class ClinicalGuideline(Base):
    __tablename__ = "clinical_guidelines"
    id = Column(Integer, primary_key=True)
    uploaded_by = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, default=2)
    title = Column(String(500), nullable=False)
    version = Column(String(50), nullable=False)
    year = Column(Integer, nullable=True)
    md5_hash = Column(String(32), unique=True, nullable=False)
    file_path = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    uploaded_at = Column(DateTime, server_default=func.now())
    total_pages = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)

    # Индексы
    __table_args__ = (
        Index("idx_guideline_active", "is_active"),
        Index("idx_guideline_md5", "md5_hash"),
        Index("idx_guideline_title", "title"),
        Index("idx_guideline_uploaded_by", "uploaded_by"),
    )


class ChunkMetadata(Base):
    __tablename__ = "chunk_metadata"
    id = Column(Integer, primary_key=True)
    chunk_id = Column(String(255), unique=True, nullable=False)
    guideline_id = Column(Integer, ForeignKey("clinical_guidelines.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, default=2)
    chunk_text = Column(Text, nullable=False)
    section = Column(String(500), nullable=True)
    page_number = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=True)
    bm25_indexed = Column(Boolean, default=False)

    # Индексы
    __table_args__ = (
        Index("idx_chunk_guideline", "guideline_id"),
        Index("idx_chunk_chunk_id", "chunk_id"),
        Index("idx_chunk_page", "page_number"),
    )


class Citation(Base):
    __tablename__ = "citations"
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    dialogue_id = Column(Integer, ForeignKey("dialogues.id"), nullable=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, default=1)
    chunk_id = Column(String(255), nullable=True)
    source_title = Column(String(500), nullable=True)
    source_year = Column(Integer, nullable=True)
    section = Column(String(500), nullable=True)
    page_number = Column(Integer, nullable=True)
    cited_text = Column(Text, nullable=True)
    citation_order = Column(Integer, nullable=True)
    cosine_similarity = Column(Float, nullable=True)
    guideline_id = Column(Integer, ForeignKey("clinical_guidelines.id"), nullable=True)
    # Индексы и ограничения
    __table_args__ = (
        CheckConstraint(
            "cosine_similarity >= 0 AND cosine_similarity <= 1",
            name="ck_citation_cosine"
        ),
        Index("idx_citation_message", "message_id"),
        Index("idx_citation_chunk", "chunk_id"),
        Index("idx_citation_dialogue", "dialogue_id"),
        Index("idx_citation_doctor", "doctor_id"),
         Index("idx_citation_guideline", "guideline_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, default=1)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    action_type = Column(String(50), nullable=False)
    action_details = Column(JSONB, nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(String(500), nullable=True)
    timestamp = Column(DateTime, server_default=func.now())
    is_abnormal = Column(Boolean, default=False)
    abnormal_reason = Column(String(255), nullable=True)

    # Индексы
    __table_args__ = (
        Index("idx_audit_doctor", "doctor_id"),
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_action", "action_type"),
        Index("idx_audit_abnormal", "is_abnormal"),
        Index("idx_audit_patient", "patient_id"),
    )