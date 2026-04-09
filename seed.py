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

# ─── Estados / Bacias Opeacionais ─────────────────────────────────────────────
STATES = {
    "1": {"name": "RJ", "lat": -22.9068, "lng": -43.1729},
    "2": {"name": "SP", "lat": -23.5505, "lng": -46.6333},
    "3": {"name": "MG", "lat": -18.5122, "lng": -44.5550},
    "4": {"name": "RS", "lat": -30.0346, "lng": -51.2177},
    "5": {"name": "PE", "lat": -8.0476,  "lng": -34.8770},
    "6": {"name": "CE", "lat": -3.7172,  "lng": -38.5433},
    "7": {"name": "RN", "lat": -5.7945,  "lng": -36.5667},
    "8": {"name": "PR", "lat": -25.2521, "lng": -52.0215},
    "9": {"name": "ES", "lat": -19.1834, "lng": -40.3089},
    "10": {"name": "BA", "lat": -12.9714, "lng": -38.5014},
    "11": {"name": "AM", "lat": -3.4168,  "lng": -65.8561},
    "12": {"name": "SE", "lat": -10.9472, "lng": -37.0731},
    "13": {"name": "Bacia_Santos", "lat": -25.0000, "lng": -43.0000},
    "14": {"name": "Bacia_Campos", "lat": -22.5000, "lng": -40.0000},
}

# ─── Regiões / Municípios / Polos ─────────────────────────────────────────────
REGIONS = {
    "1": {"name": "Rio de Janeiro", "state_id": "1", "lat": -22.9068, "lng": -43.1729},
    "2": {"name": "Duque de Caxias", "state_id": "1", "lat": -22.7856, "lng": -43.3117},
    "3": {"name": "Angra dos Reis", "state_id": "1", "lat": -23.0067, "lng": -44.3181},
    "4": {"name": "Itaboraí", "state_id": "1", "lat": -22.7444, "lng": -42.8594},
    "5": {"name": "Macaé", "state_id": "1", "lat": -22.3708, "lng": -41.7869},
    "6": {"name": "Paulínia", "state_id": "2", "lat": -22.7615, "lng": -47.1554},
    "7": {"name": "São Sebastião", "state_id": "2", "lat": -23.7605, "lng": -45.4136},
    "8": {"name": "Mauá", "state_id": "2", "lat": -23.6678, "lng": -46.4614},
    "9": {"name": "S. J. dos Campos", "state_id": "2", "lat": -23.2237, "lng": -45.9009},
    "10": {"name": "Betim", "state_id": "3", "lat": -19.9676, "lng": -44.1981},
    "11": {"name": "Canoas", "state_id": "4", "lat": -29.9150, "lng": -51.1795},
    "12": {"name": "Osório", "state_id": "4", "lat": -29.8877, "lng": -50.2709},
    "13": {"name": "Ipojuca", "state_id": "5", "lat": -8.3986, "lng": -35.0594},
    "14": {"name": "Fortaleza", "state_id": "6", "lat": -3.7327, "lng": -38.5270},
    "15": {"name": "Guamaré", "state_id": "7", "lat": -5.1130, "lng": -36.3195},
    "16": {"name": "Mossoró", "state_id": "7", "lat": -5.1888, "lng": -37.3411},
    "17": {"name": "Potiguar/Ubarana", "state_id": "7", "lat": -4.8500, "lng": -36.5200},
    "18": {"name": "Araucária", "state_id": "8", "lat": -25.5936, "lng": -49.4083},
    "19": {"name": "Aracruz", "state_id": "9", "lat": -19.8219, "lng": -40.2736},
    "20": {"name": "Serra", "state_id": "9", "lat": -20.1286, "lng": -40.3078},
    "21": {"name": "Candeias", "state_id": "10", "lat": -12.6711, "lng": -38.4897},
    "22": {"name": "Catu", "state_id": "10", "lat": -12.3533, "lng": -38.3758},
    "23": {"name": "Manaus", "state_id": "11", "lat": -3.1190, "lng": -60.0217},
    "24": {"name": "Carmópolis", "state_id": "12", "lat": -10.6475, "lng": -36.9856},
    "25": {"name": "Tupi", "state_id": "13", "lat": -24.9122, "lng": -42.4455},
    "26": {"name": "Búzios", "state_id": "13", "lat": -24.8150, "lng": -42.5080},
    "27": {"name": "Marlim", "state_id": "14", "lat": -22.3958, "lng": -40.1083},
    "28": {"name": "Peregrino", "state_id": "14", "lat": -23.3172, "lng": -41.2574},
    "29": {"name": "Santos", "state_id": "2", "lat": -23.9312, "lng": -46.3265},
    "30": {"name": "Vitória", "state_id": "9", "lat": -20.3015, "lng": -40.3005},
    "31": {"name": "São João da Barra", "state_id": "1", "lat": -21.6422, "lng": -41.0511},
    "32": {"name": "Caraguatatuba", "state_id": "2", "lat": -23.6219, "lng": -45.4124},
    "33": {"name": "Linhares", "state_id": "9", "lat": -19.3911, "lng": -40.0722},
    "34": {"name": "Coari", "state_id": "11", "lat": -4.0847, "lng": -63.1417},
    "35": {"name": "Niterói", "state_id": "1", "lat": -22.8833, "lng": -43.1036},
}

