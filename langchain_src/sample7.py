# import requests
# import json

# HEADERS = {
#     "Authorization": "Bearer 0629",
#     "Content-Type": "application/json"
# }
# payload = {
#     "model": "gemma-4-E2B",
#     "messages": [
#         {"role": "user", "content": "Hello!"}
#     ]
# }

# response = requests.post("http://127.0.0.1:8000/v1/chat/completions",
#                          headers=HEADERS, json=json.dumps(payload))

# print(response.content)


from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="0629" # Replace with actual API key
)

completion = client.chat.completions.create(
    model="Qwen3.5-9B-MLX-4bit",
    messages=[
        {
            "role": "developer",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "Hello!"
        }
    ]
)

print(completion.choices[0].message)