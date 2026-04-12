import asyncio
from fastapi import APIRouter, Depends, Query
from core.config import get_redis
from services import redis_service as db

router = APIRouter()


@router.get("/init")
async def init(r=Depends(get_redis)):
    """Bootstrap público — metadados + arcos do mapa."""
    metadata, map_interests = await asyncio.gather(
        db.get_all_metadata(r),
        db.get_map_interests(r),
    )
    return {"metadata": metadata, "map_interests": map_interests}


@router.get("/admin/users")
async def list_all_users(r=Depends(get_redis)):
    """
    Lista todos os usuários cadastrados com perfil completo e seus interesses e matches.
    Útil para debug e administração.
    """
    usernames = await r.smembers("index:all:users")
    if not usernames:
        return {"total": 0, "users": []}

    users_out = []
    for uname in sorted(usernames):
        u = await r.hgetall(f"user:{uname}")
        if not u:
            continue

        interests = await db.get_user_interests(r, uname)
        matches   = await db.get_user_matches(r, uname)

        users_out.append({
            "username":      uname,
            "base_id":       u.get("base_id"),
            "region_id":     u.get("region_id"),
            "state_id":      u.get("state_id"),
            "role_id":       u.get("role_id"),
            "role_type_id":  u.get("role_type_id"),
            "department_id": u.get("department_id"),
            "regime_id":     u.get("regime_id"),
            "state":         u.get("state", "permuta"),
            "email":         u.get("email"),
            "phone":         u.get("phone"),
            "interests":     interests,
            "matches":       [
                {
                    "id":    m["id"],
                    "chain": [s["username"] for s in m.get("chain", [])],
                }
                for m in matches
            ],
        })

    return {"total": len(users_out), "users": users_out}


@router.get("/map/arc")
async def get_arc_users(
    from_key: str = Query(...),
    to_key:   str = Query(...),
    r=Depends(get_redis),
):
    """
    Retorna os usuários que têm interesse no arco from_key→to_key.
    Inclui perfil público (sem phone/email — só liberado após match confirmado).
    """
    all_keys = await r.keys("interest:*")
    if not all_keys:
        return {"users": []}

    pipe = r.pipeline()
    for k in all_keys:
        pipe.hgetall(k)
    interests = await pipe.execute()

    matching_usernames = set()
    for interest in interests:
        if not interest:
            continue
        username = interest.get("username")
        if not username:
            continue
        user = await r.hgetall(f"user:{username}")
        if not user:
            continue
        user_base = f"base:{user.get('base_id', '0')}"
        if user_base != from_key:
            continue

        target_base   = interest.get("target_base_id",   "0")
        target_region = interest.get("target_region_id", "0")
        target_state  = interest.get("target_state_id",  "0")

        to_type, to_id = to_key.split(":", 1)
        matched = False
        if to_type == "base"   and target_base   == to_id: matched = True
        if to_type == "region" and target_region == to_id: matched = True
        if to_type == "state"  and target_state  == to_id: matched = True

        if matched:
            matching_usernames.add(username)

    users_out = []
    for uname in matching_usernames:
        u = await r.hgetall(f"user:{uname}")
        if not u:
            continue
        users_out.append({
            "name":        u.get("name", ""),
            "username":    u.get("username", uname),
            "role_id":     u.get("role_id"),
            "role_type_id": u.get("role_type_id"),
            "regime_id":   u.get("regime_id"),
            "department_id": u.get("department_id"),
            "observacoes": u.get("observacoes", ""),
            "phone":       u.get("phone", ""),
            "email":       u.get("email", ""),
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
            "email":       u.get("email", ""),
        })

    return {"users": users_out}