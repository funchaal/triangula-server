import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Query
from core.config import get_redis
from core.security import hash_password, verify_password, create_token, get_current_username
# Adicionando os novos payloads de recuperação de senha:
from models.schemas import LoginPayload, RegisterPayload, ForgotPasswordPayload, ResetPasswordPayload
from services import redis_service as db
# Importando o serviço de notificação para o disparo de e-mail:
from services import notification_service
from core.config import get_settings

settings = get_settings()

router = APIRouter(prefix="/auth")


@router.post("/login")
async def login(payload: LoginPayload, r=Depends(get_redis)):
    """
    Bootstrap do usuário autenticado.
    Retorna token + perfil + interesses + matches em uma única resposta.
    """
    user = await db.get_user_by_username(r, payload.username)

    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )

    token = create_token(payload.username)
    interests, matches = await _fetch_user_data(r, payload.username)

    complete_matches = []

    for match in matches:
        chain = match.get("chain", [])
        if not chain:
            continue
        obj = { **match, "chain": [] }
        for u in chain:
            user_info = await db.get_user(r, u["username"])
            obj["chain"].append({ **u, **user_info })
        complete_matches.append(obj)

    return {
        "token": token,
        "user": _safe_user(user),
        "interests": interests,
        "matches": complete_matches,
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterPayload, r=Depends(get_redis)):
    """Cria novo usuário e retorna o mesmo bootstrap do login."""
    if await db.username_exists(r, payload.username):
        raise HTTPException(status_code=409, detail="Username já cadastrado")

    user_data = {
        "username": payload.username,
        "name":     payload.name,
        "user_key": str(payload.user_key).upper(),
        "email":    payload.email,
        "phone":    payload.phone,
        "password_hash": hash_password(payload.password),
        "state":  payload.state, 
        "regime_id":  payload.regime_id, 
        "base_id":    payload.base_id, 
        "region_id":  payload.region_id, 
        "state_id":   payload.state_id, 
        "role_id":    payload.role_id, 
        "role_type_id":   payload.role_type_id, 
        "department_id":  payload.department_id, 
    }

    await db.save_user(r, payload.username, user_data)

    token = create_token(payload.username)
    return {
        "token": token,
        "user": _safe_user(user_data),
        "interests": [],
        "matches": [],
    }


@router.post("/session")
async def restore_session(
    username: str = Depends(get_current_username),
    r=Depends(get_redis),
):
    """
    Restaura a sessão a partir do Bearer Token.
    Chamado pelo frontend no boot quando há token salvo no localStorage.
    """
    user = await db.get_user(r, username)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    interests, matches = await _fetch_user_data(r, username)

    complete_matches = []

    for match in matches:
        chain = match.get("chain", [])
        if not chain:
            continue
        obj = { **match, "chain": [] }
        for u in chain:
            user_info = await db.get_user(r, u["username"])
            # Ajuste fino: no seu original estava {**user, **user_info}, o que sobrescrevia 
            # as chaves com os dados do dono da sessão em vez do nó do ciclo. Corrigido para {**u, **user_info}.
            obj["chain"].append({ **u, **user_info })
        complete_matches.append(obj)

    return {
        "user": _safe_user(user),
        "interests": interests,
        "matches": complete_matches,
    }


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordPayload, r=Depends(get_redis)):
    """
    Gera um token de recuperação e envia por e-mail.
    """
    user = await db.get_user_by_username(r, payload.username)
    
    # Prática de segurança: não revelar se o usuário existe ou não para evitar user enumeration
    if not user:
        return {"message": "Se o usuário existir, um e-mail de recuperação foi enviado."}
    
    token = await db.save_password_reset_token(r, payload.username)
    
    # Dica: Substitua isso por uma variável de ambiente no seu config, ex: settings.frontend_url
    frontend_url = "http://localhost:5173" 
    
    await notification_service.notify_password_reset(
        email=user.get("email"), 
        username=payload.username, 
        token=token, 
        frontend_url=frontend_url, 
        smtp_host=settings.smtp_host, 
        smtp_port=settings.smtp_port, 
        smtp_user=settings.smtp_user_matches, 
        smtp_pass=settings.smtp_pass_matches
    )
    
    return {"message": "Se o usuário existir, um e-mail de recuperação foi enviado."}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordPayload, r=Depends(get_redis)):
    """
    Recebe o token de recuperação, valida e aplica a nova senha.
    """
    username = await db.get_username_by_reset_token(r, payload.token)
    
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Token inválido ou expirado."
        )
    
    # Gera o hash da nova senha usando a mesma função do registro
    new_hashed_password = hash_password(payload.new_password)
    
    # Atualiza no Redis e invalida o token
    await db.update_user_password(r, username, new_hashed_password)
    await db.delete_reset_token(r, payload.token)
    
    return {"message": "Senha atualizada com sucesso."}


# --- Funções Auxiliares ---

async def _fetch_user_data(r, username: str):
    return await asyncio.gather(
        db.get_user_interests(r, username),
        db.get_user_matches(r, username),
    )


def _safe_user(user: dict) -> dict:
    return {k: v for k, v in user.items() if k != "password_hash"}

@router.get("/check-username")
async def check_username(
    username: str = Query(..., min_length=1),
    r=Depends(get_redis),
):
    """
    Verifica se um username já está cadastrado.
    Endpoint público — usado pelo frontend durante o registro.
    """
    exists = await db.username_exists(r, username)
    return {"available": not exists}
 