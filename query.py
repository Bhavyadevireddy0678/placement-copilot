from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://raguser:ragpass@localhost:5432/placement_rag"

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(
        text("SELECT MAX(fte_package) FROM placements")
    )

    print(result.scalar())