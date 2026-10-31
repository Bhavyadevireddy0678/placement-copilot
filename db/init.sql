CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'raguser') THEN
        CREATE ROLE raguser LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_readonly') THEN
        CREATE ROLE rag_readonly LOGIN;
    END IF;
END
$$;

\getenv app_password DB_PASSWORD
\getenv readonly_password SQL_READONLY_PASSWORD
\getenv database_name POSTGRES_DB
SELECT format('ALTER ROLE raguser WITH LOGIN PASSWORD %L', :'app_password') \gexec
SELECT format('ALTER ROLE rag_readonly WITH LOGIN PASSWORD %L', :'readonly_password') \gexec
SELECT format('ALTER DATABASE %I OWNER TO raguser', :'database_name') \gexec
ALTER SCHEMA public OWNER TO raguser;
SET ROLE raguser;

CREATE TABLE IF NOT EXISTS placements (
    student_id text,
    student_name text,
    branch text,
    company text,
    stipend integer,
    fte_package double precision,
    month_placed text
);

CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    content text NOT NULL,
    embedding vector(384) NOT NULL,
    source text NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

SELECT format('GRANT CONNECT ON DATABASE %I TO rag_readonly', :'database_name') \gexec
REVOKE ALL ON SCHEMA public FROM rag_readonly;
GRANT USAGE ON SCHEMA public TO rag_readonly;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON placements FROM rag_readonly;
REVOKE ALL ON chunks FROM rag_readonly;
GRANT SELECT ON placements TO rag_readonly;
GRANT SELECT ON chunks TO rag_readonly;
