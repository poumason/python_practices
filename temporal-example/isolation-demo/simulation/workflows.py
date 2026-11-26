import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from common.models import SimulationRequest, SimulationResult
    from simulation.activities import finalize_report, load_manifest, simulate_batch

_RETRY = RetryPolicy(initial_interval=timedelta(seconds=2), backoff_coefficient=2.0, maximum_attempts=5)


@workflow.defn
class SimulationWorkflow:
    """Run a mock agent against one golden-set *version*.

    刻意不當成 GoldenSetWorkflow 的 child：兩者生命週期不同，
    同一份 golden set 也可能被不同 agent_variant 重複模擬。
    """

    @workflow.run
    async def run(self, req: SimulationRequest) -> SimulationResult:
        run_id = workflow.info().workflow_id  # deterministic，且每次模擬一個獨立輸出路徑

        batch_ids = await workflow.execute_activity(
            load_manifest,
            args=[req.dataset, req.golden_version],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=_RETRY,
        )

        results = []
        for i in range(0, len(batch_ids), req.max_parallel):
            chunk = batch_ids[i : i + req.max_parallel]
            results += await asyncio.gather(
                *[
                    workflow.execute_activity(
                        simulate_batch,
                        args=[req.dataset, req.golden_version, b, req.agent_variant, run_id],
                        start_to_close_timeout=timedelta(minutes=30),
                        retry_policy=_RETRY,
                    )
                    for b in chunk
                ]
            )

        return await workflow.execute_activity(
            finalize_report,
            args=[req.dataset, req.golden_version, req.agent_variant, run_id, list(results)],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=_RETRY,
        )
