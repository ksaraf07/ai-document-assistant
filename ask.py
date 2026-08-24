import ollama

# Read the file's text into a variable
with open("notes.txt", "r") as file:
    document_text = file.read()

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