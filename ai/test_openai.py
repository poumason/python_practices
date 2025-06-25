from langchain_openai import OpenAI

llm = OpenAI(base_url='http://localhost:8901/v1',
             api_key='None',
             model='deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B')
print(llm.invoke('hello'))
