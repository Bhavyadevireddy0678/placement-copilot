import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
model=SentenceTransformer("all-MiniLM-L6-v2")
from sklearn.metrics.pairwise import cosine_similarity
chunks = [
    "Amazon focuses heavily on DSA and problem solving",
    "Amazon evaluates leadership principles",
    "Frontend roles require React and JavaScript",
    "Microsoft often asks system design questions"
]


embeddings = model.encode(chunks)

query = "How should I prepare for Amazon coding interviews?"

query_embedding = model.encode([query])
query_embedding = np.array(query_embedding).astype("float32")
print(embeddings.shape)
embeddings = np.array(embeddings).astype("float32")
dimension = embeddings.shape[1]

index = faiss.IndexFlatL2(dimension)
index.add(embeddings)
print(index.ntotal)
k = 2

distances, indices = index.search(query_embedding, k)
print(indices)

for idx in indices[0]:
    print(chunks[idx])