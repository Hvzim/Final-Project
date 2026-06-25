from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import secrets
import redis
import json
import requests
import os
from celery_app import celery_app
from celery.result import AsyncResult

##########################################
try:
    from kafka_producer import enviar_evento
except Exception:
    def enviar_evento(*args, **kwargs):
        pass
##########################################
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session

import logging

logging.basicConfig(
    filename="/logs/backend.log",
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}'
)

logger = logging.getLogger(__name__)

user_admin = os.getenv("MEU_USUARIO", "admin")
password_admin = os.getenv("MINHA_SENHA", "admin")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=6379,
    db=0,
    decode_responses=True
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./pokemon.db"
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()
app = FastAPI()
security = HTTPBasic()

class Pokemon(BaseModel):
    pokemon_name: str
    pokemon_level: int
    pokemon_typing: str

class Pokemon_DB(Base):
    __tablename__ = "Pokemon_Table"

    id = Column(Integer, primary_key=True, index=True)
    pokemon_name = Column(String, unique=True, index=True)
    pokemon_level = Column(Integer)
    pokemon_typing = Column(String)

Base.metadata.create_all(bind=engine)


def get_session_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
def popular_pokedex():
    db = SessionLocal()
    try:
        total = db.query(Pokemon_DB).count()
        if total > 0:
            print(f"Pokédex já possui {total} registros.")
            return
        print("Baixando pokémons da API...")
        response = requests.get(
            "https://pokeapi.co/api/v2/pokemon?limit=1025",
            timeout=30
        )
        response.raise_for_status()
        pokemons = response.json()["results"]
        for pokemon_data in pokemons:
            db.add(
                Pokemon_DB(
                    pokemon_name=pokemon_data["name"],
                    pokemon_level=1,
                    pokemon_typing="unknown"
                )
            )
        db.commit()
        print(
            f"Pokédex populada com {db.query(Pokemon_DB).count()} pokémons."
        )
    except Exception as e:
        print(f"Erro ao popular pokédex: {e}")
    finally:
        db.close()

@app.on_event("startup")
def startup_event():
    popular_pokedex()

def user_authentication(
    credentials: HTTPBasicCredentials = Depends(security)
):
    if not (
        secrets.compare_digest(credentials.username, user_admin)
        and
        secrets.compare_digest(credentials.password, password_admin)
    ):
        raise HTTPException(
            status_code=401,
            detail="Username ou senha incorretos.",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials

@app.get("/debug/redis")
def see_redis():
    keys = redis_client.keys("pokemon:*")
    pokemon = []

    for key in keys:
        value = redis_client.get(key)

        pokemon.append({
            "key": key,
            "value": json.loads(value),
            "ttl": redis_client.ttl(key)
        })

    return pokemon

@app.get("/pokemon")
async def get_pokemon(
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(get_session_db),
    credentials: HTTPBasicCredentials = Depends(user_authentication)
):
    pokemon_list = (
        db.query(Pokemon_DB)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "page": page,
        "limit": limit,
        "total": db.query(Pokemon_DB).count(),
        "pokemon": [
            {
                "id": p.id,
                "pokemon_name": p.pokemon_name,
                "pokemon_level": p.pokemon_level,
                "pokemon_typing": p.pokemon_typing
            }
            for p in pokemon_list
        ]
    }

@app.get("/pokemon/{pokemon_id}")
async def get_pokemon_by_id(
    pokemon_id: int,
    db: Session = Depends(get_session_db),
    credentials: HTTPBasicCredentials = Depends(user_authentication)
):
    pokemon = db.query(Pokemon_DB).filter(
        Pokemon_DB.id == pokemon_id
    ).first()

    if not pokemon:
        raise HTTPException(404, "Pokemon não encontrado.")

    return {
        "id": pokemon.id,
        "pokemon_name": pokemon.pokemon_name,
        "pokemon_level": pokemon.pokemon_level,
        "pokemon_typing": pokemon.pokemon_typing
    }

@app.get("/pokemon/name/{pokemon_name}")
async def get_pokemon_by_name(
    pokemon_name: str,
    db: Session = Depends(get_session_db),
    credentials: HTTPBasicCredentials = Depends(user_authentication)
):
    pokemon = db.query(Pokemon_DB).filter(
        Pokemon_DB.pokemon_name.ilike(pokemon_name)
    ).first()

    if not pokemon:
        raise HTTPException(404, "Pokemon não encontrado.")

    return {
        "id": pokemon.id,
        "pokemon_name": pokemon.pokemon_name,
        "pokemon_level": pokemon.pokemon_level,
        "pokemon_typing": pokemon.pokemon_typing
    }

@app.post("/add")
async def add_pokemon(
    pokemon: Pokemon,
    db: Session = Depends(get_session_db),
    credentials: HTTPBasicCredentials = Depends(user_authentication)
):
    existe = db.query(Pokemon_DB).filter(
        Pokemon_DB.pokemon_name == pokemon.pokemon_name
    ).first()

    if existe:
        raise HTTPException(
            status_code=400,
            detail="Esse pokemon já existe!"
        )

    novo = Pokemon_DB(
        pokemon_name=pokemon.pokemon_name,
        pokemon_level=pokemon.pokemon_level,
        pokemon_typing=pokemon.pokemon_typing
    )

    db.add(novo)
    db.commit()
    db.refresh(novo)

    logger.info(
    json.dumps({
        "evento": "pokemon_criado",
        "pokemon": pokemon.pokemon_name
    })
)

    enviar_evento(
        "pokemon-criados",
            {
                "pokemon": pokemon.pokemon_name,
                "tipo": pokemon.pokemon_typing,
                "level": pokemon.pokemon_level
            }
        )

    return {"message": "Pokemon criado com sucesso!"}
    

@app.put("/update/{pokemon_id}")
async def update_pokemon(
    pokemon_id: int,
    pokemon: Pokemon,
    db: Session = Depends(get_session_db),
    credentials: HTTPBasicCredentials = Depends(user_authentication)
):
    db_pokemon = db.query(Pokemon_DB).filter(
        Pokemon_DB.id == pokemon_id
    ).first()

    if not db_pokemon:
        raise HTTPException(404, "Pokemon não encontrado.")

    db_pokemon.pokemon_name = pokemon.pokemon_name
    db_pokemon.pokemon_level = pokemon.pokemon_level
    db_pokemon.pokemon_typing = pokemon.pokemon_typing

    db.commit()
    db.refresh(db_pokemon)

    return {"message": "Pokemon atualizado com sucesso!"}

@app.delete("/delete/{pokemon_id}")
async def delete_pokemon(
    pokemon_id: int,
    db: Session = Depends(get_session_db),
    credentials: HTTPBasicCredentials = Depends(user_authentication)
):
    pokemon = db.query(Pokemon_DB).filter(
        Pokemon_DB.id == pokemon_id
    ).first()

    if not pokemon:
        raise HTTPException(404, "Pokemon não encontrado.")

    db.delete(pokemon)
    db.commit()

    return {"message": "Pokemon removido com sucesso!"}