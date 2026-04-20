import asyncio
import logging
import time                                          # ← NOVO
from services import timed_db as db                 # ← trocado de redis_service para timed_db
from services.notification_service import notify_match
from core.config import get_settings

settings = get_settings()

log = logging.getLogger(__name__)


# ─── Entrada principal ────────────────────────────────────────────────────────

async def recalculate_matches_for_user(r, trigger_username: str):
    db.reset_metrics()                               # ← NOVO: zera contadores da sessão
    log.info(f"[RECALC] ▶ iniciando para '{trigger_username}'")

    trigger_user = await db.get_user(r, trigger_username)
    if not trigger_user:
        log.warning(f"[RECALC] usuário '{trigger_username}' não encontrado, abortando")
        return

    log.debug(f"[RECALC] perfil do trigger: base={trigger_user.get('base_id')} "
              f"region={trigger_user.get('region_id')} state={trigger_user.get('state_id')} "
              f"state(permuta/liberado)={trigger_user.get('state', 'permuta')}")

    # 1. Captura o estado ATUAL dos matches do usuário antes de qualquer alteração
    t1 = time.perf_counter()
    old_matches = await db.get_user_matches(r, trigger_username)
    old_chains = {}
    for m in old_matches:
        usernames = [step["username"] for step in m.get("chain", [])]
        key = "|".join(sorted(usernames))
        old_chains[key] = m["id"]
    log.info(f"[RECALC] [⏱ {time.perf_counter()-t1:.3f}s] "
             f"matches pré-existentes: {len(old_chains)} → {list(old_chains.keys())}")

    # 2. Busca usuários relacionados para reavaliação
    t2 = time.perf_counter()
    related_usernames = await _find_related_users(r, trigger_username, trigger_user)
    related_usernames.add(trigger_username)
    log.info(f"[RECALC] [⏱ {time.perf_counter()-t2:.3f}s] "
             f"usuários relacionados ({len(related_usernames)}): {sorted(related_usernames)}")

    # 3. Roda a busca em grafos APENAS acumulando os resultados em memória
    t3 = time.perf_counter()
    new_chains_found = []
    total_interests_evaluated = 0
    total_cycles_per_user = {}

    for username in related_usernames:
        t_user = time.perf_counter()
        user = await db.get_user(r, username)
        if not user:
            log.debug(f"[RECALC] '{username}' não encontrado no banco, pulando")
            continue
        interests = await db.get_user_interests(r, username)
        log.debug(f"[RECALC] '{username}' tem {len(interests)} interesse(s)")

        user_cycles = 0
        for interest in interests:
            total_interests_evaluated += 1
            cycles = await _try_close_cycles(r, username, user, interest)
            if cycles:
                log.debug(f"[RECALC] '{username}' → ciclos encontrados via interesse "
                          f"{interest.get('id','?')}: {cycles}")
            user_cycles += len(cycles)
            new_chains_found.extend(cycles)

        total_cycles_per_user[username] = user_cycles
        log.debug(f"[RECALC] [⏱ {time.perf_counter()-t_user:.3f}s] "
                  f"'{username}' — interesses avaliados={len(interests)}, ciclos={user_cycles}")

    log.info(f"[RECALC] [⏱ {time.perf_counter()-t3:.3f}s] etapa DFS concluída — "
             f"usuários processados={len(related_usernames)}, "
             f"interesses avaliados={total_interests_evaluated}, "
             f"ciclos brutos={len(new_chains_found)} | "
             f"ciclos por usuário={total_cycles_per_user}")
    log.debug(f"[RECALC] ciclos brutos detalhados: {new_chains_found}")

    # 4. Mapeia os novos ciclos válidos encontrados
    t4 = time.perf_counter()
    valid_chain_keys = set()
    chains_to_save = {}
    for chain in new_chains_found:
        key = "|".join(sorted(chain))
        valid_chain_keys.add(key)
        chains_to_save[key] = chain

    old_keys = set(old_chains.keys())
    log.info(f"[RECALC] [⏱ {time.perf_counter()-t4:.4f}s] "
             f"dedup — ciclos brutos={len(new_chains_found)}, "
             f"únicos={len(valid_chain_keys)} → {sorted(valid_chain_keys)}")

    # 5. Exclui APENAS os matches antigos que o usuário participava e que não foram revalidados
    t5 = time.perf_counter()
    keys_to_delete = old_keys - valid_chain_keys
    if keys_to_delete:
        log.info(f"[RECALC] removendo {len(keys_to_delete)} match(es) obsoleto(s): {keys_to_delete}")
    for k in keys_to_delete:
        log.debug(f"[RECALC] deletando match id={old_chains[k]} (chain key: {k})")
        await db.delete_match(r, old_chains[k])
    log.info(f"[RECALC] [⏱ {time.perf_counter()-t5:.3f}s] deleções concluídas — removidos={len(keys_to_delete)}")

    # 6. Salva as combinações novas
    t6 = time.perf_counter()
    new_saved = 0
    for k in valid_chain_keys:
        saved = await _close_match(r, chains_to_save[k])
        if saved:
            new_saved += 1
    log.info(f"[RECALC] [⏱ {time.perf_counter()-t6:.3f}s] salvamento concluído — "
             f"novos={new_saved}, já existiam={len(valid_chain_keys) - new_saved}")

    # ── Resumo de tempos ──────────────────────────────────────────────────────
    m = db.get_metrics()
    log.info(
        f"[RECALC] ◀ concluído para '{trigger_username}' — "
        f"novos={new_saved}, removidos={len(keys_to_delete)}, mantidos={len(valid_chain_keys) - new_saved} | "
        f"[DB] {m['calls']} chamadas · db={m['db_ms']} ms · "      # ← tempo puro de I/O Redis
        f"proc={m['proc_ms']} ms · "                                # ← tempo de CPU/lógica
        f"wall={m['wall_ms']} ms"                                   # ← tempo total real
    )


