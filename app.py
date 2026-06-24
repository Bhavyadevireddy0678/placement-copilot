from fastapi import FastAPI
from sqlalchemy import create_engine, text

app = FastAPI()

DATABASE_URL = "postgresql://raguser:ragpass@localhost:5432/placement_rag"

engine = create_engine(DATABASE_URL)

@app.get("/")
def home():
    return {"message": "Placement Copilot API Running"}

@app.get("/highest-package")
def highest_package():
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT MAX(fte_package) FROM placements")
        )
@app.get("/microsoft-count")
def microsoft_count():
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM placements
                WHERE company='Microsoft'
            """)
        )

        return {
            "count": result.scalar()
        }

        return {
            "highest_package": result.scalar()
        }