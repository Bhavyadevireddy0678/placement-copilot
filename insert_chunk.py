from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer
from db_config import get_database_url

DATABASE_URL = get_database_url()

engine = create_engine(DATABASE_URL)

model = SentenceTransformer("all-MiniLM-L6-v2")

chunk = "Amazon focuses heavily on DSA and problem solving"

embedding = model.encode(chunk).tolist()

with engine.connect() as conn:
    conn.execute(
        text("""
        INSERT INTO chunks (content, embedding, source)
        VALUES (:content, :embedding, :source)
        """),
        {
            "content": chunk,
            "embedding": embedding,
            "source": "manual"
        }
    )
    
    conn.commit()

print("Inserted successfully!")