from functools import lru_cache
from pydantic_settings import BaseSettings
import redis.asyncio as aioredis


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    jwt_secret: str = "dev-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 dias

    resend_api_key: str = ""
    email_from: str = "onboarding@resend.dev"
    bcc_email: str = ""

    frontend_url: str = "https://triangula.vercel.app/"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ─── Conexão Redis (singleton por request via FastAPI Depends) ────────────────

async def get_redis():
    settings = get_settings()
    client = await aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()
