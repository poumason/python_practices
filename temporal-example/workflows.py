from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import fetch_cnblue_news


@workflow.defn
class CNBlueNewsWorkflow:
    @workflow.run
    async def run(self, query: str = "CNBLUE") -> str:
        return await workflow.execute_activity(
            fetch_cnblue_news,
            query,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=30),
                maximum_attempts=5,
            ),
        )
