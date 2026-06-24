from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer

DATABASE_URL = "postgresql://raguser:ragpass@localhost:5432/placement_rag"

engine = create_engine(DATABASE_URL)

model = SentenceTransformer("all-MiniLM-L6-v2")

chunk = "Amazon focuses heavily on DSA and problem solving"

embedding = model.encode(chunk).tolist()

with engine.connect() as conn:
    conn.execute(
        text("""
        INSERT INTO chunks (content, embedding)
        VALUES (:content, :embedding)
        """),
        {
            "content": chunk,
            "embedding": embedding
        }
    )
    
    conn.commit()

print("Inserted successfully!")