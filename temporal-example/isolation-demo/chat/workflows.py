import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from chat.activities import route_question, run_domain_agent, summarize
    from common.models import ChatRequest, ChatResponse

# 互動式流程：timeout 短、重試次數少，寧可快速失敗也不要讓使用者久等。
_FAST = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=3)


@workflow.defn
class ChatOrchestrationWorkflow:
    """route -> fan-out to domain agents (parallel) -> summarize."""

    @workflow.run
    async def run(self, req: ChatRequest) -> ChatResponse:
        agents = await workflow.execute_activity(
            route_question,
            req.question,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_FAST,
        )

        results = await asyncio.gather(
            *[
                workflow.execute_activity(
                    run_domain_agent,
                    args=[agent, req.question],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=_FAST,
                )
                for agent in agents
            ]
        )

        summary = await workflow.execute_activity(
            summarize,
            args=[req.question, list(results)],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=_FAST,
        )
        return ChatResponse(agents=list(agents), summary=summary)
