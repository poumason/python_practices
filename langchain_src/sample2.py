from langchain_community.document_loaders import PyPDFLoader, TextLoader

from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import OllamaEmbeddings, ChatOllama

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate, ChatPromptTemplate

from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain.schema.output_parser import StrOutputParser

import asyncio
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

client = QdrantClient(url="http://localhost:6333")

prompt = PromptTemplate(
    template="""You are an assistant for question-answering tasks.
    Use the following documents to answer the question.
    If you don't know the answer, just say that you don't know.
    Use three sentences maximum and keep the answer concise:
    Question: {question}
    Documents: {documents}
    Answer:
    """,
    input_variables=["question", "documents"],
)


def loadPdf(path):
    loader = PyPDFLoader(path)
    # pages = []

    # for page in await loader.alazy_load():
    #     pages.append(page)
    pages = loader.load()
    print(len(pages))
    return pages


def main():
    pages = loadPdf('./PouLin.pdf')

    embeddings = OllamaEmbeddings(model="nomic-embed-text:v1.5",
                                  base_url='http://localhost:11434')
    # vector_store = InMemoryVectorStore.from_documents(pages, embeddings)

    # qdrant
    # client.create_collection(
    #     collection_name="demo_collection",
    #     vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
    # )

    # vector_store = QdrantVectorStore(
    #     client=client,
    #     collection_name="demo_collection",
    #     embedding=embeddings,
    # )

    vector_store = QdrantVectorStore.from_documents(
        pages,
        embeddings,
        url='http://localhost:6333',
        prefer_grpc=True,
        collection_name="my_documents",
    )

    docs = vector_store.similarity_search("What do jobs about in KKBOX", k=2)
    for doc in docs:
        print(f'Page {doc.metadata["page"]}: {doc.page_content[:300]}\n')

    # Initialize the LLM with Llama 3.1 model
    llm = ChatOllama(
        model="deepseek-r1:latest",
        temperature=0,
        base_url='http://localhost:11434'
    )

    # retriever = MultiQueryRetriever.from_llm(
    #     vector_store.as_retriever(),
    #     llm,
    #     prompt=prompt
    # )
    retriever = vector_store.as_retriever()

    template = """You are an assistant for question-answering tasks.
Use the following pieces of retrieved context to answer the question:
If you don't know the answer, then answer from your own knowledge and dont give just one word answer, and dont tell the user that you are answering from your knowledge.
Use three sentences maximum and keep the answer concise.

Question: {question}
Context: {context}
Answer:

"""

    prompt = ChatPromptTemplate.from_template(template)

    rag_chain = (
        {
            "context": retriever,
            "question": RunnablePassthrough()
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    while True:
        query = str(input("Enter Question: "))
        print(rag_chain.invoke(query))


# loader = TextLoader('./test.txt', encoding='utf-8')
# docs = loader.load()
# text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
# splits = text_splitter.split_documents(docs)


if __name__ == '__main__':
    main()
