import asyncio

from temporalio import activity

from common import mock_agents
from common.models import AgentResult


@activity.defn
async def route_question(question: str) -> list:
    """Decide which domain agents should handle the question.

    正式專案：呼叫 LiteLLM 做意圖分類。LLM 呼叫是非確定性的，所以一定放在 Activity，
    不能放在 Workflow（Workflow 必須 deterministic，replay 時才會一致）。
    """
    await asyncio.sleep(0.05)
    return mock_agents.route(question)


@activity.defn
async def run_domain_agent(agent: str, question: str) -> AgentResult:
    """Run one domain agent.

    正式專案：create_deep_agent(...).ainvoke({"messages": [...]})。
    注意：deep agent 的 todo / 虛擬檔案系統 / 完整對話不要放進回傳值，
    只回傳最終答案（或寫 storage 回傳 key），否則會堆在 Event History。
    """
    await asyncio.sleep(0.1)
    return AgentResult(agent=agent, answer=mock_agents.answer(agent, question))


@activity.defn
async def summarize(question: str, results: list) -> str:
    """Merge agent outputs into one reply (正式專案：再呼叫一次 LLM)。"""
    parts = [f"{r.agent}: {r.answer}" for r in results]
    return f"Q: {question}\n" + "\n".join(parts)
