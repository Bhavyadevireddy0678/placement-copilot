from sqlalchemy import create_engine, text
from db_config import get_database_url

DATABASE_URL = get_database_url()

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
    print(result.scalar())