from langchain_ollama import ChatOllama

model = ChatOllama(model="llama3.2",
                   base_url='http://localhost:30000',
                   )

messages = [
    ("human", "你好呀"),
]

for chunk in model.stream(messages):
    print(chunk.content, end='', flush=True)