# ─── Bases (Locations) ────────────────────────────────────────────────────────
LOCATIONS = {
    # Macaé (Bases de Apoio e Logística)
    "PQ_TUBOS_MACAE": {"name": "Parque de Tubos (Imboassica)", "region_id": "5", "state_id": "1", "type": "Onshore", "lat": -22.4182, "lng": -41.8385},
    "BASE_IMBETIBA": {"name": "Base de Imbetiba", "region_id": "5", "state_id": "1", "type": "Onshore", "lat": -22.3803, "lng": -41.7725},

    # Administrativo / Governança (RJ)
    "EDISEN": {"name": "Edifício Senado", "region_id": "1", "state_id": "1", "type": "Onshore", "lat": -22.9111, "lng": -43.1861},
    "EDIHB": {"name": "Edifício Henrique Lage", "region_id": "1", "state_id": "1", "type": "Onshore", "lat": -22.9125, "lng": -43.2243},
    "REP_CHILE": {"name": "Av. República do Chile, 65", "region_id": "1", "state_id": "1", "type": "Onshore", "lat": -22.9094, "lng": -43.1812},
    
    # Refino / Processamento de Gás
    "REDUC": {"name": "REDUC", "region_id": "2", "state_id": "1", "type": "Onshore", "lat": -22.7170, "lng": -43.2750},
    "BOAVENTURA": {"name": "Complexo Boaventura", "region_id": "4", "state_id": "1", "type": "Onshore", "lat": -22.7535, "lng": -42.8592},
    "REPLAN": {"name": "REPLAN", "region_id": "6", "state_id": "2", "type": "Onshore", "lat": -22.7231, "lng": -47.1290},
    "RECAP": {"name": "RECAP", "region_id": "8", "state_id": "2", "type": "Onshore", "lat": -23.6554, "lng": -46.4673},
    "REVAP": {"name": "REVAP", "region_id": "9", "state_id": "2", "type": "Onshore", "lat": -23.2163, "lng": -45.8251},
    "REGAP": {"name": "REGAP", "region_id": "10", "state_id": "3", "type": "Onshore", "lat": -19.9767, "lng": -44.0968},
    "REFAP": {"name": "REFAP", "region_id": "11", "state_id": "4", "type": "Onshore", "lat": -29.8651, "lng": -51.1554},
    "RNEST": {"name": "RNEST", "region_id": "13", "state_id": "5", "type": "Onshore", "lat": -8.3972, "lng": -34.9913},
    "LUBNOR": {"name": "LUBNOR", "region_id": "14", "state_id": "6", "type": "Onshore", "lat": -3.7201, "lng": -38.4752},
    "RPCC": {"name": "RPCC", "region_id": "15", "state_id": "7", "type": "Onshore", "lat": -5.1274, "lng": -36.3802},
    "REPAR": {"name": "REPAR", "region_id": "18", "state_id": "8", "type": "Onshore", "lat": -25.5682, "lng": -49.3753},
    "REMAN": {"name": "REMAN", "region_id": "23", "state_id": "11", "type": "Onshore", "lat": -3.1432, "lng": -59.9451},

    # Terminais (Transpetro)
    "TEBIG": {"name": "TEBIG", "region_id": "3", "state_id": "1", "type": "Onshore", "lat": -23.0531, "lng": -44.2405},
    "TABG": {"name": "TABG", "region_id": "1", "state_id": "1", "type": "Onshore", "lat": -22.8194, "lng": -43.1522},
    "TESS": {"name": "TESS", "region_id": "7", "state_id": "2", "type": "Onshore", "lat": -23.8033, "lng": -45.3883},
    "TEDUT": {"name": "TEDUT", "region_id": "12", "state_id": "4", "type": "Onshore", "lat": -29.9161, "lng": -50.2660},
    "TABR": {"name": "TABR", "region_id": "19", "state_id": "9", "type": "Onshore", "lat": -19.8322, "lng": -40.0551},
    "PORTO_ARATU": {"name": "Porto Aratu", "region_id": "21", "state_id": "10", "type": "Onshore", "lat": -12.7831, "lng": -38.5002},

    # Logística / Armazéns de Materiais (ARMs)
    "ARM_RIO": {"name": "ARM Rio (Cordovil)", "region_id": "1", "state_id": "1", "type": "Onshore", "lat": -22.8252, "lng": -43.2981},
    "ARM_MACAE": {"name": "ARM Macaé", "region_id": "5", "state_id": "1", "type": "Onshore", "lat": -22.4082, "lng": -41.8351},
    "ARM_TIMS": {"name": "ARM TIMS", "region_id": "20", "state_id": "9", "type": "Onshore", "lat": -20.1855, "lng": -40.2654},
    "PQ_TUBOS_MOSSORO": {"name": "Parque de Tubos Mossoró", "region_id": "16", "state_id": "7", "type": "Onshore", "lat": -5.1870, "lng": -37.3430},
    "PQ_TUBOS_CATU": {"name": "Parque de Tubos Catu", "region_id": "22", "state_id": "10", "type": "Onshore", "lat": -12.2030, "lng": -38.5580},

    # Exploração e Produção (E&P) - Terrestre e Marítimo
    "BASE_CARMOPOLIS": {"name": "Base Carmópolis", "region_id": "24", "state_id": "12", "type": "Onshore", "lat": -10.6500, "lng": -36.9800},
    "PLATAFORMA_3R_8": {"name": "Plataforma 3R-8", "region_id": "17", "state_id": "7", "type": "Offshore", "lat": -4.8500, "lng": -36.5200},
    "FPSO_CIDADE_ANGRA": {"name": "FPSO Cidade de Angra", "region_id": "25", "state_id": "13", "type": "Offshore", "lat": -24.9122, "lng": -42.4455},
    "FPSO_ALMIRANTE_BARROSO": {"name": "FPSO Almirante Barroso", "region_id": "26", "state_id": "13", "type": "Offshore", "lat": -24.8150, "lng": -42.5080},
    "FPSO_ANITA_GARIBALDI": {"name": "FPSO Anita Garibaldi", "region_id": "27", "state_id": "14", "type": "Offshore", "lat": -22.3958, "lng": -40.1083},
    "FPSO_PEREGRINO_1": {"name": "FPSO Peregrino 1", "region_id": "28", "state_id": "14", "type": "Offshore", "lat": -23.3172, "lng": -41.2574},

    # ─── Sedes Administrativas e Pesquisa (Adicionais) ────────────────────────
    "EDISA": {"name": "Edifício Valongo (EDISA)", "region_id": "29", "state_id": "2", "type": "Onshore", "lat": -23.9312, "lng": -46.3265},
    "EDIVIT": {"name": "Edifício Sede Vitória (EDIVIT)", "region_id": "30", "state_id": "9", "type": "Onshore", "lat": -20.3015, "lng": -40.3005},
    "CENPES": {"name": "Centro de Pesquisas (CENPES)", "region_id": "1", "state_id": "1", "type": "Onshore", "lat": -22.8624, "lng": -43.2307},

    # ─── Terminais de Processamento de Gás (UPGNs) e Hubs ─────────────────────
    "TECAB": {"name": "Terminal de Cabiúnas", "region_id": "5", "state_id": "1", "type": "Onshore", "lat": -22.2858, "lng": -41.7225},
    "UTGCA": {"name": "UPGN Caraguatatuba (Monteiro Lobato)", "region_id": "32", "state_id": "2", "type": "Onshore", "lat": -23.6547, "lng": -45.4312},
    "UTGC": {"name": "UPGN Cacimbas", "region_id": "33", "state_id": "9", "type": "Onshore", "lat": -19.5750, "lng": -39.9525},

    # ─── Logística de Apoio Offshore e Portos ─────────────────────────────────
    "PORTO_ACU": {"name": "Base de Apoio Porto do Açu", "region_id": "31", "state_id": "1", "type": "Onshore", "lat": -21.8344, "lng": -41.0116},
    "BASE_NITEROI": {"name": "Base Niterói (Ilha da Conceição)", "region_id": "35", "state_id": "1", "type": "Onshore", "lat": -22.8711, "lng": -43.1250},

    # ─── Exploração e Produção Onshore ────────────────────────────────────────
    "BASE_URUCU": {"name": "Polo Arara (Base Urucu)", "region_id": "34", "state_id": "11", "type": "Onshore", "lat": -4.8600, "lng": -65.2900},
}

