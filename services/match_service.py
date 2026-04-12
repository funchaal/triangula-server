"""
Algoritmo de Triangulação — Recálculo Inteligente

Estado do usuário:
  - state='permuta':  precisa de alguém que vá para o lugar dele para fechar ciclo
  - state='liberado': não precisa de ninguém indo para o lugar dele
                      (ele "sai de graça", então pode fechar ciclo sem contrapartida para sua base)

Recálculo inteligente:
  Dado um gatilho (novo interesse, interesse removido, perfil atualizado),
  identifica apenas os interesses com relação de origem/destino com o gatilho
  e reavalia só elas — não varre o sistema inteiro.
"""
import asyncio
import logging
from services import redis_service as db
from services.notification_service import notify_match

log = logging.getLogger(__name__)


# ─── Entrada principal ────────────────────────────────────────────────────────

async def recalculate_matches_for_user(r, trigger_username: str):
    log.info(f"[RECALC] ▶ iniciando para '{trigger_username}'")

    trigger_user = await db.get_user(r, trigger_username)
    if not trigger_user:
        log.warning(f"[RECALC] usuário '{trigger_username}' não encontrado, abortando")
        return

    log.debug(f"[RECALC] perfil do trigger: base={trigger_user.get('base_id')} "
              f"region={trigger_user.get('region_id')} state={trigger_user.get('state_id')} "
              f"state(permuta/liberado)={trigger_user.get('state', 'permuta')}")

    # 1. Captura o estado ATUAL dos matches do usuário antes de qualquer alteração
    old_matches = await db.get_user_matches(r, trigger_username)
    old_chains = {}
    for m in old_matches:
        usernames = [step["username"] for step in m.get("chain", [])]
        key = "|".join(sorted(usernames))
        old_chains[key] = m["id"]
    log.info(f"[RECALC] matches pré-existentes: {len(old_chains)} → {list(old_chains.keys())}")

    # 2. Busca usuários relacionados para reavaliação
    related_usernames = await _find_related_users(r, trigger_username, trigger_user)
    related_usernames.add(trigger_username)
    log.info(f"[RECALC] usuários relacionados ({len(related_usernames)}): {sorted(related_usernames)}")

    # 3. Roda a busca em grafos APENAS acumulando os resultados em memória
    new_chains_found = []
    for username in related_usernames:
        user = await db.get_user(r, username)
        if not user:
            log.debug(f"[RECALC] '{username}' não encontrado no banco, pulando")
            continue
        interests = await db.get_user_interests(r, username)
        log.debug(f"[RECALC] '{username}' tem {len(interests)} interesse(s)")
        for interest in interests:
            cycles = await _try_close_cycles(r, username, user, interest)
            if cycles:
                log.debug(f"[RECALC] '{username}' → ciclos encontrados via interesse {interest.get('id','?')}: {cycles}")
            new_chains_found.extend(cycles)

    log.info(f"[RECALC] total de ciclos brutos encontrados: {len(new_chains_found)} → {new_chains_found}")

    # 4. Mapeia os novos ciclos válidos encontrados
    valid_chain_keys = set()
    chains_to_save = {}
    for chain in new_chains_found:
        key = "|".join(sorted(chain))
        valid_chain_keys.add(key)
        chains_to_save[key] = chain

    old_keys = set(old_chains.keys())
    log.info(f"[RECALC] ciclos válidos (dedup): {len(valid_chain_keys)} → {sorted(valid_chain_keys)}")

    # 5. Exclui APENAS os matches antigos que o usuário participava e que não foram revalidados
    keys_to_delete = old_keys - valid_chain_keys
    if keys_to_delete:
        log.info(f"[RECALC] removendo {len(keys_to_delete)} match(es) obsoleto(s): {keys_to_delete}")
    for k in keys_to_delete:
        log.debug(f"[RECALC] deletando match id={old_chains[k]} (chain key: {k})")
        await db.delete_match(r, old_chains[k])

    # 6. Salva as combinações. A _close_match verifica duplicatas com o banco,
    # garantindo que o e-mail só dispare para novos arranjos de triangulação.
    new_saved = 0
    for k in valid_chain_keys:
        saved = await _close_match(r, chains_to_save[k])
        if saved:
            new_saved += 1

    log.info(f"[RECALC] ◀ concluído para '{trigger_username}' — "
             f"novos={new_saved}, removidos={len(keys_to_delete)}, mantidos={len(valid_chain_keys) - new_saved}")


