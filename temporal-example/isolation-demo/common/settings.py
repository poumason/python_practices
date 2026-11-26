"""Runtime settings (read from env). Do NOT import this from workflow code."""
import os

TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")

# 本機資料夾，模擬 object storage（MinIO / S3）。正式環境換成 bucket。
DATA_DIR = os.getenv(
    "DEMO_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)
