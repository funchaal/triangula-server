import secrets
import redis.asyncio as aioredis
from datetime import datetime, timedelta
from core.config import get_settings

class TokenService:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.settings = get_settings()
        self.token_expire_minutes = 60  # Token expira em 60 minutos

    async def generate_reset_token(self, email: str) -> str:
        token = secrets.token_urlsafe(32)
        # Armazena o token no Redis com o email associado e um tempo de expiração
        await self.redis.setex(
            f"reset_token:{token}",
            timedelta(minutes=self.token_expire_minutes),
            email
        )
        return token

    async def verify_reset_token(self, token: str) -> str | None:
        email = await self.redis.get(f"reset_token:{token}")
        if email:
            # Invalida o token após o uso para evitar reuso
            await self.redis.delete(f"reset_token:{token}")
            return email.decode('utf-8') # Decodifica o email de bytes para string
        return None
