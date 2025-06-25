# references: https://myapollo.com.tw/blog/langchain-streamlit-toolbox/
import os
import streamlit as st
# from langchain_community.llms.ollama import Ollama
from langchain_ollama import OllamaLLM

llm = OllamaLLM(model='deepseek-r1:latest')

def generate_response(text):
    # return llm.invoke(text)
    for r in llm.stream(text):
        yield r

st.title('Ask Me Anything')

with st.form('form'):
    text = st.text_area('Enter text', '')
    submitted = st.form_submit_button('Submit')
    if submitted:
        st.write_stream(generate_response(text))