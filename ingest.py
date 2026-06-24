from sentence_transformers import SentenceTransformer
import psycopg2
from pgvector.psycopg2 import register_vector

model = SentenceTransformer("all-MiniLM-L6-v2")

documents = [
    "Students with CGPA below 6.0 are not eligible for placement drives.",
    "Companies offering above 10 LPA require CGPA 7.5 and no active backlogs.",
    "Formal dress code is mandatory for placement drives.",
    "Students can attend a maximum of 3 dream company interviews.",
    "Backlogs must be cleared before placement season."
]

conn = psycopg2.connect(
    dbname="placement_rag",
    user="raguser",
    password="ragpass",
    host="localhost",
    port="5432"
)

register_vector(conn)

cur = conn.cursor()

for doc in documents:
    embedding = model.encode(doc)

    cur.execute(
        """
        INSERT INTO chunks(content, embedding)
        VALUES (%s, %s)
        """,
        (doc, embedding)
    )

conn.commit()

cur.close()
conn.close()

print("Done")