async def _find_related_users(r, trigger_username: str, trigger_user: dict) -> set:
    related = set()
    all_interests = await db.get_all_interests(r)
    trigger_interests = await db.get_user_interests(r, trigger_username)

    # Localidade atual do usuário trigger
    t_base   = str(trigger_user.get("base_id",   "0"))
    t_region = str(trigger_user.get("region_id", "0"))
    t_state  = str(trigger_user.get("state_id",  "0"))

    # Alvos dos interesses do usuário trigger
    t_targets_base   = {str(i.get("target_base_id",   "0")) for i in trigger_interests} - {"0"}
    t_targets_region = {str(i.get("target_region_id", "0")) for i in trigger_interests} - {"0"}
    t_targets_state  = {str(i.get("target_state_id",  "0")) for i in trigger_interests} - {"0"}

    log.debug(f"[RELATED] trigger base={t_base} region={t_region} state={t_state}")
    log.debug(f"[RELATED] trigger quer ir para → bases={t_targets_base} regiões={t_targets_region} estados={t_targets_state}")

    for interest in all_interests:
        uname = interest.get("username")
        if not uname or uname == trigger_username:
            continue

        i_base   = str(interest.get("target_base_id",   "0"))
        i_region = str(interest.get("target_region_id", "0"))
        i_state  = str(interest.get("target_state_id",  "0"))

        # 1. Este usuário quer ir para a base/região/estado do trigger?
        if (i_base   != "0" and i_base   == t_base)   or \
           (i_region != "0" and i_region == t_region) or \
           (i_state  != "0" and i_state  == t_state):
            log.debug(f"[RELATED] '{uname}' adicionado — quer ir para onde trigger está")
            related.add(uname)
            continue

        # 2. O trigger quer ir para a base/região/estado deste usuário?
        other_user = await db.get_user(r, uname)
        if other_user:
            o_base   = str(other_user.get("base_id",   "0"))
            o_region = str(other_user.get("region_id", "0"))
            o_state  = str(other_user.get("state_id",  "0"))

            if (o_base   != "0" and o_base   in t_targets_base)   or \
               (o_region != "0" and o_region in t_targets_region) or \
               (o_state  != "0" and o_state  in t_targets_state):
                log.debug(f"[RELATED] '{uname}' adicionado — trigger quer ir para onde ele está")
                related.add(uname)

    log.info(f"[RELATED] {len(related)} usuário(s) relacionado(s) encontrado(s): {sorted(related)}")
    return related


async def _try_close_cycles(r, origin_username: str, origin_user: dict, interest: dict) -> list:
    """
    Para um interesse específico, busca candidatos e retorna os ciclos fechados em memória.
    """
    found_cycles = []
    origin_base = origin_user.get("base_id", "0")

    candidates = await _get_candidates(r, origin_user, interest)
    candidates.discard(origin_username)

    log.debug(f"[DFS] '{origin_username}' (base={origin_base}) | interesse={interest.get('id','?')} "
              f"→ target_base={interest.get('target_base_id','0')} "
              f"target_region={interest.get('target_region_id','0')} "
              f"target_state={interest.get('target_state_id','0')} "
              f"| candidatos ({len(candidates)}): {sorted(candidates)}")

    for candidate in candidates:
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

    return found_cycles


# ─── Candidatos via índices Redis ─────────────────────────────────────────────

async def _get_candidates(r, user: dict, interest: dict) -> set:
    """
    Retorna usuários que estão na localidade alvo do interesse.
    União dos índices geográficos (base OR região OR estado), depois interseção com perfil.
    """
    target_base   = str(interest.get("target_base_id",   "0"))
    target_region = str(interest.get("target_region_id", "0"))
    target_state  = str(interest.get("target_state_id",  "0"))

    loc_keys = []
    if target_base   != "0": loc_keys.append(f"index:location:{target_base}:users")
    if target_region != "0": loc_keys.append(f"index:region:{target_region}:users")
    if target_state  != "0": loc_keys.append(f"index:state:{target_state}:users")

    # União dos geográficos (qualquer nível satisfaz)
    if loc_keys:
        geo_sets = await asyncio.gather(*[r.smembers(k) for k in loc_keys])
        geo_candidates = set().union(*geo_sets)
    else:
        geo_candidates = set(await r.smembers("index:all:users"))

    log.debug(f"[CANDIDATES] geo_keys={loc_keys} → {len(geo_candidates)} candidato(s) geográfico(s)")

    # Interseção com filtros de perfil (todos devem casar)
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
    log.debug(f"[CANDIDATES] profile_keys={extra_keys} → {len(profile_candidates)} perfil | final={len(final)}")
    return final


def _interest_matches_user(interest: dict, user: dict) -> bool:
    """Verifica se o interesse satisfaz a localização e o perfil completo do usuário alvo."""

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

    return True


# ─── DFS ──────────────────────────────────────────────────────────────────────

async def _dfs_find_cycle(r, start_username, start_base, current, path, max_depth) -> list | None:
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

    # Verifica fechamento do ciclo
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
    next_candidates = set()
    for interest in current_interests:
        next_candidates.update(await _get_candidates(r, current_user, interest))
    next_candidates -= set(new_path)

    log.debug(f"[DFS] expandindo de '{current}' | path={new_path} | próximos={sorted(next_candidates)}")

    for nxt in next_candidates:
        result = await _dfs_find_cycle(r, start_username, start_base, nxt, new_path, max_depth)
        if result:
            return result

    return None


def _targets_base(interest: dict, base_id: str) -> bool:
    t = str(interest.get("target_base_id", "0"))
    return t == "0" or t == base_id


# ─── Fechar ciclo ─────────────────────────────────────────────────────────────

async def _close_match(r, chain: list) -> bool:
    """Salva o match se ainda não existe. Retorna True se foi um match novo."""
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

    if await db.match_exists_for_chain(r, chain_usernames):
        log.info(f"[CLOSE] match já existe para {chain_usernames}, pulando")
        return False

    match_id = await db.save_match(r, chain_usernames, chain_data)
    log.info(f"[CLOSE] ✓ novo match salvo: id={match_id} → {chain_usernames}")

    for i in range(len(chain_data)):
        frm = chain_data[i]["base_id"]
        to  = chain_data[(i + 1) % len(chain_data)]["base_id"]
        if frm and to:
            await db.increment_arc(r, frm, to)

    asyncio.create_task(notify_match(r, {"id": match_id, "chain": chain_data}, [u for u in users if u]))
    return True