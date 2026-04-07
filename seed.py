"""
Script de população inicial do Redis.
Estrutura hierárquica: State → Region → Location (base)
Cada entidade tem lat/lng próprio.

Uso: python seed.py
"""
import asyncio
import redis.asyncio as aioredis
from dotenv import load_dotenv
import os

load_dotenv()

# ─── Estados ─────────────────────────────────────────────────────────────────

STATES = {
    "1": { "name": "RJ", "lat": -22.9068,  "lng": -43.1729 },
    "2": { "name": "SP", "lat": -23.5505,  "lng": -46.6333 },
    "3": { "name": "ES", "lat": -20.3155,  "lng": -40.3128 },
    "4": { "name": "BA", "lat": -12.9714,  "lng": -38.5014 },
    "5": { "name": "AM", "lat":  -3.1190,  "lng": -60.0217 },
}

# ─── Regiões ──────────────────────────────────────────────────────────────────

REGIONS = {
    "1": { "name": "Macaé",          "state_id": "1", "lat": -22.3803, "lng": -41.7869 },
    "2": { "name": "Bacia de Campos","state_id": "1", "lat": -22.4000, "lng": -40.5000 },
    "3": { "name": "Rio de Janeiro", "state_id": "1", "lat": -22.9068, "lng": -43.1729 },
    "4": { "name": "Santos",         "state_id": "2", "lat": -23.9535, "lng": -46.3333 },
    "5": { "name": "Vitória",        "state_id": "3", "lat": -20.3155, "lng": -40.3128 },
    "6": { "name": "Salvador",       "state_id": "4", "lat": -12.9714, "lng": -38.5014 },
    "7": { "name": "Manaus",         "state_id": "5", "lat":  -3.1190, "lng": -60.0217 },
}

# ─── Bases (Locations) ────────────────────────────────────────────────────────

LOCATIONS = {
    "EDISA": {
        "name": "EDISA", "region_id": "4", "state_id": "2",
        "type": "Onshore", "lat": -23.9535, "lng": -46.3333,
    },
    "EDIVIT": {
        "name": "EDIVIT", "region_id": "5", "state_id": "3",
        "type": "Onshore", "lat": -20.3155, "lng": -40.3128,
    },
    "IMBETIBA": {
        "name": "Base de Imbetiba", "region_id": "1", "state_id": "1",
        "type": "Onshore", "lat": -22.3803, "lng": -41.7725,
    },
    "PARQUE_TUBOS": {
        "name": "Parque de Tubos", "region_id": "1", "state_id": "1",
        "type": "Onshore", "lat": -22.4182, "lng": -41.8385,
    },
    "P37": {
        "name": "Plataforma P-37", "region_id": "2", "state_id": "1",
        "type": "Offshore", "lat": -22.4283, "lng": -40.1834,
    },
}

# ─── Outros metadados ─────────────────────────────────────────────────────────

ROLES = {
    "1": "Logística de Transportes", "2": "Operação",
    "3": "Manutenção", "4": "Engenharia", "5": "Administração",
}

ROLE_TYPES = { "1": "Nível Superior", "2": "Nível Técnico" }

DEPARTMENTS = {
    "1": "POÇOS", "2": "SUB", "3": "SUPRIMENTOS",
    "4": "LOEP", "5": "OPERAÇÃO", "6": "COMPARTILHADO"
}

WORK_REGIMES = {
    "1": "Turno", "2": "Administrativo", "3": "Embarcado (Offshore)",
}

# ─── Seed ─────────────────────────────────────────────────────────────────────

async def seed(r):
    await r.flushdb()
    pipe = r.pipeline()

    # States
    for sid, data in STATES.items():
        pipe.hset(f"meta:states:{sid}", mapping={k: str(v) for k, v in data.items()})
        pipe.sadd("meta:states:list", sid)

    # Regions
    for rid, data in REGIONS.items():
        pipe.hset(f"meta:regions:{rid}", mapping={k: str(v) for k, v in data.items()})
        pipe.sadd("meta:regions:list", rid)

    # Locations
    for base_id, data in LOCATIONS.items():
        pipe.hset(f"meta:locations:{base_id}", mapping={k: str(v) for k, v in data.items()})
        pipe.sadd("meta:locations:list", base_id)

    # Lookup hashes simples (para dropdowns)
    for rid, name in ROLES.items():        pipe.hset("meta:roles",        rid, name)
    for rid, name in ROLE_TYPES.items():   pipe.hset("meta:role_types",   rid, name)
    for did, name in DEPARTMENTS.items():  pipe.hset("meta:departments",  did, name)
    for wid, name in WORK_REGIMES.items(): pipe.hset("meta:work_regimes", wid, name)

    await pipe.execute()
    print(f"✓ {len(STATES)} estados, {len(REGIONS)} regiões, {len(LOCATIONS)} bases")
    print(f"✓ roles, role_types, departments, work_regimes")


async def main():
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    r = await aioredis.from_url(url, decode_responses=True)
    try:
        await seed(r)
    finally:
        await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())