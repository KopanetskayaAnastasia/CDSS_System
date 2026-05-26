"""
Интеграция с МИС через HL7 FHIR
"""
import requests
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from ..models import Patient

logger = logging.getLogger(__name__)


class FHIRClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get_patient_by_snils(self, snils: str) -> Optional[Dict[str, Any]]:
        clean_snils = snils.replace("-", "").replace(" ", "")
        url = f"{self.base_url}/Patient"
        params = {"identifier": clean_snils}
        headers = self._get_headers()

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('total', 0) > 0:
                    return data['entry'][0]['resource']
            return None
        except Exception as e:
            logger.error(f"FHIR error: {e}")
            return None

    def import_patient_to_db(self, db: Session, snils: str) -> Optional[Patient]:
        existing = db.query(Patient).filter(Patient.snils == snils).first()
        if existing:
            return existing

        fhir_patient = self.get_patient_by_snils(snils)
        if not fhir_patient:
            return None

        name = fhir_patient.get('name', [{}])[0]
        full_name = f"{name.get('family', '')} {name.get('given', [''])[0]}".strip()

        patient = Patient(
            full_name=full_name,
            snils=snils,
            medical_record_number=fhir_patient.get('id')
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
        return patient


def get_fhir_client() -> FHIRClient:
    import os
    base_url = os.getenv("MIS_FHIR_URL", "")
    api_key = os.getenv("MIS_API_KEY", "")
    return FHIRClient(base_url, api_key)