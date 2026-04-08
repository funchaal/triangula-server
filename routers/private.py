import asyncio
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from core.config import get_redis
from core.security import get_current_username
from models.schemas import UpdateMePayload, InterestPayload, AddMetadataPayload
from services import redis_service as db
from services.match_service import recalculate_matches_for_user

router = APIRouter()


# ─── PUT /api/users/me ────────────────────────────────────────────────────────

@router.put("/users/me")
async def update_me(
    payload: UpdateMePayload,
    background_tasks: BackgroundTasks,
    username: str = Depends(get_current_username),
    r=Depends(get_redis),
):
    old_user = await db.get_user(r, username)
    if not old_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        return {"user": _safe_user(old_user)}

    new_user = {**old_user, **{k: str(v) for k, v in updates.items()}}
    await db.save_user(r, username, new_user)
    await db.update_user_indexes(r, username, old_user, new_user)

    # Verifica se algum campo de localização ou perfil profissional foi alterado
    campos_gatilho_match = {"state", "regime_id", "base_id", "region_id", "state_id", "role_type_id", "role_id", "department_id"}
    deve_recalcular = any(campo in campos_gatilho_match for campo in updates.keys())

    if deve_recalcular:
        # Executa no fluxo principal (foreground) para garantir que os matches
        # sejam atualizados antes de montar a resposta HTTP.
        await recalculate_matches_for_user(r, username)

    matches = await db.get_user_matches(r, username)

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

    return {"user": _safe_user(new_user), "matches": complete_matches}




# ─── POST /api/interests ─────────────────────────────────────────────────────

@router.post("/interests")
async def create_interest(
    payload: InterestPayload,
    username: str = Depends(get_current_username),
    r=Depends(get_redis),
):
    interest_data = payload.model_dump()
    interest_id   = await db.save_interest(r, username, interest_data)

    # Recálculo inteligente em foreground para retornar estado atualizado
    await recalculate_matches_for_user(r, username)

    interests = await db.get_user_interests(r, username)
    matches    = await db.get_user_matches(r, username)

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
        "interest_id": interest_id, 
        "interests": interests, 
        "matches": complete_matches
    }


# ─── DELETE /api/interests/{interest_id} ────────────────────────────────────

@router.delete("/interests/{interest_id}")
async def delete_interest(
    interest_id: str,
    username: str = Depends(get_current_username),
    r=Depends(get_redis),
):
    deleted_interest = await db.delete_interest(r, username, interest_id)
    if deleted_interest is None:
        raise HTTPException(status_code=403, detail="Interesse não encontrada ou sem permissão")

    # Invalida matches do usuário (podem ter sido criados por esse interesse)
    # await db.invalidate_matches_containing(r, username)

    # Recálculo inteligente em foreground para retornar estado atualizado
    await recalculate_matches_for_user(r, username)

    interests = await db.get_user_interests(r, username)
    matches    = await db.get_user_matches(r, username)

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

    return {"interest_id": interest_id, "interests": interests, "matches": complete_matches}


# ─── POST /api/config/add-metadata (Admin) ────────────────────────────────────

@router.post("/config/add-metadata")
async def add_metadata(
    payload: AddMetadataPayload,
    username: str = Depends(get_current_username),
    r=Depends(get_redis),
):
    allowed = {"roles", "role_types", "departments", "work_regimes", "locations"}
    if payload.category not in allowed:
        raise HTTPException(status_code=400, detail=f"Categoria inválida: {payload.category}")
    new_key = await db.add_metadata_entry(r, payload.category, payload.value)
    return {"category": payload.category, "key": new_key, "value": payload.value}


def _safe_user(user: dict) -> dict:
    return {k: v for k, v in user.items() if k != "password_hash"}