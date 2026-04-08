from pydantic import BaseModel, EmailStr
from typing import Optional, Literal


class LoginPayload(BaseModel):
    username: str
    password: str


class RegisterPayload(BaseModel):
    username: str
    password: str
    email: EmailStr
    phone: str
    name: str
    user_key: str
    state: str
    base_id: str
    region_id: int
    state_id: int
    role_id: int
    role_type_id: int
    department_id: int
    regime_id: int
    observations: str





class UpdateMePayload(BaseModel):
    # Contato
    phone:         Optional[str]                          = None
    email:         Optional[EmailStr]                     = None
    # Identificação
    name:          Optional[str]                          = None  # Nome completo
    user_key:           Optional[str]                          = None  # Chave funcional ex: CM0E
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
    observations:   Optional[str]                          = None


class InterestPayload(BaseModel):
    target_base_id:       str = "0"
    target_region_id:     int = 0
    target_state_id:      int = 0
    target_role_id:       int = 0
    target_role_type_id:  int = 0
    target_department_id: int = 0
    target_regime_id:     int = 0
    observations:          str = ""


class ForgotPasswordPayload(BaseModel):
    username: str

class ResetPasswordPayload(BaseModel):
    token: str
    new_password: str

class AddMetadataPayload(BaseModel):
    category: str
    value: str