import requests
import json
from ollama import Client

client = Client(host='http://localhost:11434')
response = client.chat(model='llama3:latest', messages=[
  {
    'role': 'user',
    'content': 'Why is the sky blue?',
  },
])
print(response.content)


def analyze_file(file_path: str) -> Dict[str, Any]:
    with open(file_path, "rb") as file:
        data = {"model": "text-davinci-003", "prompt": f"Analyze the following {os.path.basename(file_path)}:", "file": file}
        response = client.create_chat_completion(**data)
        return response["choices"][0]["message"]["content"]
    
# # Your API token goes here
# api_token = 'YOUR_API_TOKEN'

# # The URL for the Ollama API
# url = "https://app.ollama.io/v1/reviews"

# # Your code goes here
# code = """
# # Sample Python code for Ollama API

# def function():
#     pass
# """

# # Create a dictionary with your code as the value of the 'code' key
# data = {'code': code}

# # Make a POST request to the Ollama API using the requests library
# response = requests.post(url, json=data, headers={'Authorization': f'Bearer {api_token}'})

# # Print the response from the Ollama API
# print(json.loads(response.content))
