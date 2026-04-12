"""
Migra um username no Redis, atualizando todas as chaves relacionadas.

Uso:
    python migrate_username.py "Diogo Duarte" "diogo_duarte"

Variáveis de ambiente (opcionais):
    REDIS_HOST  (default: localhost)
    REDIS_PORT  (default: 6379)
    REDIS_DB    (default: 0)
    REDIS_PASSWORD (default: None)
"""
import asyncio
import json
import os
import sys
import redis.asyncio as aioredis

from dotenv import load_dotenv

load_dotenv()

r = aioredis.Redis.from_url(
    os.getenv("REDIS_URL"),
    decode_responses=True,
)


async def migrate(old: str, new: str):

    print(f"\n{'='*60}")
    print(f"  Migrando '{old}' → '{new}'")
    print(f"{'='*60}\n")

    # ── 0. Sanity checks ──────────────────────────────────────────
    if not await r.exists(f"user:{old}"):
        print(f"[ERRO] Usuário '{old}' não encontrado no Redis.")
        await r.aclose()
        return

    if await r.exists(f"user:{new}"):
        print(f"[ERRO] Username '{new}' já existe. Escolha outro nome.")
        await r.aclose()
        return

    # ── 1. Copia hash do usuário ──────────────────────────────────
    user_data = await r.hgetall(f"user:{old}")
    user_data["username"] = new
    await r.hset(f"user:{new}", mapping=user_data)
    print(f"[OK] Hash user:{new} criado com {len(user_data)} campo(s)")

    # ── 2. Atualiza índices de set ────────────────────────────────
    index_fields = [
        ("base_id",    "index:location:{}:users"),
        ("role_id",    "index:role:{}:users"),
        ("region_id",  "index:region:{}:users"),
        ("state_id",   "index:state:{}:users"),
        ("regime_id",  "index:regime:{}:users"),
    ]

    await r.srem("index:all:users", old)
    await r.sadd("index:all:users", new)
    print(f"[OK] index:all:users atualizado")

    for field, pattern in index_fields:
        val = user_data.get(field)
        if val and val not in ("0", "None", ""):
            key = pattern.format(val)
            await r.srem(key, old)
            await r.sadd(key, new)
            print(f"[OK] {key} → removido '{old}', adicionado '{new}'")

    # ── 3. Migra interesses ───────────────────────────────────────
    old_interests_key = f"user:{old}:interests"
    new_interests_key = f"user:{new}:interests"
    interest_ids = await r.smembers(old_interests_key)

    if interest_ids:
        for iid in interest_ids:
            await r.hset(f"interest:{iid}", "username", new)
            print(f"[OK] interest:{iid} → username atualizado para '{new}'")
        await r.rename(old_interests_key, new_interests_key)
        print(f"[OK] Set de interesses renomeado para {new_interests_key}")
    else:
        print(f"[--] Nenhum interesse encontrado para '{old}'")

    # ── 4. Migra matches ──────────────────────────────────────────
    old_matches_key = f"user:{old}:matches"
    new_matches_key = f"user:{new}:matches"
    match_ids = await r.smembers(old_matches_key)

    if match_ids:
        for mid in match_ids:
            raw = await r.get(f"match:{mid}")
            if not raw:
                print(f"[WARN] match:{mid} não encontrado, pulando")
                continue

            match = json.loads(raw)
            old_chain_usernames = [s["username"] for s in match.get("chain", [])]

            # Atualiza username dentro do JSON da chain
            for step in match.get("chain", []):
                if step["username"] == old:
                    step["username"] = new

            new_chain_usernames = [s["username"] for s in match.get("chain", [])]

            # Recria a chave de dedup (match:members:...)
            old_members_key = f"match:members:{'|'.join(sorted(old_chain_usernames))}"
            new_members_key = f"match:members:{'|'.join(sorted(new_chain_usernames))}"

            pipe = r.pipeline()
            pipe.set(f"match:{mid}", json.dumps(match))
            pipe.delete(old_members_key)
            pipe.set(new_members_key, mid)
            await pipe.execute()

            print(f"[OK] match:{mid} → JSON e dedup atualizados")
            print(f"      {old_members_key}")
            print(f"   →  {new_members_key}")

        await r.rename(old_matches_key, new_matches_key)
        print(f"[OK] Set de matches renomeado para {new_matches_key}")
    else:
        print(f"[--] Nenhum match encontrado para '{old}'")

    # ── 5. Remove hash antigo ─────────────────────────────────────
    await r.delete(f"user:{old}")
    print(f"[OK] Hash user:{old} removido")

    # ── 6. Resumo final ───────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Migração concluída com sucesso!")
    print(f"  '{old}' → '{new}'")
    print(f"  Interesses migrados: {len(interest_ids)}")
    print(f"  Matches migrados:    {len(match_ids)}")
    print(f"{'='*60}\n")

    await r.aclose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python migrate_username.py \"username antigo\" \"username_novo\"")
        sys.exit(1)

    old_username = sys.argv[1]
    new_username = sys.argv[2]
    asyncio.run(migrate(old_username, new_username))