async def _find_related_users(r, trigger_username: str, trigger_user: dict) -> set:
    t0 = time.perf_counter()
    related = set()

    t_fetch = time.perf_counter()
    all_interests = await db.get_all_interests(r)
    trigger_interests = await db.get_user_interests(r, trigger_username)
    log.debug(f"[RELATED] [⏱ {time.perf_counter()-t_fetch:.3f}s] "
              f"fetch — all_interests={len(all_interests)}, trigger_interests={len(trigger_interests)}")

    t_base   = str(trigger_user.get("base_id",   "0"))
    t_region = str(trigger_user.get("region_id", "0"))
    t_state  = str(trigger_user.get("state_id",  "0"))

    t_targets_base   = {str(i.get("target_base_id",   "0")) for i in trigger_interests} - {"0"}
    t_targets_region = {str(i.get("target_region_id", "0")) for i in trigger_interests} - {"0"}
    t_targets_state  = {str(i.get("target_state_id",  "0")) for i in trigger_interests} - {"0"}

    log.debug(f"[RELATED] trigger base={t_base} region={t_region} state={t_state}")
    log.debug(f"[RELATED] trigger quer ir para → bases={t_targets_base} regiões={t_targets_region} estados={t_targets_state}")

    iters = 0
    db_lookups = 0
    added_rule1 = 0
    added_rule2 = 0

    for interest in all_interests:
        iters += 1
        uname = interest.get("username")
        if not uname or uname == trigger_username:
            continue

        i_base   = str(interest.get("target_base_id",   "0"))
        i_region = str(interest.get("target_region_id", "0"))
        i_state  = str(interest.get("target_state_id",  "0"))

        # Regra 1: este usuário quer ir para onde o trigger está?
        if (i_base   != "0" and i_base   == t_base)   or \
           (i_region != "0" and i_region == t_region) or \
           (i_state  != "0" and i_state  == t_state):
            log.debug(f"[RELATED] '{uname}' adicionado — quer ir para onde trigger está")
            related.add(uname)
            added_rule1 += 1
            continue

        # Regra 2: o trigger quer ir para onde este usuário está?
        other_user = await db.get_user(r, uname)
        db_lookups += 1
        if other_user:
            o_base   = str(other_user.get("base_id",   "0"))
            o_region = str(other_user.get("region_id", "0"))
            o_state  = str(other_user.get("state_id",  "0"))

            if (o_base   != "0" and o_base   in t_targets_base)   or \
               (o_region != "0" and o_region in t_targets_region) or \
               (o_state  != "0" and o_state  in t_targets_state):
                log.debug(f"[RELATED] '{uname}' adicionado — trigger quer ir para onde ele está")
                related.add(uname)
                added_rule2 += 1

    log.info(f"[RELATED] [⏱ {time.perf_counter()-t0:.3f}s] "
             f"iterações={iters}, db_lookups(regra2)={db_lookups}, "
             f"adicionados(regra1)={added_rule1}, adicionados(regra2)={added_rule2}, "
             f"total={len(related)} → {sorted(related)}")
    return related


