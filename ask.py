import ollama

# Read the file's text into a variable
with open("notes.txt", "r") as file:
    document_text = file.read()

# Split the document into chunks (splitting on blank lines between paragraphs)
chunks = document_text.split("\n\n")
chunks = [chunk.strip() for chunk in chunks if chunk.strip() != ""]

print(f"Split into {len(chunks)} chunks")
for i, chunk in enumerate(chunks):
    print(f"--- Chunk {i} ---")
    print(chunk)

question = input("Ask something about the document: ")

# Combine the document and the question into one message
prompt = f"""Here is a document:

{document_text}

Based on the document above, answer this question: {question}"""

response = ollama.chat(
    model="llama3.2",
    messages=[
        {"role": "user", "content": prompt}
    ]
)

print(response["message"]["content"])