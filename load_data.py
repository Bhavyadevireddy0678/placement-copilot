import pandas as pd
from sqlalchemy import create_engine

DATABASE_URL = "postgresql://raguser:ragpass@localhost:5432/placement_rag"

engine = create_engine(DATABASE_URL)

df = pd.read_csv("synthetic_placements.csv")

df.to_sql(
    "placements",
    engine,
    if_exists="append",
    index=False
)

print("Loaded", len(df), "rows")