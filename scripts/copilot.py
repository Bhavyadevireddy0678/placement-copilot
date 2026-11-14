from sqlalchemy import create_engine, text
from db_config import get_database_url

DATABASE_URL = get_database_url()

engine = create_engine(DATABASE_URL)

question = input("Ask a question: ")

if "highest package" in question.lower():
    query = "SELECT MAX(fte_package) FROM placements"

elif "average package" in question.lower():
    query = "SELECT AVG(fte_package) FROM placements"

elif "microsoft" in question.lower():
    query = "SELECT COUNT(*) FROM placements WHERE company='Microsoft'"

elif "top recruiter" in question.lower():
    query = """
    SELECT company
    FROM placements
    GROUP BY company
    ORDER BY COUNT(*) DESC
    LIMIT 1
    """
else:
    print("I don't know this question yet.")
    exit()

with engine.connect() as conn:
    result = conn.execute(text(query))

    print("Answer:", result.scalar())