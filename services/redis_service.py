"""
Camada de acesso ao Redis.
Identificador do usuário: username
Matches vivem em match:{id} com índices bidirecionais.
"""
import json
import uuid
from typing import Optional

META_KEYS = ["role_types", "departments", "work_regimes"]


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _clean(data: dict) -> dict:
    """Remove valores None/'None'/'' para não salvar lixo no Redis."""
    return {k: str(v) for k, v in data.items() if v is not None and str(v) not in ("None", "")}

def _valid(val) -> bool:
    return val is not None and str(val) not in ("None", "", "0")


# ─── Metadados ────────────────────────────────────────────────────────────────

async def get_all_metadata(r) -> dict:
    pipe = r.pipeline()
    for key in META_KEYS:
        pipe.hgetall(f"meta:{key}")
    pipe.smembers("meta:locations:list")
    pipe.smembers("meta:regions:list")
    pipe.smembers("meta:states:list")
    # Adicionado a busca da lista de roles
    pipe.smembers("meta:roles:list")
    results = await pipe.execute()

    metadata = {META_KEYS[i]: results[i] for i in range(len(META_KEYS))}
    location_ids = results[-4]
    region_ids   = results[-3]
    state_ids    = results[-2]
    role_ids     = results[-1] # Pega os IDs da lista de roles

    pipe2 = r.pipeline()
    for lid in location_ids:  pipe2.hgetall(f"meta:locations:{lid}")
    for rid in region_ids:    pipe2.hgetall(f"meta:regions:{rid}")
    for sid in state_ids:     pipe2.hgetall(f"meta:states:{sid}")
    for roid in role_ids:     pipe2.hgetall(f"meta:roles:{roid}") # Pega os dados de cada role
    res2 = await pipe2.execute()

    nl, nr, ns = len(location_ids), len(region_ids), len(state_ids)

    locations = {}
    for lid, d in zip(location_ids, res2[:nl]):
        if d:
            locations[lid] = {
                "name":      d.get("name", lid),
                "coords":    [float(d.get("lng", 0)), float(d.get("lat", 0))],
                "type":      d.get("type", "Terra"),
                "region_id": d.get("region_id"),
                "state_id":  d.get("state_id"),
            }

    regions = {}
    for rid, d in zip(region_ids, res2[nl:nl+nr]):
        if d:
            regions[rid] = {
                "name":     d.get("name", rid),
                "coords":   [float(d.get("lng", 0)), float(d.get("lat", 0))],
                "state_id": d.get("state_id"),
            }

    states_meta = {}
    for sid, d in zip(state_ids, res2[nl+nr:nl+nr+ns]):
        if d:
            states_meta[sid] = {
                "name":   d.get("name", sid),
                "coords": [float(d.get("lng", 0)), float(d.get("lat", 0))],
            }

    # Novo parse para popular o dicionário de roles com name e role_type_id
    roles = {}
    for roid, d in zip(role_ids, res2[nl+nr+ns:]):
        if d:
            roles[roid] = {
                "name": d.get("name", roid),
                "role_type_id": d.get("role_type_id")
            }

    metadata["locations"] = locations
    metadata["regions"]   = regions
    metadata["states"]    = states_meta
    metadata["roles"]     = roles # Injetado manualmente com o formato estruturado
    
    return metadata

async def get_map_interests(r) -> list:
    """
    Deriva arcos do mapa a partir dos interesses ativas.
    Agrupa por (from_key, to_key) — sem duplicatas.
    Usuários com state='liberado' também geram arcos de saída.
    """
    all_keys = await r.keys("interest:*")
    if not all_keys:
        return []

    pipe = r.pipeline()
    for k in all_keys:
        pipe.hgetall(k)
    interests = await pipe.execute()

    arc_counts = {}
    for interest in interests:
        if not interest:
            continue
        username = interest.get("username")
        if not username:
            continue
        user = await r.hgetall(f"user:{username}")
        if not user:
            continue
        from_base = user.get("base_id", "0")
        if not from_base or from_base == "0":
            continue

        target_base   = interest.get("target_base_id",   "0")
        target_region = interest.get("target_region_id", "0")
        target_state  = interest.get("target_state_id",  "0")

        if target_base != "0":
            to_key = f"base:{target_base}"
        elif target_region != "0":
            to_key = f"region:{target_region}"
        elif target_state != "0":
            to_key = f"state:{target_state}"
        else:
            continue

        if from_base == target_base:
            continue

        key = (f"base:{from_base}", to_key)
        arc_counts[key] = arc_counts.get(key, 0) + 1

    return [{"from": frm, "to": to, "count": count} for (frm, to), count in arc_counts.items()]


