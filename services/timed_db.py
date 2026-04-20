"""
timed_db.py — Proxy de instrumentação para redis_service.

Uso:
    from services import timed_db as db   # substitui 'redis_service as db'

Cada chamada ao banco é medida individualmente e emite:
    [DB] get_user('alice') → 1.23 ms
    [DB] get_user_interests('alice') → 0.87 ms

No final de cada recalculate_matches_for_user há um resumo:
    [DB SUMMARY] 14 chamadas | total_db=18.4 ms | total_processing=312.1 ms | wall=330.5 ms
"""

import asyncio
import time
import logging
import functools
from services import redis_service as _db

log = logging.getLogger(__name__)

# ─── Contexto de métricas por "sessão de recálculo" ──────────────────────────
# Usa contextvariable para ser seguro em cenários com múltiplas corrotinas concorrentes.
from contextvars import ContextVar

_db_time:   ContextVar[float] = ContextVar("_db_time",   default=0.0)
_db_calls:  ContextVar[int]   = ContextVar("_db_calls",  default=0)
_wall_start: ContextVar[float] = ContextVar("_wall_start", default=0.0)


def reset_metrics():
    """Chame no início de cada recalculate_matches_for_user."""
    _db_time.set(0.0)
    _db_calls.set(0)
    _wall_start.set(time.perf_counter())


def get_metrics() -> dict:
    wall = time.perf_counter() - _wall_start.get()
    db_t = _db_time.get()
    return {
        "calls":      _db_calls.get(),
        "db_ms":      round(db_t * 1000, 2),
        "proc_ms":    round((wall - db_t) * 1000, 2),
        "wall_ms":    round(wall * 1000, 2),
    }


# ─── Gerador automático de wrappers ──────────────────────────────────────────

def _make_timed(fn_name: str):
    """Cria um wrapper async que mede o tempo de qualquer função do redis_service."""
    original = getattr(_db, fn_name)

    @functools.wraps(original)
    async def wrapper(*args, **kwargs):
        # Monta label legível ignorando o objeto 'r' (primeiro argumento sempre)
        label_args = ", ".join(
            repr(a) for a in args[1:]   # args[0] é o cliente redis
        )
        t0 = time.perf_counter()
        result = await original(*args, **kwargs)
        elapsed = time.perf_counter() - t0

        # Acumula métricas
        _db_time.set(_db_time.get() + elapsed)
        _db_calls.set(_db_calls.get() + 1)

        log.debug(f"[DB] {fn_name}({label_args}) → {elapsed * 1000:.2f} ms")
        return result

    return wrapper


# ─── Exposição dos símbolos do redis_service, com instrumentação ──────────────
# Funções async instrumentadas:
get_user               = _make_timed("get_user")
get_user_matches       = _make_timed("get_user_matches")
get_user_interests     = _make_timed("get_user_interests")
get_all_interests      = _make_timed("get_all_interests")
match_exists_for_chain = _make_timed("match_exists_for_chain")
save_match             = _make_timed("save_match")
delete_match           = _make_timed("delete_match")
increment_arc          = _make_timed("increment_arc")

# Funções/atributos não-async repassados diretamente (se existirem no módulo original):
def __getattr__(name: str):
    return getattr(_db, name)