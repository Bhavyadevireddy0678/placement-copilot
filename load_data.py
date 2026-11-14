from uuid import uuid4

import pandas as pd
from sqlalchemy import create_engine, text
from db_config import BASE_DIR, get_database_url

DATABASE_URL = get_database_url()

engine = create_engine(DATABASE_URL)

df = pd.read_csv(BASE_DIR / "synthetic_placements.csv")
staging_table = f"placements_staging_{uuid4().hex}"

df.to_sql(staging_table, engine, if_exists="fail", index=False)
try:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE placements"))
        connection.execute(
            text(
                f"""
                INSERT INTO placements (
                    student_id, student_name, branch, company,
                    stipend, fte_package, month_placed
                )
                SELECT student_id, student_name, branch, company,
                       stipend, fte_package, month_placed
                FROM \"{staging_table}\"
                """
            )
        )
        connection.execute(text(f'DROP TABLE "{staging_table}"'))
finally:
    with engine.begin() as connection:
        connection.execute(text(f'DROP TABLE IF EXISTS "{staging_table}"'))

print("Loaded", len(df), "rows")