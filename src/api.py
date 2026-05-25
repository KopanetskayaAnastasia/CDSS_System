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
from fastapi.responses import Response

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
    return [
        {
            "id": g.id,
            "title": g.title,
            "version": g.version,
            "year": g.year,
            "is_active": g.is_active,
            "total_chunks": g.total_chunks or 0,
            "total_pages": g.total_pages or 0
        }
        for g in guidelines
    ]

@router.get("/admin/status")
def admin_status(db: Session = Depends(get_db), current_doctor=Depends(auth_handler.get_current_user)):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")
    active = db.query(ClinicalGuideline).filter(ClinicalGuideline.is_active == True).count()
    total = db.query(ClinicalGuideline).count()
    return {"active_guidelines": active, "total_guidelines": total}


@router.get("/dialogues/{dialogue_id}/export")
def export_dialogue(
    dialogue_id: int,
    db: Session = Depends(get_db),
    current_doctor = Depends(auth_handler.get_current_user)
):
    from .export_pdf import export_dialogue_to_pdf
    try:
        pdf_bytes = export_dialogue_to_pdf(db, dialogue_id)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=dialogue_{dialogue_id}.pdf"}
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/admin/dialogues")
def get_admin_dialogues(
        limit: int = 50,
        offset: int = 0,
        doctor_id: Optional[int] = None,
        patient_id: Optional[int] = None,
        db: Session = Depends(get_db),
        current_doctor=Depends(auth_handler.get_current_user)
):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = db.query(Dialogue)

    if doctor_id:
        query = query.filter(Dialogue.doctor_id == doctor_id)
    if patient_id:
        query = query.filter(Dialogue.patient_id == patient_id)

    total = query.count()
    dialogues = query.order_by(Dialogue.id.desc()).offset(offset).limit(limit).all()

    result = []
    for d in dialogues:
        doctor = db.query(Doctor).filter(Doctor.id == d.doctor_id).first()
        patient = db.query(Patient).filter(Patient.id == d.patient_id).first() if d.patient_id else None
        messages_count = db.query(Message).filter(Message.dialogue_id == d.id).count()

        result.append({
            "id": d.id,
            "session_uuid": str(d.session_uuid),
            "doctor_name": doctor.full_name if doctor else None,
            "patient_name": patient.full_name if patient else None,
            "started_at": d.started_at.isoformat() if d.started_at else None,
            "ended_at": d.ended_at.isoformat() if d.ended_at else None,
            "status": d.status,
            "message_count": messages_count
        })

    return {"total": total, "dialogues": result}


@router.get("/admin/doctors")
def get_admin_doctors(db: Session = Depends(get_db), current_doctor=Depends(auth_handler.get_current_user)):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")

    doctors = db.query(Doctor).all()
    return [
        {
            "id": d.id,
            "login": d.login,
            "full_name": d.full_name,
            "specialty": d.specialty,
            "is_active": d.is_active,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "last_login": d.last_login.isoformat() if d.last_login else None
        }
        for d in doctors
    ]


from fastapi import UploadFile, File, Form


@router.post("/admin/upload")
async def upload_guideline(
        file: UploadFile = File(...),
        title: str = Form(...),
        version: str = Form(...),
        year: int = Form(...),
        db: Session = Depends(get_db),
        current_doctor=Depends(auth_handler.get_current_user)
):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")

    content = await file.read()
    from .admin import admin_service
    result = admin_service.upload_guideline(
        db, content, file.filename, title, version, year, current_doctor.id
    )
    if result["success"]:
        return {"message": "OK", "guideline_id": result["guideline_id"]}
    else:
        raise HTTPException(status_code=400, detail=result["error"])


