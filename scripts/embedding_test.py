from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

model = SentenceTransformer("all-MiniLM-L6-v2")

with open("documents/amazon.txt", "r") as file:
    text = file.read()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)

chunks = splitter.split_text(text)

for i, chunk in enumerate(chunks):
    embedding = model.encode(chunk)

    print(f"\n--- CHUNK {i + 1} ---")
    print(chunk)
    print("Embedding dimensions:", len(embedding))
