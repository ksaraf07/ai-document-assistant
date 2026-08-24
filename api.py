from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pwdlib import PasswordHash
import ollama
import math
import os
import sqlite3
import os
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()
SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # token stays valid for 1 day

DOCUMENTS_FOLDER = "documents"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3
MIN_SIMILARITY = 0.5

all_chunks = []
chunk_embeddings = []

password_hash = PasswordHash.recommended()

def get_user_db_connection():
    return sqlite3.connect("users.db")


def init_users_table():
    connection = get_user_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL
        )
    """)
    connection.commit()
    connection.close()


class UserRegister(BaseModel):
    username: str
    password: str


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
        start += chunk_size - overlap
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
    init_users_table()
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


@app.post("/register")
def register(payload: UserRegister):
    connection = get_user_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (payload.username,))
    existing = cursor.fetchone()

    if existing:
        connection.close()
        raise HTTPException(status_code=400, detail="Username already taken")

    hashed = password_hash.hash(payload.password)
    cursor.execute(
        "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
        (payload.username, hashed)
    )
    connection.commit()
    connection.close()

    return {"message": "User created", "username": payload.username}

class UserLogin(BaseModel):
    username: str
    password: str


def create_access_token(username: str):
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@app.post("/login")
def login(payload: UserLogin):
    connection = get_user_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT hashed_password FROM users WHERE username = ?", (payload.username,))
    row = cursor.fetchone()
    connection.close()

    if row is None or not password_hash.verify(payload.password, row[0]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    token = create_access_token(payload.username)
    return {"access_token": token, "token_type": "bearer"}


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