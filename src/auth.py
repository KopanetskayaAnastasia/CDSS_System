"""
JWT аутентификация для FastAPI
"""

import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .config import config
from .database import get_db
from .models import Doctor

security = HTTPBearer()


class AuthHandler:
    """Обработчик JWT аутентификации"""

    @staticmethod
    def hash_password(password: str) -> str:
        """Хэширование пароля bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Проверка пароля"""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

    @staticmethod
    def create_token(doctor_id: int, login: str, role_id: int) -> str:
        """Создание JWT токена"""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(doctor_id),
            "login": login,
            "role_id": role_id,
            "exp": now + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
            "iat": now
        }
        return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """Декодирование JWT токена"""
        try:
            payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

    @staticmethod
    def authenticate(db: Session, login: str, password: str) -> Optional[Doctor]:
        """Аутентификация пользователя"""
        doctor = db.query(Doctor).filter(Doctor.login == login, Doctor.is_active == True).first()
        if not doctor:
            return None
        if not AuthHandler.verify_password(password, doctor.password_hash):
            return None
        return doctor

    async def get_current_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
    ) -> Doctor:
        """Получение текущего пользователя из токена"""
        token = credentials.credentials
        payload = self.decode_token(token)
        doctor_id_str = payload.get("sub")

        if not doctor_id_str:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        try:
            doctor_id = int(doctor_id_str)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        doctor = db.query(Doctor).filter(Doctor.id == doctor_id, Doctor.is_active == True).first()
        if not doctor:
            raise HTTPException(status_code=401, detail="User not found")

        return doctor

    async def get_current_admin(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
    ) -> Doctor:
        """Получение текущего администратора (role_id=2)"""
        doctor = await self.get_current_user(credentials, db)
        if doctor.role_id != 2:
            raise HTTPException(status_code=403, detail="Admin access required")
        return doctor


auth_handler = AuthHandler()