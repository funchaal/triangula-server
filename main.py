import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import admin, public, auth, private

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logging.info("Iniciando Triangula API")

app = FastAPI(title="Triangula API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Ajustar para o domínio do frontend em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(admin.router,  prefix="/api")           # GET  /api/init
app.include_router(public.router,  prefix="/api")           # GET  /api/init
app.include_router(auth.router,    prefix="/api")           # POST /api/auth/*
app.include_router(private.router, prefix="/api")           # PUT  /api/users/me, etc.

@app.get("/")
async def root():
    return "Rafael Funchal é muito lindo! :p"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Triangula API"}
