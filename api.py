from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from datetime import datetime, timedelta, timezone
import ollama
import math
import os
import re
import sqlite3
import jwt
from dotenv import load_dotenv
from pypdf import PdfReader
import io

load_dotenv()
SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

DOCUMENTS_FOLDER = "documents"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3
MIN_SIMILARITY = 0.5

TEXT_EXTENSIONS = {".txt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PDF_EXTENSIONS = {".pdf"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | PDF_EXTENSIONS
MIN_PDF_TEXT_LENGTH = 20  # below this, assume it's a scanned PDF with no real text
VISION_MODEL = "qwen2.5vl:3b"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

security = HTTPBearer()
password_hash = PasswordHash.recommended()

user_index = {}


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
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)


class UserLogin(BaseModel):
    username: str
    password: str


def create_access_token(username: str):
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_username(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


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

def extract_pdf_text(contents):
    reader = PdfReader(io.BytesIO(contents))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages).strip()

def load_user_documents(username):
    """Chunk and embed every .txt file in this user's folder.
    Raw image files are skipped here on purpose — only their generated
    .description.txt (created at upload time) gets indexed."""
    user_folder = os.path.join(DOCUMENTS_FOLDER, username)
    chunks = []

    if os.path.exists(user_folder):
        for filename in os.listdir(user_folder):
            if not filename.endswith(".txt"):
                continue
            filepath = os.path.join(user_folder, filename)
            with open(filepath, "r") as file:
                text = file.read()
            for piece in split_into_chunks(text):
                chunks.append((filename, piece))

    embeddings = [get_embedding(chunk) for _, chunk in chunks]
    return {"chunks": chunks, "embeddings": embeddings}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_users_table()
    os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)

    print("Loading each user's documents...")
    for username in os.listdir(DOCUMENTS_FOLDER):
        user_folder = os.path.join(DOCUMENTS_FOLDER, username)
        if os.path.isdir(user_folder):
            user_index[username] = load_user_documents(username)
            print(f"  {username}: {len(user_index[username]['chunks'])} chunks")

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
    if cursor.fetchone():
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


@app.post("/documents/upload")
def upload_document(file: UploadFile = File(...), username: str = Depends(get_current_username)):
    original_name = file.filename
    ext = os.path.splitext(original_name)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only .txt files, images (.jpg, .jpeg, .png, .webp), and text-based .pdf files are supported"
        )

    contents = file.file.read()

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="That file is empty")

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File is too large (max 10MB)")

    # For PDFs, check there's actual readable text BEFORE saving anything —
    # this is what quietly rejects scanned/image-only PDFs
    extracted_pdf_text = None
    if ext == ".pdf":
        extracted_pdf_text = extract_pdf_text(contents)
        if len(extracted_pdf_text) < MIN_PDF_TEXT_LENGTH:
            raise HTTPException(
                status_code=400,
                detail="This PDF doesn't contain readable text (it may be a scanned document). Please upload a text-based PDF instead."
            )

    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(original_name))

    user_folder = os.path.join(DOCUMENTS_FOLDER, username)
    os.makedirs(user_folder, exist_ok=True)

    filepath = os.path.join(user_folder, safe_name)
    with open(filepath, "wb") as f:
        f.write(contents)

    if ext in IMAGE_EXTENSIONS:
        description_response = ollama.chat(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": "Describe this image in detail, including any visible text.",
                "images": [contents]
            }]
        )
        description = description_response["message"]["content"]
        with open(filepath + ".description.txt", "w") as f:
            f.write(f"[Image: {safe_name}]\n\n{description}")

    elif ext == ".pdf":
        with open(filepath + ".extracted.txt", "w") as f:
            f.write(f"[PDF: {safe_name}]\n\n{extracted_pdf_text}")

    user_index[username] = load_user_documents(username)

    return {
        "message": "File uploaded",
        "filename": safe_name,
        "total_chunks": len(user_index[username]["chunks"])
    }


class Question(BaseModel):
    question: str


@app.post("/ask")
def ask(payload: Question, username: str = Depends(get_current_username)):
    user_data = user_index.get(username)

    if not user_data or not user_data["chunks"]:
        raise HTTPException(status_code=404, detail="You haven't uploaded any documents yet")

    chunks = user_data["chunks"]
    chunk_embeddings = user_data["embeddings"]

    question_embedding = get_embedding(payload.question)
    similarities = [cosine_similarity(question_embedding, emb) for emb in chunk_embeddings]

    ranked_indices = sorted(range(len(similarities)), key=lambda i: similarities[i], reverse=True)
    top_indices = [i for i in ranked_indices if similarities[i] >= MIN_SIMILARITY][:TOP_K]
    if not top_indices:
        top_indices = ranked_indices[:1]

    context_parts = []
    sources = set()
    for i in top_indices:
        filename, chunk = chunks[i]
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