# ─── Outros metadados ─────────────────────────────────────────────────────────

ROLE_TYPES = {
    "1": "Nível Técnico",
    "2": "Nível Superior"
}

# Gerador dinâmico agrupado em apenas 2 níveis
RAW_ROLES = [
    ("1", [ # Nível Técnico (Técnicos + Apoio Operacional de Campo)
        "Técnico em Mecânica", "Técnico em Eletromecânica", "Técnico em Eletrotécnica", "Técnico em Eletrônica",
        "Técnico em Automação Industrial", "Técnico em Instrumentação", "Técnico em Mecatrônica", "Técnico em Metalurgia",
        "Técnico em Soldagem", "Técnico em Caldeiraria", "Técnico em Refrigeração e Climatização", "Técnico em Manutenção Industrial",
        "Técnico de Operação", "Técnico de Operação de Processos Industriais", "Técnico de Operação de Plataforma",
        "Técnico de Operação de Refinaria", "Técnico de Operação de Utilidades", "Técnico de Operação de Transferência e Estocagem",
        "Técnico de Operação de Produção", "Técnico em Logística", "Técnico em Suprimentos", "Técnico em Armazenagem",
        "Técnico em Controle de Materiais", "Técnico em Planejamento e Controle de Materiais (PCM)", "Técnico em Transporte",
        "Técnico em Movimentação de Cargas", "Técnico de ARM / Almoxarifado", "Técnico de Parque de Tubos",
        "Técnico de Estocagem e Dutos", "Técnico em Poços", "Técnico em Perfuração", "Técnico em Completação",
        "Técnico em Intervenção em Poços", "Técnico em Sondagem", "Técnico em Fluidos de Perfuração", "Técnico em Cimentação",
        "Técnico em Avaliação de Formação", "Técnico em Inspeção de Equipamentos", "Técnico em Ensaios Não Destrutivos (END)",
        "Técnico em Integridade de Dutos", "Técnico em Corrosão", "Técnico em Confiabilidade", "Técnico em Qualidade",
        "Técnico em Segurança do Trabalho", "Técnico em Meio Ambiente", "Técnico em Higiene Ocupacional",
        "Técnico em Saúde Ocupacional", "Técnico em Gestão Ambiental", "Técnico em Emergência Industrial",
        "Técnico em Química", "Técnico em Laboratório", "Técnico em Análises Químicas", "Técnico em Petróleo e Gás",
        "Técnico em Geoquímica", "Técnico em Fluidos", "Técnico em Cromatografia",
        "Operador de Guindaste", "Operador de Empilhadeira", "Operador de Equipamentos Pesados", "Inspetor de Cargas",
        "Fiscal de Contratos", "Supervisor de Área", "Supervisor de Operações", "Supervisor de Manutenção",
        "Coordenador Operacional", "Coordenador de SMS"
    ]),
    ("2", [ # Nível Superior (Engenharias, Geociências, Tecnólogos e Corporativo)
        "Engenheiro de Petróleo", "Engenheiro de Poços", "Engenheiro de Perfuração", "Engenheiro de Completação",
        "Engenheiro de Produção", "Engenheiro Mecânico", "Engenheiro Elétrico", "Engenheiro Eletrônico",
        "Engenheiro de Automação", "Engenheiro Químico", "Engenheiro de Processamento", "Engenheiro Metalurgista",
        "Engenheiro Naval", "Engenheiro Oceânico", "Engenheiro Civil", "Engenheiro de Materiais", "Engenheiro de Corrosão",
        "Engenheiro de Confiabilidade", "Engenheiro de Manutenção", "Engenheiro de Integridade", "Engenheiro de Dutos",
        "Engenheiro de Segurança de Processos", "Engenheiro Ambiental", "Engenheiro de Energia", "Engenheiro de Reservatórios",
        "Engenheiro Submarino", "Geólogo", "Geofísico", "Geofísico de Processamento", "Geofísico de Interpretação",
        "Geólogo de Reservatórios", "Geólogo de Poços", "Geólogo de Exploração", "Geocientista", "Químico",
        "Químico Industrial", "Pesquisador em Química", "Pesquisador em Petróleo", "Pesquisador em Materiais",
        "Pesquisador em Fluidos", "Pesquisador em Geoquímica",
        "Tecnólogo em Logística", "Tecnólogo em Petróleo e Gás", "Tecnólogo em Processos Industriais",
        "Tecnólogo em Automação Industrial", "Tecnólogo em Manutenção Industrial", "Tecnólogo em Produção",
        "Tecnólogo em Gestão Ambiental", "Tecnólogo em Gestão de Projetos", "Tecnólogo em Sistemas Industriais",
        "Analista de Planejamento", "Analista de Custos", "Analista de Contratos", "Analista de Suprimentos",
        "Analista de Logística", "Analista de Materiais", "Analista de Projetos", "Analista de Confiabilidade",
        "Analista de Processos", "Analista de Riscos", "Analista de SMS", "Analista de Meio Ambiente",
        "Analista de Sistemas", "Analista de Infraestrutura", "Analista de Redes", "Analista de Cibersegurança",
        "Analista de Dados", "Cientista de Dados", "Engenheiro de Dados", "Especialista em Automação Predial",
        "Especialista em Sistemas Industriais (OT)", "Analista de Recursos Humanos", "Analista de Treinamento",
        "Analista Financeiro", "Analista Contábil", "Economista", "Advogado", "Administrador", "Auditor"
    ])
]

