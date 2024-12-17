from markitdown import MarkItDown
from openai import OpenAI
import os

print(os.getcwd())
test_file = os.path.join(os.getcwd(), 'ai', 'test.xlsx')
print(os.path.exists(test_file))

markitdown = MarkItDown()
result = markitdown.convert(test_file)
print(result.text_content)
print("=========")

client = OpenAI(
    base_url = 'http://localhost:11434/v1',
    api_key='ollama', # required, but unused
)

md = MarkItDown(mlm_client=client, mlm_model="llama3")
# test_file = os.path.join(os.getcwd(), 'ai', 'test.jpg')
result = md.convert(test_file)
print(result.text_content)