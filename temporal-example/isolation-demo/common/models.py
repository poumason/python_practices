"""Dataclasses passed in/out of workflows and activities.

只放「小」的東西（參照、計數、摘要）。大資料一律寫到 storage，只傳 key。
Python 3.9 相容：用 Optional，不用 `X | None`。
"""
from dataclasses import dataclass


# ---- (1) chat -------------------------------------------------------------
@dataclass
class ChatRequest:
    question: str
    user_id: str = "anonymous"


@dataclass
class AgentResult:
    agent: str
    answer: str


@dataclass
class ChatResponse:
    agents: list
    summary: str


# ---- (2) golden set -------------------------------------------------------
@dataclass
class GoldenSetRequest:
    dataset: str
    version: str
    offset: int = 0      # Continue-As-New 時帶到下一段
    processed: int = 0   # Continue-As-New 時帶到下一段
    force: bool = False  # True = 已存在的輸出也重做（覆寫）


@dataclass
class CleanBatchResult:
    batch_id: str
    read: int
    kept: int
    skipped_existing: bool


@dataclass
class ManifestInfo:
    manifest_key: str
    batches: int
    cases: int


@dataclass
class GoldenSetResult:
    dataset: str
    version: str
    batches: int
    cases: int
    manifest_key: str


# ---- (3) simulation -------------------------------------------------------
@dataclass
class SimulationRequest:
    dataset: str
    golden_version: str
    agent_variant: str = "mock-good"
    max_parallel: int = 3


@dataclass
class BatchSimResult:
    batch_id: str
    total: int
    passed: int


@dataclass
class SimulationResult:
    run_id: str
    dataset: str
    golden_version: str
    agent_variant: str
    total: int
    passed: int
    pass_rate: float
    report_key: str
