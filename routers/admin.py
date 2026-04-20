"""
routers/admin.py — Rotas de administração (apenas is_admin=true)
Gerencia estados, regiões e bases (locations) do seed.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from core.security import get_current_username          # seu dep. de autenticação
from services import redis_service as db
from models.schemas import StatePayload, RegionPayload, LocationPayload, UserAdminPayload, RoleTypePayload, RolePayload, DepartmentPayload
from core.config import get_redis

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Dependência de guarda ────────────────────────────────────────────────────

async def require_admin(username: str = Depends(get_current_username), r = Depends(get_redis)):
    user = await db.get_user(r, username)
    if not user or str(user.get("is_admin", "false")).lower() != "true":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
    return user





# ─── Estados ──────────────────────────────────────────────────────────────────

@router.get("/states", dependencies=[Depends(require_admin)])
async def list_states(r=Depends(get_redis)):
    ids = await r.smembers("meta:states:list")
    pipe = r.pipeline()
    for sid in ids:
        pipe.hgetall(f"meta:states:{sid}")
    results = await pipe.execute()
    return [{"id": sid, **data} for sid, data in zip(ids, results) if data]


@router.post("/states", dependencies=[Depends(require_admin)])
async def create_state(payload: StatePayload, r=Depends(get_redis)):
    new_id = str(await r.incr("meta:counters:states"))
    mapping = {"name": payload.name, "lat": str(payload.lat), "lng": str(payload.lng)}
    pipe = r.pipeline()
    pipe.hset(f"meta:states:{new_id}", mapping=mapping)
    pipe.sadd("meta:states:list", new_id)
    await pipe.execute()
    return {"id": new_id, **mapping}


@router.put("/states/{state_id}", dependencies=[Depends(require_admin)])
async def update_state(state_id: str, payload: StatePayload, r=Depends(get_redis)):
    exists = await r.exists(f"meta:states:{state_id}")
    if not exists:
        raise HTTPException(status_code=404, detail="Estado não encontrado.")
    mapping = {"name": payload.name, "lat": str(payload.lat), "lng": str(payload.lng)}
    await r.hset(f"meta:states:{state_id}", mapping=mapping)
    return {"id": state_id, **mapping}


@router.delete("/states/{state_id}", dependencies=[Depends(require_admin)])
async def delete_state(state_id: str, r=Depends(get_redis)):
    pipe = r.pipeline()
    pipe.delete(f"meta:states:{state_id}")
    pipe.srem("meta:states:list", state_id)
    await pipe.execute()
    return {"deleted": state_id}


# ─── Regiões ──────────────────────────────────────────────────────────────────

@router.get("/regions", dependencies=[Depends(require_admin)])
async def list_regions(r=Depends(get_redis)):
    ids = await r.smembers("meta:regions:list")
    pipe = r.pipeline()
    for rid in ids:
        pipe.hgetall(f"meta:regions:{rid}")
    results = await pipe.execute()
    return [{"id": rid, **data} for rid, data in zip(ids, results) if data]


@router.post("/regions", dependencies=[Depends(require_admin)])
async def create_region(payload: RegionPayload, r=Depends(get_redis)):
    new_id = str(await r.incr("meta:counters:regions"))
    mapping = {
        "name": payload.name, "state_id": payload.state_id,
        "lat": str(payload.lat), "lng": str(payload.lng),
    }
    pipe = r.pipeline()
    pipe.hset(f"meta:regions:{new_id}", mapping=mapping)
    pipe.sadd("meta:regions:list", new_id)
    await pipe.execute()
    return {"id": new_id, **mapping}


@router.put("/regions/{region_id}", dependencies=[Depends(require_admin)])
async def update_region(region_id: str, payload: RegionPayload, r=Depends(get_redis)):
    if not await r.exists(f"meta:regions:{region_id}"):
        raise HTTPException(status_code=404, detail="Região não encontrada.")
    mapping = {
        "name": payload.name, "state_id": payload.state_id,
        "lat": str(payload.lat), "lng": str(payload.lng),
    }
    await r.hset(f"meta:regions:{region_id}", mapping=mapping)
    return {"id": region_id, **mapping}


@router.delete("/regions/{region_id}", dependencies=[Depends(require_admin)])
async def delete_region(region_id: str, r=Depends(get_redis)):
    pipe = r.pipeline()
    pipe.delete(f"meta:regions:{region_id}")
    pipe.srem("meta:regions:list", region_id)
    await pipe.execute()
    return {"deleted": region_id}


# ─── Bases (Locations) ────────────────────────────────────────────────────────

@router.get("/locations", dependencies=[Depends(require_admin)])
async def list_locations(r=Depends(get_redis)):
    ids = await r.smembers("meta:locations:list")
    pipe = r.pipeline()
    for lid in ids:
        pipe.hgetall(f"meta:locations:{lid}")
    results = await pipe.execute()
    return [{"id": lid, **data} for lid, data in zip(ids, results) if data]


@router.post("/locations", dependencies=[Depends(require_admin)])
async def create_location(payload: LocationPayload, r=Depends(get_redis)):
    # ID gerado como slug numérico incremental para manter o padrão
    new_id = str(await r.incr("meta:counters:locations"))
    mapping = {
        "name": payload.name, "region_id": payload.region_id,
        "state_id": payload.state_id, "type": payload.type,
        "lat": str(payload.lat), "lng": str(payload.lng),
    }
    pipe = r.pipeline()
    pipe.hset(f"meta:locations:{new_id}", mapping=mapping)
    pipe.sadd("meta:locations:list", new_id)
    await pipe.execute()
    return {"id": new_id, **mapping}


@router.put("/locations/{location_id}", dependencies=[Depends(require_admin)])
async def update_location(location_id: str, payload: LocationPayload, r=Depends(get_redis)):
    if not await r.exists(f"meta:locations:{location_id}"):
        raise HTTPException(status_code=404, detail="Base não encontrada.")
    mapping = {
        "name": payload.name, "region_id": payload.region_id,
        "state_id": payload.state_id, "type": payload.type,
        "lat": str(payload.lat), "lng": str(payload.lng),
    }
    await r.hset(f"meta:locations:{location_id}", mapping=mapping)
    return {"id": location_id, **mapping}


@router.delete("/locations/{location_id}", dependencies=[Depends(require_admin)])
async def delete_location(location_id: str, r=Depends(get_redis)):
    pipe = r.pipeline()
    pipe.delete(f"meta:locations:{location_id}")
    pipe.srem("meta:locations:list", location_id)
    await pipe.execute()
    return {"deleted": location_id}

# ─── Tipos de Cargo (role_types) ──────────────────────────────────────────────
# Hash simples: meta:role_types  { "1": "Nível Técnico", "2": "Nível Superior" }
 
@router.get("/role-types", dependencies=[Depends(require_admin)])
async def list_role_types(r=Depends(get_redis)):
    data = await r.hgetall("meta:role_types")
    return sorted([{"id": k, "name": v} for k, v in data.items()], key=lambda x: x["name"])
 
@router.post("/role-types", dependencies=[Depends(require_admin)])
async def create_role_type(payload: RoleTypePayload, r=Depends(get_redis)):
    new_id = str(await r.incr("meta:counters:role_types"))
    await r.hset("meta:role_types", new_id, payload.name)
    return {"id": new_id, "name": payload.name}
 
@router.put("/role-types/{role_type_id}", dependencies=[Depends(require_admin)])
async def update_role_type(role_type_id: str, payload: RoleTypePayload, r=Depends(get_redis)):
    if not await r.hexists("meta:role_types", role_type_id):
        raise HTTPException(status_code=404, detail="Tipo de cargo não encontrado.")
    await r.hset("meta:role_types", role_type_id, payload.name)
    return {"id": role_type_id, "name": payload.name}
 
@router.delete("/role-types/{role_type_id}", dependencies=[Depends(require_admin)])
async def delete_role_type(role_type_id: str, r=Depends(get_redis)):
    # Bloqueia se houver cargos vinculados
    role_ids = await r.smembers("meta:roles:list")
    pipe = r.pipeline()
    for rid in role_ids:
        pipe.hget(f"meta:roles:{rid}", "role_type_id")
    type_ids = await pipe.execute()
    linked = [rid for rid, tid in zip(role_ids, type_ids) if tid == role_type_id]
    if linked:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo em uso por {len(linked)} cargo(s). Remova-os antes de deletar o tipo."
        )
    await r.hdel("meta:role_types", role_type_id)
    return {"deleted": role_type_id}
 
 
# ─── Cargos (roles) ───────────────────────────────────────────────────────────
# Hashes individuais: meta:roles:{id}  { name, role_type_id }
# Índice de IDs: meta:roles:list (set)
 
@router.get("/roles", dependencies=[Depends(require_admin)])
async def list_roles(r=Depends(get_redis)):
    ids = await r.smembers("meta:roles:list")
    pipe = r.pipeline()
    for rid in ids:
        pipe.hgetall(f"meta:roles:{rid}")
    results = await pipe.execute()
    return [{"id": rid, **data} for rid, data in zip(ids, results) if data]
 
@router.post("/roles", dependencies=[Depends(require_admin)])
async def create_role(payload: RolePayload, r=Depends(get_redis)):
    if not await r.hexists("meta:role_types", payload.role_type_id):
        raise HTTPException(status_code=400, detail="Tipo de cargo inválido.")
    new_id = str(await r.incr("meta:counters:roles"))
    mapping = {"name": payload.name, "role_type_id": payload.role_type_id}
    pipe = r.pipeline()
    pipe.hset(f"meta:roles:{new_id}", mapping=mapping)
    pipe.sadd("meta:roles:list", new_id)
    await pipe.execute()
    return {"id": new_id, **mapping}
 
@router.put("/roles/{role_id}", dependencies=[Depends(require_admin)])
async def update_role(role_id: str, payload: RolePayload, r=Depends(get_redis)):
    if not await r.exists(f"meta:roles:{role_id}"):
        raise HTTPException(status_code=404, detail="Cargo não encontrado.")
    if not await r.hexists("meta:role_types", payload.role_type_id):
        raise HTTPException(status_code=400, detail="Tipo de cargo inválido.")
    mapping = {"name": payload.name, "role_type_id": payload.role_type_id}
    await r.hset(f"meta:roles:{role_id}", mapping=mapping)
    return {"id": role_id, **mapping}
 
@router.delete("/roles/{role_id}", dependencies=[Depends(require_admin)])
async def delete_role(role_id: str, r=Depends(get_redis)):
    pipe = r.pipeline()
    pipe.delete(f"meta:roles:{role_id}")
    pipe.srem("meta:roles:list", role_id)
    await pipe.execute()
    return {"deleted": role_id}

# ─── Departamentos ────────────────────────────────────────────────────────────
# Hash simples: meta:departments  { "1": "POÇOS", "2": "SUB", ... }

 
@router.get("/departments", dependencies=[Depends(require_admin)])
async def list_departments(r=Depends(get_redis)):
    data = await r.hgetall("meta:departments")
    return sorted([{"id": k, "name": v} for k, v in data.items()], key=lambda x: x["name"])
 
@router.post("/departments", dependencies=[Depends(require_admin)])
async def create_department(payload: DepartmentPayload, r=Depends(get_redis)):
    new_id = str(await r.incr("meta:counters:departments"))
    await r.hset("meta:departments", new_id, payload.name)
    return {"id": new_id, "name": payload.name}
 
@router.put("/departments/{dept_id}", dependencies=[Depends(require_admin)])
async def update_department(dept_id: str, payload: DepartmentPayload, r=Depends(get_redis)):
    if not await r.hexists("meta:departments", dept_id):
        raise HTTPException(status_code=404, detail="Departamento não encontrado.")
    await r.hset("meta:departments", dept_id, payload.name)
    return {"id": dept_id, "name": payload.name}
 
@router.delete("/departments/{dept_id}", dependencies=[Depends(require_admin)])
async def delete_department(dept_id: str, r=Depends(get_redis)):
    if not await r.hexists("meta:departments", dept_id):
        raise HTTPException(status_code=404, detail="Departamento não encontrado.")
    await r.hdel("meta:departments", dept_id)
    return {"deleted": dept_id}

# ─── Gerenciar admins ─────────────────────────────────────────────────────────
 
@router.patch("/users/{username}/admin", dependencies=[Depends(require_admin)])
async def set_user_admin(username: str, payload: UserAdminPayload, r=Depends(get_redis)):
    user = await db.get_user(r, username)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    await r.hset(f"user:{username}", "is_admin", str(payload.is_admin).lower())
    return {"username": username, "is_admin": payload.is_admin}
 