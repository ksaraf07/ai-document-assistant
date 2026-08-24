from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ollama
import math
import os

MIN_SIMILARITY = 0.5

DOCUMENTS_FOLDER = "documents"
CHUNK_SIZE = 500       # characters per chunk
CHUNK_OVERLAP = 50     # characters shared between neighboring chunks
TOP_K = 3              # how many chunks to hand the AI

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


def split_into_chunks(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start += chunk_size - overlap  # step forward, but re-cover the overlap
    return chunks


def load_chunks():
    chunks = []
    for filename in os.listdir(DOCUMENTS_FOLDER):
        filepath = os.path.join(DOCUMENTS_FOLDER, filename)
        with open(filepath, "r") as file:
            text = file.read()
        for piece in split_into_chunks(text):
            chunks.append((filename, piece))
    return chunks


@asynccontextmanager
async def lifespan(app: FastAPI):
    global all_chunks, chunk_embeddings
    print("Loading documents and computing embeddings...")
    all_chunks = load_chunks()
    chunk_embeddings = [get_embedding(chunk) for _, chunk in all_chunks]
    print(f"Ready with {len(all_chunks)} chunks")
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Question(BaseModel):
    question: str


@app.post("/ask")
def ask(payload: Question):
    question_embedding = get_embedding(payload.question)
    similarities = [cosine_similarity(question_embedding, emb) for emb in chunk_embeddings]

    ranked_indices = sorted(range(len(similarities)), key=lambda i: similarities[i], reverse=True)

    top_indices = [i for i in ranked_indices if similarities[i] >= MIN_SIMILARITY][:TOP_K]

    if not top_indices:
        top_indices = ranked_indices[:1]

    context_parts = []
    sources = set()
    for i in top_indices:
        filename, chunk = all_chunks[i]
        context_parts.append(f'From "{filename}":\n{chunk}')
        sources.add(filename)

    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""Here are some relevant excerpts from documents:

{context}

Based on the excerpts above, answer this question: {payload.question}"""

    response = ollama.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": prompt}]
    )

    return {
        "answer": response["message"]["content"],
        "sources": list(sources)
    }