@router.post("/admin/reindex-all")
def reindex_all_guidelines(
        db: Session = Depends(get_db),
        current_doctor=Depends(auth_handler.get_current_user)
):
    """Переиндексация всех клинических рекомендаций"""
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")

    from .admin import admin_service
    from .models import ClinicalGuideline

    guidelines = db.query(ClinicalGuideline).filter(ClinicalGuideline.is_active == True).all()

    results = []
    for guideline in guidelines:
        try:
            success = admin_service.reindex_guideline(db, guideline.id)
            results.append({
                "guideline_id": guideline.id,
                "title": guideline.title,
                "success": success
            })
        except Exception as e:
            results.append({
                "guideline_id": guideline.id,
                "title": guideline.title,
                "success": False,
                "error": str(e)
            })

    return {"success": True, "results": results}


@router.get("/admin/audit-logs")
def get_audit_logs(
        limit: int = 50,
        offset: int = 0,
        action_type: Optional[str] = None,
        from_date: Optional[str] = None,
        db: Session = Depends(get_db),
        current_doctor=Depends(auth_handler.get_current_user)
):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = db.query(AuditLog)

    if action_type:
        query = query.filter(AuditLog.action_type == action_type)
    if from_date:
        query = query.filter(AuditLog.timestamp >= from_date)

    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()

    result = []
    for log in logs:
        doctor = db.query(Doctor).filter(Doctor.id == log.doctor_id).first()
        result.append({
            "id": log.id,
            "action_type": log.action_type,
            "action_details": log.action_details,
            "doctor_login": doctor.login if doctor else None,
            "patient_id": log.patient_id,
            "ip_address": str(log.ip_address) if log.ip_address else None,
            "user_agent": log.user_agent,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "is_abnormal": log.is_abnormal,
            "abnormal_reason": log.abnormal_reason
        })

    return {"total": total, "logs": result}


@router.get("/admin/stats")
def get_admin_stats(db: Session = Depends(get_db), current_doctor=Depends(auth_handler.get_current_user)):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")

    from sqlalchemy import func

    doctors_total = db.query(Doctor).count()
    doctors_active = db.query(Doctor).filter(Doctor.is_active == True).count()
    patients_total = db.query(Patient).count()
    dialogues_total = db.query(Dialogue).count()
    messages_total = db.query(Message).count()
    queries_total = db.query(Message).filter(Message.sender == "user").count()
    assistant_total = db.query(Message).filter(Message.sender == "assistant").count()
    avg_confidence = db.query(func.avg(Message.confidence)).filter(Message.confidence.isnot(None)).scalar() or 0
    guidelines_total = db.query(ClinicalGuideline).count()
    guidelines_active = db.query(ClinicalGuideline).filter(ClinicalGuideline.is_active == True).count()
    chunks_total = db.query(ChunkMetadata).count()

    return {
        "doctors": {"total": doctors_total, "active": doctors_active},
        "patients": patients_total,
        "dialogues": dialogues_total,
        "messages": {
            "total": messages_total,
            "queries": queries_total,
            "assistant_responses": assistant_total
        },
        "avg_confidence": float(avg_confidence),
        "guidelines": {"total": guidelines_total, "active": guidelines_active},
        "chunks": chunks_total
    }


@router.get("/admin/roles")
def get_admin_roles(db: Session = Depends(get_db), current_doctor=Depends(auth_handler.get_current_user)):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")

    roles = db.query(Role).all()
    result = []
    for role in roles:
        doctors_count = db.query(Doctor).filter(Doctor.role_id == role.id).count()
        result.append({
            "id": role.id,
            "role_name": role.role_name,
            "description": role.description,
            "doctors_count": doctors_count
        })

    return result


@router.post("/admin/reindex/{guideline_id}")
def reindex_guideline(
        guideline_id: int,
        db: Session = Depends(get_db),
        current_doctor=Depends(auth_handler.get_current_user)
):
    if current_doctor.role_id != 2:
        raise HTTPException(status_code=403, detail="Admin access required")

    from .admin import admin_service
    success = admin_service.reindex_guideline(db, guideline_id)

    if success:
        return {"success": True}
    else:
        raise HTTPException(status_code=400, detail="Reindex failed")