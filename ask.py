import ollama

question = input("Ask something: ")

response = ollama.chat(
    model="llama3.2",
    messages=[
        {"role": "user", "content": question}
    ]
)

print(response["message"]["content"])