import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL


BASE_DIR = Path(__file__).resolve().parent


def get_database_url():
    load_dotenv(BASE_DIR / ".env")
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    password = os.getenv("DB_PASSWORD")
    if not password:
        raise RuntimeError("Set DATABASE_URL or DB_PASSWORD before connecting")

    return URL.create(
        "postgresql",
        username=os.getenv("DB_USER", "raguser"),
        password=password,
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "placement_rag"),
    ).render_as_string(hide_password=False)