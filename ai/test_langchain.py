import getpass
import os

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage,SystemMessage,AIMessage
from langchain_core.prompts import ChatPromptTemplate,HumanMessagePromptTemplate,PromptTemplate

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

prompt = ChatPromptTemplate(
 input_variables=['input'],
 messages=[
 SystemMessage(content='You are a doctor.'),
 HumanMessage(content='I do not feel good.'),
 AIMessage(content='I am sorry to hear that. Can you tell me more about your symptoms?'),
#  直接用同名的 input 帶入參數
 HumanMessagePromptTemplate(prompt=PromptTemplate(input_variables=['input'], template='{input}'))
 ]
)

# print(model.invoke(messages))
chats = model.invoke(prompt.format_messages(input="I have a headache")).content
print(chats)