from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Literal
import re

class LoginPayload(BaseModel):
    username: str
    password: str

class RegisterPayload(BaseModel):
    username: str
    
    @field_validator("username")
    @classmethod
    def username_sem_espaco(cls, v):
        if not re.match(r"^[a-zA-Z0-9_.-]+$", v):
            raise ValueError("username não pode conter espaços ou caracteres especiais")
        return v.lower()
    password: str
    email: EmailStr
    phone: str
    name: str
    user_key: str
    state: str
    
    # Tornamos os IDs e observações opcionais com valores padrão
    # para evitar o erro 422 se o frontend omitir o campo no payload
    base_id: Optional[str] = "0"
    region_id: Optional[int] = 0
    state_id: Optional[int] = 0
    role_id: Optional[int] = 0
    role_type_id: Optional[int] = 0
    department_id: Optional[int] = 0
    regime_id: Optional[int] = 0
    observations: Optional[str] = ""


class UpdateMePayload(BaseModel):
    # Contato
    phone:         Optional[str]                          = None
    email:         Optional[EmailStr]                     = None
    # Identificação
    name:          Optional[str]                          = None  # Nome completo
    user_key:      Optional[str]                          = None  # Chave funcional ex: CM0E
    # Status de permuta
    state:         Optional[Literal["permuta","liberado"]] = None
    # Localização
    base_id:       Optional[str]                          = None
    region_id:     Optional[int]                          = None
    state_id:      Optional[int]                          = None
    # Perfil profissional
    role_id:       Optional[int]                          = None
    role_type_id:  Optional[int]                          = None
    department_id: Optional[int]                          = None
    regime_id:     Optional[int]                          = None
    observations:  Optional[str]                          = None


class InterestPayload(BaseModel):
    target_base_id:       str = "0"
    target_region_id:     int = 0
    target_state_id:      int = 0
    target_role_id:       int = 0
    target_role_type_id:  int = 0
    target_department_id: int = 0
    target_regime_id:     int = 0
    observations:         str = ""


class ForgotPasswordPayload(BaseModel):
    username: str

class ResetPasswordPayload(BaseModel):
    token: str
    new_password: str

class AddMetadataPayload(BaseModel):
    category: str
    value: str

class StatePayload(BaseModel):
    name: str
    lat: float
    lng: float

class RegionPayload(BaseModel):
    name: str
    state_id: str
    lat: float
    lng: float

class LocationPayload(BaseModel):
    name: str
    region_id: str
    state_id: str
    type: str           # "Onshore" | "Offshore"
    lat: float
    lng: float

class RoleTypePayload(BaseModel):
    name: str
 
class RolePayload(BaseModel):
    name: str
    role_type_id: str

class DepartmentPayload(BaseModel):
    name: str

class UserAdminPayload(BaseModel):
    is_admin: bool