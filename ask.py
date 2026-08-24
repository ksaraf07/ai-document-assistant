import ollama
import math
import os

DOCUMENTS_FOLDER = "documents"


def load_chunks():
    all_chunks = []  # each item: (which file it came from, the text)
    for filename in os.listdir(DOCUMENTS_FOLDER):
        filepath = os.path.join(DOCUMENTS_FOLDER, filename)
        with open(filepath, "r") as file:
            text = file.read()
        chunks = text.split("\n\n")
        chunks = [c.strip() for c in chunks if c.strip() != ""]
        for chunk in chunks:
            all_chunks.append((filename, chunk))
    return all_chunks


def get_embedding(text):
    response = ollama.embed(model="nomic-embed-text", input=text)
    return response["embeddings"][0]


def cosine_similarity(a, b):
    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x * x for x in a))
    magnitude_b = math.sqrt(sum(x * x for x in b))
    return dot_product / (magnitude_a * magnitude_b)


print("Loading documents...")
all_chunks = load_chunks()
file_count = len(set(filename for filename, _ in all_chunks))
print(f"Loaded {len(all_chunks)} chunks from {file_count} files")

print("Turning each chunk into numbers...")
chunk_embeddings = [get_embedding(chunk) for _, chunk in all_chunks]

print("\nReady! Type a question, or type 'quit' to exit.\n")

while True:
    question = input("Ask something: ")

    if question.lower() == "quit":
        break

    question_embedding = get_embedding(question)

    similarities = [cosine_similarity(question_embedding, emb) for emb in chunk_embeddings]
    best_index = similarities.index(max(similarities))
    best_filename, best_chunk = all_chunks[best_index]

    prompt = f"""Here is a relevant excerpt from a document called "{best_filename}":

{best_chunk}

Based on the excerpt above, answer this question: {question}"""

    response = ollama.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": prompt}]
    )

    print(f"\n(from {best_filename})")
    print(response["message"]["content"])
    print()