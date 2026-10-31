import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pgvector.psycopg2 import register_vector
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer
from sqlalchemy.engine import URL


BASE_DIR = Path(__file__).resolve().parent
DOCUMENTS_DIR = BASE_DIR / "documents"
EMBEDDING_DIMENSION = 384


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, connect_timeout=5)

    password = os.getenv("DB_PASSWORD")
    if not password:
        raise RuntimeError("Set DATABASE_URL or DB_PASSWORD before ingestion")

    database_url = URL.create(
        "postgresql",
        username=os.getenv("DB_USER", "raguser"),
        password=password,
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "placement_rag"),
    )
    return psycopg2.connect(database_url.render_as_string(hide_password=False), connect_timeout=5)


def main():
    load_dotenv(BASE_DIR / ".env")
    batch_size = int(os.getenv("INGEST_BATCH_SIZE", "64"))
    if batch_size < 1:
        raise ValueError("INGEST_BATCH_SIZE must be a positive integer")

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = []
    for path in sorted(DOCUMENTS_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            chunks.extend((chunk, path.name) for chunk in splitter.split_text(text))

    if not chunks:
        raise RuntimeError(f"No non-empty .txt documents found in {DOCUMENTS_DIR}")

    model = SentenceTransformer(os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
    if model.get_sentence_embedding_dimension() != EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Embedding model must produce {EMBEDDING_DIMENSION}-dimensional vectors"
        )
    connection = get_connection()
    try:
        register_vector(connection)
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS source text")
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
                    ON chunks USING hnsw (embedding vector_cosine_ops)
                    """
                )
                cursor.execute(
                    """
                    CREATE TEMP TABLE chunks_staging (
                        content text NOT NULL,
                        embedding vector(384) NOT NULL,
                        source text NOT NULL
                    ) ON COMMIT DROP
                    """
                )

                for start in range(0, len(chunks), batch_size):
                    batch = chunks[start : start + batch_size]
                    embeddings = model.encode(
                        [content for content, _ in batch],
                        batch_size=batch_size,
                        show_progress_bar=False,
                    )
                    rows = [
                        (content, embedding, source)
                        for (content, source), embedding in zip(batch, embeddings)
                    ]
                    execute_values(
                        cursor,
                        "INSERT INTO chunks_staging (content, embedding, source) VALUES %s",
                        rows,
                        page_size=batch_size,
                    )

                cursor.execute("TRUNCATE TABLE chunks")
                cursor.execute(
                    """
                    INSERT INTO chunks (content, embedding, source)
                    SELECT content, embedding, source
                    FROM chunks_staging
                    """
                )
        print(f"Ingestion complete: replaced corpus with {len(chunks)} chunks")
    finally:
        connection.close()


if __name__ == "__main__":
    main()