"""Pure, deterministic stand-ins for the LLM router / domain agents.

正式專案：
  - route()  -> 呼叫 LiteLLM 做意圖分類（用 chat 專用 virtual key）
  - answer() -> create_deep_agent(...).ainvoke(...)
(3) 模擬測試用 VARIANTS 裡的 mock，不接任何有副作用的真實工具。
"""
import zlib

KEYWORDS = {
    "billing": ("invoice", "refund", "payment", "發票", "退款", "付款"),
    "hr": ("leave", "salary", "onboarding", "請假", "薪資", "到職"),
    "it-support": ("vpn", "password", "laptop", "密碼", "電腦", "網路"),
}


def route(question: str) -> list:
    q = question.lower()
    hits = [agent for agent, kws in KEYWORDS.items() if any(k in q for k in kws)]
    return hits or ["general"]


def flaky_route(question: str) -> list:
    """Deterministically misroutes ~1/3 of questions (crc32 is stable across processes,
    unlike Python's salted hash())."""
    if zlib.crc32(question.encode("utf-8")) % 3 == 0:
        return ["general"]
    return route(question)


def answer(agent: str, question: str) -> str:
    return f"[{agent}] handled: {question[:80]}"


VARIANTS = {
    "mock-good": route,
    "mock-flaky": flaky_route,
}