async def _try_close_cycles(r, origin_username: str, origin_user: dict, interest: dict) -> list:
    t0 = time.perf_counter()
    found_cycles = []
    origin_base = origin_user.get("base_id", "0")

    candidates = await _get_candidates(r, origin_user, interest)
    candidates.discard(origin_username)

    log.debug(f"[DFS] '{origin_username}' (base={origin_base}) | interesse={interest.get('id','?')} "
              f"→ target_base={interest.get('target_base_id','0')} "
              f"target_region={interest.get('target_region_id','0')} "
              f"target_state={interest.get('target_state_id','0')} "
              f"| candidatos ({len(candidates)}): {sorted(candidates)}")

    dfs_calls = 0
    for candidate in candidates:
        dfs_calls += 1
        chain = await _dfs_find_cycle(
            r,
            start_username=origin_username,
            start_base=origin_base,
            current=candidate,
            path=[origin_username],
            max_depth=4,
        )
        if chain:
            log.info(f"[DFS] ✓ ciclo fechado: {chain}")
            found_cycles.append(chain)
        else:
            log.debug(f"[DFS] ✗ sem ciclo via candidato '{candidate}' partindo de '{origin_username}'")

    log.debug(f"[TRY_CYCLES] [⏱ {time.perf_counter()-t0:.3f}s] "
              f"interesse={interest.get('id','?')}, candidatos={len(candidates)}, "
              f"chamadas_dfs={dfs_calls}, ciclos={len(found_cycles)}")
    return found_cycles


# ─── Candidatos via índices Redis ─────────────────────────────────────────────

async def _get_candidates(r, user: dict, interest: dict) -> set:
    t0 = time.perf_counter()
    target_base   = str(interest.get("target_base_id",   "0"))
    target_region = str(interest.get("target_region_id", "0"))
    target_state  = str(interest.get("target_state_id",  "0"))

    loc_keys = []
    if target_base   != "0": loc_keys.append(f"index:location:{target_base}:users")
    if target_region != "0": loc_keys.append(f"index:region:{target_region}:users")
    if target_state  != "0": loc_keys.append(f"index:state:{target_state}:users")

    if loc_keys:
        geo_sets = await asyncio.gather(*[r.smembers(k) for k in loc_keys])
        geo_candidates = set().union(*geo_sets)
    else:
        geo_candidates = set(await r.smembers("index:all:users"))

    log.debug(f"[CANDIDATES] [⏱ {time.perf_counter()-t0:.3f}s] "
              f"geo_keys={loc_keys} → {len(geo_candidates)} candidato(s) geográfico(s)")

    extra_keys = []
    if str(interest.get("target_role_id",       "0")) != "0":
        extra_keys.append(f"index:role:{interest['target_role_id']}:users")
    if str(interest.get("target_role_type_id",  "0")) != "0":
        extra_keys.append(f"index:role_type:{interest['target_role_type_id']}:users")
    if str(interest.get("target_department_id", "0")) != "0":
        extra_keys.append(f"index:department:{interest['target_department_id']}:users")
    if str(interest.get("target_regime_id",     "0")) != "0":
        extra_keys.append(f"index:regime:{interest['target_regime_id']}:users")

    if not extra_keys:
        return geo_candidates

    profile_sets = await asyncio.gather(*[r.smembers(k) for k in extra_keys])
    profile_candidates = profile_sets[0]
    for s in profile_sets[1:]:
        profile_candidates = profile_candidates & s

    final = geo_candidates & profile_candidates
    log.debug(f"[CANDIDATES] [⏱ {time.perf_counter()-t0:.3f}s] "
              f"profile_keys={extra_keys} → geo={len(geo_candidates)}, "
              f"perfil={len(profile_candidates)}, final={len(final)}")
    return final


def _interest_matches_user(interest: dict, user: dict) -> bool:
    t_base   = str(interest.get("target_base_id",   "0"))
    t_region = str(interest.get("target_region_id", "0"))
    t_state  = str(interest.get("target_state_id",  "0"))

    u_base   = str(user.get("base_id",   "0"))
    u_region = str(user.get("region_id", "0"))
    u_state  = str(user.get("state_id",  "0"))

    no_geo = t_base == "0" and t_region == "0" and t_state == "0"

    if not no_geo:
        loc_match = (
            (t_base   != "0" and t_base   == u_base)   or
            (t_region != "0" and t_region == u_region) or
            (t_state  != "0" and t_state  == u_state)
        )
        if not loc_match:
            log.debug(f"[MATCH_CHECK] reprovado na localização: "
                      f"interest(base={t_base},region={t_region},state={t_state}) "
                      f"vs user(base={u_base},region={u_region},state={u_state})")
            return False

    t_dept   = str(interest.get("target_department_id", "0"))
    t_regime = str(interest.get("target_regime_id",     "0"))

    if t_dept != "0" and t_dept != str(user.get("department_id", "0")):
        log.debug(f"[MATCH_CHECK] reprovado no departamento: interesse={t_dept} vs user={user.get('department_id')}")
        return False
    if t_regime != "0" and t_regime != str(user.get("regime_id", "0")):
        log.debug(f"[MATCH_CHECK] reprovado no regime: interesse={t_regime} vs user={user.get('regime_id')}")
        return False

    t_role      = str(interest.get("target_role_id",      "0"))
    t_role_type = str(interest.get("target_role_type_id", "0"))

    if t_role      != "0" and t_role      != str(user.get("role_id",      "0")): return False
    if t_role_type != "0" and t_role_type != str(user.get("role_type_id", "0")): return False

    return True


