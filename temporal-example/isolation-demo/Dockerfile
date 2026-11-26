# 同一個 image，三個 Deployment（用 WORKER_ROLE 決定角色）。
# 想把 image 也拆開時：複製這份，只 COPY 該角色需要的目錄（common/ + 該 workflow 目錄）。
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir temporalio

COPY common/ common/
COPY chat/ chat/
COPY golden/ golden/
COPY simulation/ simulation/
COPY worker.py .

ENV PYTHONUNBUFFERED=1
# 角色由環境變數決定：WORKER_ROLE=chat | golden | simulation
CMD ["python", "worker.py"]
