"""Pure constants (safe to import from workflow code)."""

# 一種 workflow = 一個 task queue = 一組獨立的 worker Deployment
CHAT_QUEUE = "chat-orchestration"   # (1) 使用者問題路由 + summary（低延遲，最高優先）
GOLDEN_QUEUE = "golden-set-etl"     # (2) log 清洗 + golden set（批次、可 re-run）
SIM_QUEUE = "agent-simulation"      # (3) mock agent 模擬測試（批次、大量 LLM 呼叫）