# ─── DFS ──────────────────────────────────────────────────────────────────────

async def _dfs_find_cycle(r, start_username, start_base, current, path, max_depth, _depth=0) -> list | None:
    if len(path) >= max_depth:
        log.debug(f"[DFS] profundidade máxima atingida em path={path + [current]}")
        return None

    current_user = await db.get_user(r, current)
    if not current_user:
        log.debug(f"[DFS] '{current}' não encontrado no banco")
        return None

    current_interests = await db.get_user_interests(r, current)
    if not current_interests:
        log.debug(f"[DFS] '{current}' sem interesses, caminho morto")
        return None

    new_path = path + [current]

    start_user  = await db.get_user(r, start_username)
    start_state = start_user.get("state", "permuta") if start_user else "permuta"

    if start_state == "permuta" and start_user:
        matching = [i for i in current_interests if _interest_matches_user(i, start_user)]
        if matching:
            log.debug(f"[DFS] '{current}' fecha ciclo com '{start_username}' via interesse(s): "
                      f"{[i.get('id','?') for i in matching]} | path={new_path}")
            if len(new_path) >= 2:
                return new_path
        else:
            log.debug(f"[DFS] '{current}' não fecha ciclo com '{start_username}' (nenhum interesse compatível)")
    elif start_state == "liberado":
        log.debug(f"[DFS] '{start_username}' é liberado — ciclo não pode ser fechado por ele")

    # Continua DFS
    t_cands = time.perf_counter()
    next_candidates = set()
    for interest in current_interests:
        next_candidates.update(await _get_candidates(r, current_user, interest))
    next_candidates -= set(new_path)
    log.debug(f"[DFS] [⏱ {time.perf_counter()-t_cands:.3f}s] "
              f"candidatos para '{current}' (depth={_depth}): {len(next_candidates)} → {sorted(next_candidates)}")

    for nxt in next_candidates:
        result = await _dfs_find_cycle(r, start_username, start_base, nxt, new_path, max_depth, _depth + 1)
        if result:
            return result

    return None


def _targets_base(interest: dict, base_id: str) -> bool:
    t = str(interest.get("target_base_id", "0"))
    return t == "0" or t == base_id


# ─── Fechar ciclo ─────────────────────────────────────────────────────────────

async def _close_match(r, chain: list) -> bool:
    t0 = time.perf_counter()
    users = await asyncio.gather(*[db.get_user(r, key) for key in chain])

    chain_data = [
        {
            "username": key,
            "base_id":  user.get("base_id", ""),
            "state":    user.get("state", "permuta"),
        }
        for key, user in zip(chain, users) if user
    ]

    if len(chain_data) < 2:
        log.warning(f"[CLOSE] chain_data insuficiente para salvar: {chain_data}")
        return False

    chain_usernames = [s["username"] for s in chain_data]

    t_exists = time.perf_counter()
    exists = await db.match_exists_for_chain(r, chain_usernames)
    log.debug(f"[CLOSE] [⏱ {time.perf_counter()-t_exists:.3f}s] match_exists check para {chain_usernames}")

    if exists:
        log.info(f"[CLOSE] match já existe para {chain_usernames}, pulando")
        return False

    t_save = time.perf_counter()
    match_id = await db.save_match(r, chain_usernames, chain_data)
    log.info(f"[CLOSE] [⏱ {time.perf_counter()-t_save:.3f}s] ✓ novo match salvo: id={match_id} → {chain_usernames}")

    for i in range(len(chain_data)):
        frm = chain_data[i]["base_id"]
        to  = chain_data[(i + 1) % len(chain_data)]["base_id"]
        if frm and to:
            await db.increment_arc(r, frm, to)

    # asyncio.create_task(notify_match(match={"id": match_id, "chain": chain_data}, users=[u for u in users if u]))
    return True
