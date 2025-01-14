import getpass
import os

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage,SystemMessage

# if not os.environ.get("OPENAI_API_KEY"):
#   os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter API key for OpenAI: ")

# from langchain_openai import ChatOpenAI

# model = ChatOpenAI(model="mistral:latest", base_url="http://localhost:11434/api", api_key="ollama")

# model.invoke("Hello, world!")

model = ChatOllama(base_url="http://localhost:11434", model='mistral:latest')

messages = [
    SystemMessage("Translate the following from English into Italian"),
    HumanMessage("hi!"),
]

print(model.invoke(messages))