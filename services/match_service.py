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
    trigger_user = await db.get_user(r, trigger_username)
    if not trigger_user:
        return

    # 1. Captura o estado ATUAL dos matches do usuário antes de qualquer alteração
    old_matches = await db.get_user_matches(r, trigger_username)
    old_chains = {}
    for m in old_matches:
        usernames = [step["username"] for step in m.get("chain", [])]
        key = "|".join(sorted(usernames))
        old_chains[key] = m["id"]

    # 2. Busca usuários relacionados para reavaliação
    related_usernames = await _find_related_users(r, trigger_username, trigger_user)
    related_usernames.add(trigger_username)

    log.info(f"recalculate: {trigger_username} → avaliando {len(related_usernames)} usuários")

    # 3. Roda a busca em grafos APENAS acumulando os resultados em memória
    new_chains_found = []
    for username in related_usernames:
        user = await db.get_user(r, username)
        if not user:
            continue
        interests = await db.get_user_interests(r, username)
        for interest in interests:
            cycles = await _try_close_cycles(r, username, user, interest)
            new_chains_found.extend(cycles)

    # 4. Mapeia os novos ciclos válidos encontrados
    valid_chain_keys = set()
    chains_to_save = {}
    for chain in new_chains_found:
        key = "|".join(sorted(chain))
        valid_chain_keys.add(key)
        chains_to_save[key] = chain

    old_keys = set(old_chains.keys())

    # 5. Exclui APENAS os matches antigos que o usuário participava e que não foram revalidados
    keys_to_delete = old_keys - valid_chain_keys
    for k in keys_to_delete:
        await db.delete_match(r, old_chains[k])

    # 6. Salva as combinações. A _close_match verifica duplicatas com o banco, 
    # garantindo que o e-mail só dispare para novos arranjos de triangulação.
    for k in valid_chain_keys:
        await _close_match(r, chains_to_save[k])


async def _find_related_users(r, trigger_username: str, trigger_user: dict) -> set:
    related = set()
    all_interests = await db.get_all_interests(r)
    trigger_interests = await db.get_user_interests(r, trigger_username)

    # Localidade atual do usuário trigger
    t_base = str(trigger_user.get("base_id", "0"))
    t_region = str(trigger_user.get("region_id", "0"))
    t_state = str(trigger_user.get("state_id", "0"))

    # Alvos dos interesses do usuário trigger
    t_targets_base = {str(i.get("target_base_id", "0")) for i in trigger_interests} - {"0"}
    t_targets_region = {str(i.get("target_region_id", "0")) for i in trigger_interests} - {"0"}
    t_targets_state = {str(i.get("target_state_id", "0")) for i in trigger_interests} - {"0"}

    for interest in all_interests:
        uname = interest.get("username")
        if not uname or uname == trigger_username:
            continue

        # 1. Este usuário quer ir para a base/região/estado do trigger?
        i_base = str(interest.get("target_base_id", "0"))
        i_region = str(interest.get("target_region_id", "0"))
        i_state = str(interest.get("target_state_id", "0"))

        if (i_base != "0" and i_base == t_base) or \
           (i_region != "0" and i_region == t_region) or \
           (i_state != "0" and i_state == t_state):
            related.add(uname)
            continue

        # 2. O trigger quer ir para a base/região/estado deste usuário?
        other_user = await db.get_user(r, uname)
        if other_user:
            o_base = str(other_user.get("base_id", "0"))
            o_region = str(other_user.get("region_id", "0"))
            o_state = str(other_user.get("state_id", "0"))

            if (o_base != "0" and o_base in t_targets_base) or \
               (o_region != "0" and o_region in t_targets_region) or \
               (o_state != "0" and o_state in t_targets_state):
                related.add(uname)

    return related

async def _try_close_cycles(r, origin_username: str, origin_user: dict, interest: dict) -> list:
    """
    Para um interesse específico, busca candidatos e retorna os ciclos fechados em memória.
    """
    found_cycles = []
    origin_base = origin_user.get("base_id", "0")

    candidates = await _get_candidates(r, origin_user, interest)
    candidates.discard(origin_username)

    for candidate in candidates:
        # Importante: Qualquer verificação no banco (db.match_exists_for_chain) foi 
        # removida daqui de dentro, pois impedia o algoritmo de mapear o grafo completo.
        chain = await _dfs_find_cycle(
            r,
            start_username=origin_username,
            start_base=origin_base,
            current=candidate,
            path=[origin_username],
            max_depth=4,
        )
        if chain:
            found_cycles.append(chain)
            
    return found_cycles


# ─── Candidatos via SINTER ────────────────────────────────────────────────────