# A rotina de compilação continua idêntica
ROLES = {}
_role_id = 1
for r_type_id, role_list in RAW_ROLES:
    for r_name in role_list:
        ROLES[str(_role_id)] = {
            "name": r_name,
            "role_type_id": r_type_id
        }
        _role_id += 1

DEPARTMENTS = {
    "1": "POÇOS", "2": "SUB", "3": "SUPRIMENTOS",
    "4": "LOEP", "5": "OPERAÇÃO", "6": "COMPARTILHADO", "7": "ANCORAGEM", "8": "ARM", "9": "RH"
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

    # ROLES (Agora estruturado)
    for rid, data in ROLES.items():
        pipe.hset(f"meta:roles:{rid}", mapping={k: str(v) for k, v in data.items()})
        pipe.sadd("meta:roles:list", rid)

    # Lookup hashes simples (para dropdowns remanescentes)
    for rid, name in ROLE_TYPES.items():   pipe.hset("meta:role_types",   rid, name)
    for did, name in DEPARTMENTS.items():  pipe.hset("meta:departments",  did, name)
    for wid, name in WORK_REGIMES.items(): pipe.hset("meta:work_regimes", wid, name)

    await pipe.execute()
    print(f"✓ {len(STATES)} estados, {len(REGIONS)} regiões, {len(LOCATIONS)} bases")
    print(f"✓ {len(ROLES)} cargos (roles), {len(ROLE_TYPES)} tipos de cargo")
    print(f"✓ departments, work_regimes")


async def main():
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    r = await aioredis.from_url(url, decode_responses=True)
    try:
        await seed(r)
    finally:
        await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())