async def increment_arc(r, from_base: str, to_base: str):
    await r.incr(f"arc:{from_base}:{to_base}")


# ─── Usuários ─────────────────────────────────────────────────────────────────

async def get_user(r, username: str) -> Optional[dict]:
    data = await r.hgetall(f"user:{username}")
    return data if data else None

async def get_user_by_username(r, username: str) -> Optional[dict]:
    return await get_user(r, username)

async def username_exists(r, username: str) -> bool:
    return await r.exists(f"user:{username}") == 1

async def save_user(r, username: str, data: dict):
    cleaned = _clean(data)
    await r.hset(f"user:{username}", mapping=cleaned)
    await r.sadd("index:all:users", username)

async def update_user_indexes(r, username: str, old: dict, new: dict):
    pipe = r.pipeline()

    def reindex(field, prefix):
        o, n = old.get(field), new.get(field)
        if o != n:
            if _valid(o): pipe.srem(f"index:{prefix}:{o}:users", username)
            if _valid(n): pipe.sadd(f"index:{prefix}:{n}:users", username)

    reindex("base_id",    "location")
    reindex("role_id",    "role")
    reindex("region_id",  "region")
    reindex("state_id",   "state")
    reindex("regime_id",  "regime")
    await pipe.execute()

async def add_user_to_indexes(r, username: str, user: dict):
    pipe = r.pipeline()
    pipe.sadd("index:all:users", username)
    if _valid(user.get("base_id")):   pipe.sadd(f"index:location:{user['base_id']}:users",  username)
    if _valid(user.get("role_id")):   pipe.sadd(f"index:role:{user['role_id']}:users",       username)
    if _valid(user.get("region_id")): pipe.sadd(f"index:region:{user['region_id']}:users",  username)
    if _valid(user.get("state_id")):  pipe.sadd(f"index:state:{user['state_id']}:users",    username)
    if _valid(user.get("regime_id")): pipe.sadd(f"index:regime:{user['regime_id']}:users",  username)
    await pipe.execute()


# ─── Interesses ────────────────────────────────────────────────────────────────

async def save_interest(r, username: str, interest: dict) -> str:
    interest_id = str(uuid.uuid4())
    interest["id"]       = interest_id
    interest["username"] = username
    pipe = r.pipeline()
    pipe.hset(f"interest:{interest_id}", mapping={k: str(v) for k, v in interest.items()})
    pipe.sadd(f"user:{username}:interests", interest_id)
    await pipe.execute()
    return interest_id

async def delete_interest(r, username: str, interest_id: str) -> Optional[dict]:
    """Deleta e retorna seus dados (para uso no recálculo)."""
    if not await r.sismember(f"user:{username}:interests", interest_id):
        return None
    interest = await r.hgetall(f"interest:{interest_id}")
    pipe = r.pipeline()
    pipe.srem(f"user:{username}:interests", interest_id)
    pipe.delete(f"interest:{interest_id}")
    await pipe.execute()
    return interest

async def get_user_interests(r, username: str) -> list:
    ids = await r.smembers(f"user:{username}:interests")
    if not ids:
        return []
    pipe = r.pipeline()
    for iid in ids:
        pipe.hgetall(f"interest:{iid}")
    return [res for res in await pipe.execute() if res]

async def get_all_interests(r) -> list:
    """Retorna todas os interesses do sistema."""
    keys = await r.keys("interest:*")
    if not keys:
        return []
    pipe = r.pipeline()
    for k in keys:
        pipe.hgetall(k)
    return [res for res in await pipe.execute() if res]


# ─── Matches (tabela própria) ─────────────────────────────────────────────────

