from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

llm = ChatOpenAI(base_url='http://localhost:8500/v1',
                 openai_api_key='sk-bf-d5f8fbd7-440c-4d47-94a3-ed8a42e69cca',
                 model='ollama/qwen3:8b',
                 temperature=0
                 )

# print(llm.invoke('hello'))

# from langchain_openai import ChatOpenAI

# # Initialize the model pointing to Bifrost
# llm = ChatOpenAI(
#     model="gpt-4o", # Or any model supported by your Bifrost config (e.g., "claude-3")
#     openai_api_key="your-bifrost-virtual-key",
#     base_url="http://localhost:8080/v1" # Your Bifrost endpoint
# )

# Invoke the model
response = llm.invoke(
    [HumanMessage(content="give me a joke about car, and word limit to 10.")])
print(response.content)


# curl -X POST http://localhost:8500/v1/chat/completions \
#   --connect-timeout 5
#   -H "Content-Type: application/json" \
#   -d '{
#     "model": "ollama/qwen3:8b",
#     "messages": [{"role": "user", "content": "What is the benefit of using an LLM gateway?"}]
#   }'

# from langchain_ollama import ChatOllama

# llm = ChatOllama(
#     base_url="http://localhost:8500",
#     model="ollama/qwen3:8b",
#     temperature=0,
#     # other params...

# )
