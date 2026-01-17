from langchain_openai import ChatOpenAI

if __name__ == "__main__":
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_base="https://api.openai.com/v1")
    response = llm.predict("Hello, world!")
    print(response)