async def _get_candidates(r, user: dict, interest: dict) -> set:
    """
    Retorna usuários que estão na localidade alvo do interesse.
    """
    loc_keys = []
    target_base   = str(interest.get("target_base_id",   "0"))
    target_region = str(interest.get("target_region_id", "0"))
    target_state  = str(interest.get("target_state_id",  "0"))

    if target_base != "0":
        loc_keys.append(f"index:location:{target_base}:users")
    elif target_region != "0":
        loc_keys.append(f"index:region:{target_region}:users")
    elif target_state != "0":
        loc_keys.append(f"index:state:{target_state}:users")

    extra_keys = []
    if str(interest.get("target_role_id",       "0")) != "0":
        extra_keys.append(f"index:role:{interest['target_role_id']}:users")
    if str(interest.get("target_role_type_id",  "0")) != "0":
        extra_keys.append(f"index:role_type:{interest['target_role_type_id']}:users")
    if str(interest.get("target_department_id", "0")) != "0":
        extra_keys.append(f"index:department:{interest['target_department_id']}:users")
    if str(interest.get("target_regime_id",     "0")) != "0":
        extra_keys.append(f"index:regime:{interest['target_regime_id']}:users")

    all_keys = loc_keys + extra_keys
    if not all_keys:
        return set(await r.smembers("index:all:users"))
    if len(all_keys) == 1:
        return set(await r.smembers(all_keys[0]))
    return set(await r.sinter(*all_keys))

def _interest_matches_user(interest: dict, user: dict) -> bool:
    """Verifica se o interesse satisfaz a localização e o perfil completo do usuário alvo."""
    
    # 1. Validação de Localização
    t_base = str(interest.get("target_base_id", "0"))
    t_region = str(interest.get("target_region_id", "0"))
    t_state = str(interest.get("target_state_id", "0"))
    
    u_base = str(user.get("base_id", "0"))
    u_region = str(user.get("region_id", "0"))
    u_state = str(user.get("state_id", "0"))

    loc_match = False
    if t_base != "0":
        loc_match = (t_base == u_base)
    elif t_region != "0":
        loc_match = (t_region == u_region)
    elif t_state != "0":
        loc_match = (t_state == u_state)
    else:
        loc_match = True # Sem restrição geográfica

    if not loc_match:
        return False

    # 2. Validação de Perfil Profissional (Área, Regime, Cargo)
    t_dept = str(interest.get("target_department_id", "0"))
    t_regime = str(interest.get("target_regime_id", "0"))
    # t_role = str(interest.get("target_role_id", "0"))
    # t_type = str(interest.get("target_role_type_id", "0"))

    if t_dept != "0" and t_dept != str(user.get("department_id", "0")): return False
    if t_regime != "0" and t_regime != str(user.get("regime_id", "0")): return False
    # if t_role != "0" and t_role != str(user.get("role_id", "0")): return False
    # if t_type != "0" and t_type != str(user.get("role_type_id", "0")): return False

    return True


# ─── DFS ──────────────────────────────────────────────────────────────────────

async def _dfs_find_cycle(r, start_username, start_base, current, path, max_depth) -> list | None:
    if len(path) >= max_depth:
        return None

    current_user = await db.get_user(r, current)
    if not current_user:
        return None

    # TRAVA 1: Ninguém pode ocupar a vaga de um usuário 'liberado'.
    # Se o elo atual da cadeia não deixa vaga, a trilha morre aqui.
    if current_user.get("state", "permuta") == "liberado":
        return None

    current_interests = await db.get_user_interests(r, current)
    if not current_interests:
        return None

    new_path = path + [current]

    # Verifica fechamento do ciclo
    start_user = await db.get_user(r, start_username)
    start_state = start_user.get("state", "permuta") if start_user else "permuta"
    
    cycle_closes = False
    # TRAVA 2: O ciclo SÓ fecha se o usuário que iniciou a busca FOR 'permuta'.
    # Se o start_user for 'liberado', ele não abre o espaço necessário para abrigar o último da cadeia.
    if start_state == "permuta" and start_user and any(_interest_matches_user(i, start_user) for i in current_interests):
        cycle_closes = True

    if cycle_closes and len(new_path) >= 2:
        return new_path

    # Continua DFS
    next_candidates = set()
    for interest in current_interests:
        next_candidates.update(await _get_candidates(r, current_user, interest))
    next_candidates -= set(new_path)

    for nxt in next_candidates:
        result = await _dfs_find_cycle(r, start_username, start_base, nxt, new_path, max_depth)
        if result:
            return result

    return None


def _targets_base(interest: dict, base_id: str) -> bool:
    t = str(interest.get("target_base_id", "0"))
    return t == "0" or t == base_id


# ─── Fechar ciclo ─────────────────────────────────────────────────────────────

async def _close_match(r, chain: list):
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
        return

    # Checa dedup antes de salvar
    chain_usernames = [s["username"] for s in chain_data]
    if await db.match_exists_for_chain(r, chain_usernames):
        log.info(f"Match já existe para {chain_usernames}, pulando")
        return

    match_id = await db.save_match(r, chain_usernames, chain_data)
    log.info(f"Match salvo: {match_id} → {chain_usernames}")

    for i in range(len(chain_data)):
        frm = chain_data[i]["base_id"]
        to  = chain_data[(i + 1) % len(chain_data)]["base_id"]
        if frm and to:
            await db.increment_arc(r, frm, to)

    asyncio.create_task(notify_match(r, {"id": match_id, "chain": chain_data}, [u for u in users if u]))