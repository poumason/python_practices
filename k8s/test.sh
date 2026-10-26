curl -X POST 'http://127.0.0.1:4000/v1/chat/completions' \
-H 'Content-Type: application/json' \
-H 'Authorization: Bearer sk-1234' \
-d '{
    "model": "qwen3:0.6b",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me a joke."}
    ]
}'
{
  "model_name": "qwen3:0.6b",
  "litellm_params": {
    "api_key": "",
    "api_base": "http://0.0.0.0:11434",
    "configurable_clientside_auth_params": [
      "string",
      {
        "api_base": "string",
        "api_key": "none"
      }
    ],
    "model": "ollama/qwen3:0.6b"
  }
}