from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
import ollama
import math
import os

DOCUMENTS_FOLDER = "documents"

all_chunks = []
chunk_embeddings = []


def get_embedding(text):
    response = ollama.embed(model="nomic-embed-text", input=text)
    return response["embeddings"][0]


def cosine_similarity(a, b):
    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x * x for x in a))
    magnitude_b = math.sqrt(sum(x * x for x in b))
    return dot_product / (magnitude_a * magnitude_b)


def load_chunks():
    chunks = []
    for filename in os.listdir(DOCUMENTS_FOLDER):
        filepath = os.path.join(DOCUMENTS_FOLDER, filename)
        with open(filepath, "r") as file:
            text = file.read()
        pieces = text.split("\n\n")
        pieces = [p.strip() for p in pieces if p.strip() != ""]
        for piece in pieces:
            chunks.append((filename, piece))
    return chunks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Everything before "yield" runs once, when the server starts
    global all_chunks, chunk_embeddings
    print("Loading documents and computing embeddings...")
    all_chunks = load_chunks()
    chunk_embeddings = [get_embedding(chunk) for _, chunk in all_chunks]
    print(f"Ready with {len(all_chunks)} chunks")
    yield
    # (anything after "yield" would run when the server shuts down — nothing needed here)


app = FastAPI(lifespan=lifespan)


class Question(BaseModel):
    question: str


@app.post("/ask")
def ask(payload: Question):
    question_embedding = get_embedding(payload.question)
    similarities = [cosine_similarity(question_embedding, emb) for emb in chunk_embeddings]
    best_index = similarities.index(max(similarities))
    best_filename, best_chunk = all_chunks[best_index]

    prompt = f"""Here is a relevant excerpt from a document called "{best_filename}":

{best_chunk}

Based on the excerpt above, answer this question: {payload.question}"""

    response = ollama.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": prompt}]
    )

    return {
        "answer": response["message"]["content"],
        "source": best_filename
    }