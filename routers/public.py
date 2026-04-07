import asyncio
from fastapi import APIRouter, Depends, Query
from core.config import get_redis
from services import redis_service as db

router = APIRouter()


@router.get("/init")
async def init(r=Depends(get_redis)):
    """Bootstrap público — metadados + arcos do mapa."""
    metadata, map_intentions = await asyncio.gather(
        db.get_all_metadata(r),
        db.get_map_intentions(r),
    )
    return {"metadata": metadata, "map_intentions": map_intentions}


@router.get("/map/arc")
async def get_arc_users(
    from_key: str = Query(...),
    to_key:   str = Query(...),
    r=Depends(get_redis),
):
    """
    Retorna os usuários que têm intenção no arco from_key→to_key.
    Inclui perfil público (sem phone/email — só liberado após match confirmado).
    """
    all_keys = await r.keys("intention:*")
    if not all_keys:
        return {"users": []}

    pipe = r.pipeline()
    for k in all_keys:
        pipe.hgetall(k)
    intentions = await pipe.execute()

    # Filtra intenções compatíveis com o arco
    matching_usernames = set()
    for intent in intentions:
        if not intent:
            continue
        # from_key é sempre base:XXX
        user_base = None
        username  = intent.get("username")
        if not username:
            continue
        user = await r.hgetall(f"user:{username}")
        if not user:
            continue
        user_base = f"base:{user.get('base_id', '0')}"
        if user_base != from_key:
            continue

        # Verifica se o destino da intenção bate com to_key
        target_base   = intent.get("target_base_id",   "0")
        target_region = intent.get("target_region_id", "0")
        target_state  = intent.get("target_state_id",  "0")

        to_type, to_id = to_key.split(":", 1)
        matched = False
        if to_type == "base"   and target_base   == to_id:   matched = True
        if to_type == "region" and target_region == to_id:   matched = True
        if to_type == "state"  and target_state  == to_id:   matched = True

        if matched:
            matching_usernames.add(username)

    # Busca perfis dos usuários
    users_out = []
    for uname in matching_usernames:
        u = await r.hgetall(f"user:{uname}")
        if not u:
            continue
        users_out.append({
            "username":    u.get("username", uname),
            "role_id":     u.get("role_id"),
            "regime_id":   u.get("regime_id"),
            "observacoes": u.get("observacoes", ""), 
            "phone":       u.get("phone", ""),
            "email":       u.get("email", "")
        })

    return {"users": users_out}


@router.get("/map/base")
async def get_base_users(
    key: str = Query(...),
    r=Depends(get_redis),
):
    """
    Retorna os usuários que estão atualmente nesta base/região/estado.
    """
    node_type, node_id = key.split(":", 1)

    if node_type == "base":
        usernames = await r.smembers(f"index:location:{node_id}:users")
    elif node_type == "region":
        usernames = await r.smembers(f"index:region:{node_id}:users")
    elif node_type == "state":
        usernames = await r.smembers(f"index:state:{node_id}:users")
    else:
        return {"users": []}

    users_out = []
    for uname in usernames:
        u = await r.hgetall(f"user:{uname}")
        if not u:
            continue
        users_out.append({
            "username":    u.get("username", uname),
            "role_id":     u.get("role_id"),
            "regime_id":   u.get("regime_id"),
            "observacoes": u.get("observacoes", ""),
            "base_id":     u.get("base_id"),
            "phone":       u.get("phone", ""),
            "email":       u.get("email", "")
        })

    return {"users": users_out}