"""
FastAPI роутер – все эндпоинты системы
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import uuid
import os
from sqlalchemy import func

from .database import get_db
from .models import Doctor, Dialogue, Message, Citation, Patient, ClinicalGuideline, ChunkMetadata, Role, AuditLog
from .retriever import retriever
from .generator import Generator
from .memory import memory_manager
from .auth import auth_handler
from .utils import log_audit
from .ingestion import ingestion_pipeline, process_and_index

router = APIRouter()
generator = Generator()


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    patient_id: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]]
    confidence: float
    session_id: str
    processing_time_ms: int


class LoginRequest(BaseModel):
    login: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str


class PatientCreate(BaseModel):
    full_name: str
    date_of_birth: Optional[date] = None
    snils: Optional[str] = None
    policy_number: Optional[str] = None
    medical_record_number: Optional[str] = None
    gender: Optional[str] = None


class PatientResponse(BaseModel):
    id: int
    full_name: str
    date_of_birth: Optional[date] = None
    snils: Optional[str] = None
    policy_number: Optional[str] = None


class DoctorCreate(BaseModel):
    login: str
    password: str
    full_name: str
    specialty: Optional[str] = None


class DoctorResponse(BaseModel):
    id: int
    login: str
    full_name: str
    specialty: Optional[str]
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    doctor = auth_handler.authenticate(db, req.login, req.password)
    if not doctor:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = auth_handler.create_token(doctor.id, doctor.login, doctor.role_id)
    log_audit(db, doctor.id, "login", {"login": req.login})
    doctor.last_login = datetime.now()
    db.commit()
    return {"access_token": token, "token_type": "bearer"}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db), current_doctor=Depends(auth_handler.get_current_user)):
    start_time = datetime.now()

    new_uuid = str(uuid.uuid4())
    dialogue = Dialogue(
        session_uuid=new_uuid,
        doctor_id=current_doctor.id,
        patient_id=req.patient_id,
        role_id=current_doctor.role_id,
        started_at=datetime.now(),
        status="active"
    )
    db.add(dialogue)
    db.flush()
    session_id = new_uuid

    user_message = Message(
        dialogue_id=dialogue.id,
        doctor_id=current_doctor.id,
        patient_id=req.patient_id,
        role_id=current_doctor.role_id,
        sender="user",
        message_text=req.query,
        timestamp=datetime.now()
    )
    db.add(user_message)
    db.flush()

    context = retriever.hybrid_search(req.query)

    history = db.query(Message).filter(
        Message.dialogue_id == dialogue.id,
        Message.sender.in_(['user', 'assistant'])
    ).order_by(Message.timestamp).limit(10).all()

    history_list = [
        {"sender": "user" if m.sender == "user" else "assistant", "text": m.message_text}
        for m in history[:-1]
    ]

    facts = memory_manager.get_patient_facts(db, req.patient_id) if req.patient_id else []

    search_confidence = sum(chunk.get("score", 0.5) for chunk in context) / len(context) if context else 0.0
    if search_confidence > 1:
        search_confidence = min(search_confidence / 15.0, 1.0)

    result = generator.generate_answer(req.query, context, history_list, facts, search_confidence)

    processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

    assistant_message = Message(
        dialogue_id=dialogue.id,
        doctor_id=current_doctor.id,
        patient_id=req.patient_id,
        role_id=current_doctor.role_id,
        sender="assistant",
        message_text=result["answer"],
        confidence=result.get("confidence", 0.0),
        raw_context={"chunks": context},
        tokens_in=len(req.query.split()),
        processing_time_ms=processing_time,
        timestamp=datetime.now()
    )
    db.add(assistant_message)
    db.flush()

    for citation in result.get("citations", []):
        cos_sim = citation.get("cosine_similarity", 0.5)
        if cos_sim > 1:
            cos_sim = max(0.0, min(1.0, cos_sim / 15.0))

        source_year = citation.get("source_year")
        if source_year == "" or source_year is None:
            source_year = None

        cit = Citation(
            message_id=assistant_message.id,
            dialogue_id=dialogue.id,
            doctor_id=current_doctor.id,
            patient_id=req.patient_id,
            role_id=current_doctor.role_id,
            chunk_id=citation.get("chunk_id"),
            source_title=citation.get("source_title"),
            source_year=source_year,
            section=citation.get("section"),
            page_number=citation.get("page_number"),
            cited_text=citation.get("cited_text"),
            citation_order=citation.get("citation_order"),
            cosine_similarity=cos_sim,
            guideline_id=citation.get("guideline_id")
        )
        db.add(cit)

    log_audit(db, current_doctor.id, "query", {"query": req.query, "confidence": result.get("confidence", 0.0)})

    db.commit()

    return ChatResponse(
        answer=result["answer"],
        citations=result.get("citations", []),
        confidence=result.get("confidence", 0.0),
        session_id=str(session_id),
        processing_time_ms=processing_time
    )


# ========== ПАЦИЕНТЫ ==========
@router.get("/patients", response_model=List[PatientResponse])
def get_patients(db: Session = Depends(get_db), current_doctor=Depends(auth_handler.get_current_user)):
    patients = db.query(Patient).order_by(Patient.id).all()
    return [
        {
            "id": p.id,
            "full_name": p.full_name,
            "date_of_birth": p.date_of_birth,
            "snils": p.snils,
            "policy_number": p.policy_number
        }
        for p in patients
    ]


@router.post("/patients", response_model=PatientResponse)
def add_patient(
    patient_data: PatientCreate,
    db: Session = Depends(get_db),
    current_doctor=Depends(auth_handler.get_current_user)
):
    if patient_data.snils:
        existing = db.query(Patient).filter(Patient.snils == patient_data.snils).first()
        if existing:
            raise HTTPException(status_code=400, detail="Patient with this SNILS already exists")

    patient = Patient(
        full_name=patient_data.full_name,
        date_of_birth=patient_data.date_of_birth,
        snils=patient_data.snils,
        policy_number=patient_data.policy_number,
        medical_record_number=patient_data.medical_record_number,
        gender=patient_data.gender,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    log_audit(db, current_doctor.id, "add_patient", {"patient_id": patient.id, "full_name": patient.full_name})

    return {
        "id": patient.id,
        "full_name": patient.full_name,
        "date_of_birth": patient.date_of_birth,
        "snils": patient.snils,
        "policy_number": patient.policy_number
    }


@router.delete("/patients/{patient_id}")
def delete_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_doctor=Depends(auth_handler.get_current_user)
):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    db.delete(patient)
    db.commit()

    log_audit(db, current_doctor.id, "delete_patient", {"patient_id": patient_id})
    return {"success": True}


# ========== PDF ЭНДПОИНТ (без авторизации) ==========
@router.get("/guidelines/{guideline_id}/pdf")
def download_guideline_pdf(
    guideline_id: int,
    db: Session = Depends(get_db)
):
    """Скачать PDF клинической рекомендации по ID"""
    guideline = db.query(ClinicalGuideline).filter(ClinicalGuideline.id == guideline_id).first()
    if not guideline:
        raise HTTPException(status_code=404, detail=f"Guideline {guideline_id} not found")

    if not os.path.exists(guideline.file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {guideline.file_path}")

    return FileResponse(
        guideline.file_path,
        media_type="application/pdf",
        filename=f"{guideline.title}.pdf"
    )


# ========== ОСТАЛЬНЫЕ ЭНДПОИНТЫ (ADMIN и т.д.) ==========
@router.get("/admin/guidelines")
def get_guidelines(db: Session = Depends(get_db), current_doctor=Depends(auth_handler.get_current_user)):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")
    guidelines = db.query(ClinicalGuideline).order_by(ClinicalGuideline.id.desc()).all()
    return [{"id": g.id, "title": g.title, "version": g.version, "year": g.year, "is_active": g.is_active} for g in guidelines]


@router.get("/admin/status")
def admin_status(db: Session = Depends(get_db), current_doctor=Depends(auth_handler.get_current_user)):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")
    active = db.query(ClinicalGuideline).filter(ClinicalGuideline.is_active == True).count()
    total = db.query(ClinicalGuideline).count()
    return {"active_guidelines": active, "total_guidelines": total}