from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.2:1b",
                 base_url='http://localhost:11434',
                 api_key="ollama"
                 )

question = "how old is the US president?"
raw_prompt_template = (
    "You have access to search engine that provides you an "
    "information about fresh events and news given the query. "
    "Given the question, decide whether you need an additional "
    "information from the search engine (reply with 'SEARCH: "
    "<generated query>' or you know enough to answer the user "
    "then reply with 'RESPONSE <final response>').\n"
    "Now, act to answer a user question:\n{QUESTION}"
)
prompt_template = PromptTemplate.from_template(raw_prompt_template)
result = (prompt_template | llm).invoke(question)


print(result.content)