async def save_match(r, chain_usernames: list, chain_data: list) -> str:
    """
    Salva um match e constrói índices bidirecionais.
    chain_usernames: ['alice', 'bob', ...]
    chain_data: [{'username':..., 'base_id':...}, ...]
    """
    match_id = str(uuid.uuid4())
    match    = {"id": match_id, "chain": chain_data}

    pipe = r.pipeline()
    pipe.set(f"match:{match_id}", json.dumps(match))

    # Índice: conjunto de usernames ordenado (para dedup)
    members_key = "|".join(sorted(chain_usernames))
    pipe.set(f"match:members:{members_key}", match_id)

    for username in chain_usernames:
        pipe.sadd(f"user:{username}:matches", match_id)

    await pipe.execute()
    return match_id

async def match_exists_for_chain(r, chain_usernames: list) -> bool:
    """Verifica se já existe match para esse conjunto de usuários."""
    members_key = "|".join(sorted(chain_usernames))
    return await r.exists(f"match:members:{members_key}") == 1

async def delete_match(r, match_id: str):
    """Remove match e limpa todos os índices."""
    raw = await r.get(f"match:{match_id}")
    if not raw:
        return
    match = json.loads(raw)
    chain_usernames = [step["username"] for step in match.get("chain", [])]
    members_key = "|".join(sorted(chain_usernames))

    pipe = r.pipeline()
    pipe.delete(f"match:{match_id}")
    pipe.delete(f"match:members:{members_key}")
    for username in chain_usernames:
        pipe.srem(f"user:{username}:matches", match_id)
    await pipe.execute()

async def get_user_matches(r, username: str) -> list:
    ids = await r.smembers(f"user:{username}:matches")
    if not ids:
        return []
    pipe = r.pipeline()
    for mid in ids:
        pipe.get(f"match:{mid}")
    results = await pipe.execute()
    return [json.loads(m) for m in results if m]

async def get_all_match_ids(r) -> set:
    keys = await r.keys("match:*")
    # Filtra só os IDs reais (ignora match:members:*)
    return {k.split("match:")[1] for k in keys if not k.startswith("match:members:")}

async def invalidate_matches_containing(r, username: str) -> list:
    """
    Remove todos os matches que contenham `username`.
    Retorna lista de match_ids removidos.
    """
    match_ids = list(await r.smembers(f"user:{username}:matches"))
    for mid in match_ids:
        await delete_match(r, mid)
    return match_ids

# ─── Recuperação de Senha ─────────────────────────────────────────────────────

async def create_reset_token(r, username: str, expires_in: int = 3600) -> str:
    """Gera um token UUID e salva no Redis referenciando o username com expiração."""
    token = str(uuid.uuid4())
    await r.setex(f"reset_token:{token}", expires_in, username)
    return token

async def get_username_by_reset_token(r, token: str) -> Optional[str]:
    """Valida o token e retorna o username se existir e não estiver expirado."""
    return await r.get(f"reset_token:{token}")

async def delete_reset_token(r, token: str):
    """Invalida o token após o uso."""
    await r.delete(f"reset_token:{token}")

async def update_user_password(r, username: str, new_password_hash: str):
    """Atualiza o hash da senha do usuário no banco."""
    await r.hset(f"user:{username}", "password", new_password_hash)

async def save_password_reset_token(r, username: str) -> str:
    """Gera um token único de expiração rápida (1 hora) para reset de senha."""
    token = str(uuid.uuid4())
    # Expira em 3600 segundos (1 hora)
    await r.setex(f"reset_token:{token}", 3600, username)
    return token

async def get_username_by_reset_token(r, token: str) -> Optional[str]:
    """Recupera o username associado ao token."""
    return await r.get(f"reset_token:{token}")

async def delete_reset_token(r, token: str):
    """Invalida o token após o uso."""
    await r.delete(f"reset_token:{token}")

async def update_user_password(r, username: str, hashed_password: str):
    """Atualiza a senha do usuário no hash."""
    await r.hset(f"user:{username}", "password_hash", hashed_password)

async def add_metadata_entry(r, category: str, value: str) -> str:
    new_id = await r.hincrby("meta:counters", category, 1)
    await r.hset(f"meta:{category}", str(new_id), value)
    return str(new_id)