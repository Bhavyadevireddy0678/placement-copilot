from sqlalchemy import text


VECTOR_QUERY = text(
    """
    SELECT content,
           source,
           embedding <=> :embedding AS distance
    FROM chunks
    ORDER BY distance
    LIMIT :top_k
    """
)

HYBRID_QUERY = text(
    """
    WITH vector_results AS (
        SELECT id,
               content,
               source,
               embedding <=> :embedding AS distance,
               row_number() OVER (
                   ORDER BY embedding <=> :embedding ASC, id ASC
               ) AS vector_rank
        FROM chunks
        ORDER BY embedding <=> :embedding ASC, id ASC
        LIMIT :candidate_limit
    ),
    text_results AS (
        SELECT id,
               content,
               source,
               embedding <=> :embedding AS distance,
               row_number() OVER (
                   ORDER BY ts_rank_cd(
                       search_vector,
                       plainto_tsquery('english', :question)
                   ) DESC,
                   id ASC
               ) AS text_rank
        FROM chunks
        WHERE search_vector @@ plainto_tsquery('english', :question)
        ORDER BY ts_rank_cd(
            search_vector,
            plainto_tsquery('english', :question)
        ) DESC, id ASC
        LIMIT :candidate_limit
    ),
    ranked_candidates AS (
        SELECT id, content, source, distance, vector_rank AS result_rank
        FROM vector_results
        UNION ALL
        SELECT id, content, source, distance, text_rank AS result_rank
        FROM text_results
    ),
    fused_results AS (
        SELECT id,
               content,
               source,
               MIN(distance) AS distance,
               SUM(1.0 / (60 + result_rank)) AS rrf_score
        FROM ranked_candidates
        GROUP BY id, content, source
    )
    SELECT content, source, distance, rrf_score
    FROM fused_results
    ORDER BY rrf_score DESC, distance ASC, id ASC
    LIMIT :top_k
    """
)


def retrieve_chunks(connection, question, embedding, top_k=3, hybrid=False):
    if top_k < 1:
        raise ValueError("top_k must be a positive integer")
    parameters = {"embedding": embedding, "top_k": top_k}
    if not hybrid:
        return connection.execute(VECTOR_QUERY, parameters).fetchall()

    candidate_limit = max(top_k * 4, 20)
    parameters.update(
        question=question,
        candidate_limit=candidate_limit,
    )
    return connection.execute(HYBRID_QUERY, parameters).fetchall()
