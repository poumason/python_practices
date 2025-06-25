import os

# Get keys for your project from the project settings page
# https://cloud.langfuse.com
os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-7598748f-59e9-4bc9-950a-e1feb9e8ecfc"
os.environ["LANGFUSE_SECRET_KEY"] = "sk-lf-e6aa1127-237d-425c-a119-6c3c460554b9"
os.environ["LANGFUSE_HOST"] = "http://localhost:8198/my_langfuse" # 🇪🇺 EU region

# Drop-in replacement to get full logging by changing only the import
from langfuse.openai import OpenAI

# Configure the OpenAI client to use http://localhost:11434/v1 as base url
client = OpenAI(
    base_url = 'http://localhost:11434/v1',
    api_key='None', # required, but unused
)

response = client.chat.completions.create(
  model="llama3.2:latest",
  messages=[
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Who was the first person to step on the moon?"},
    {"role": "assistant", "content": "Neil Armstrong was the first person to step on the moon on July 20, 1969, during the Apollo 11 mission."},
    {"role": "user", "content": "What were his first words when he stepped on the moon?"}
  ]
)
print(response.choices[0].message.content)