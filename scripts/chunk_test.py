from langchain_text_splitters import RecursiveCharacterTextSplitter

with open("documents/amazon.txt", "r") as file:
    text = file.read()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)

chunks = splitter.split_text(text)

for i, chunk in enumerate(chunks):
    print(f"\n--- CHUNK {i + 1} ---")
    print(chunk)
