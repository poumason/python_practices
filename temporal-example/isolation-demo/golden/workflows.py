import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from common.models import GoldenSetRequest, GoldenSetResult
    from golden.activities import clean_batch, list_log_batches, write_manifest

# Demo 用小數字，方便看到 Continue-As-New。
# 正式環境：BATCHES_PER_RUN 要讓單一 run 的 Event History 遠小於上限
# （官方硬上限 51,200 events / 50MB，建議在 ~10k events 前就續跑）。
BATCHES_PER_RUN = 4
MAX_PARALLEL = 3  # 同時清洗的 batch 數：保護資料來源與 LLM，不要壓垮共用資源

_RETRY = RetryPolicy(initial_interval=timedelta(seconds=2), backoff_coefficient=2.0, maximum_attempts=5)


@workflow.defn
class GoldenSetWorkflow:
    """Each run handles a window of batches (fan-out, bounded), then Continue-As-New.

    Workflow ID 建議 = f"golden-{dataset}-{version}"：
      - 同一個事件重複送達 -> 不會重複啟動（冪等觸發）
      - 想整批重做 -> 換 version（或 ID 加 -rN）
      - 只想從失敗處繼續 -> `temporal workflow reset`（見 README）
    """

    @workflow.run
    async def run(self, req: GoldenSetRequest) -> GoldenSetResult:
        batch_ids = await workflow.execute_activity(
            list_log_batches,
            args=[req.dataset, req.offset, BATCHES_PER_RUN],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=_RETRY,
        )

        if not batch_ids:
            info = await workflow.execute_activity(
                write_manifest,
                args=[req.dataset, req.version],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_RETRY,
            )
            return GoldenSetResult(
                dataset=req.dataset,
                version=req.version,
                batches=info.batches,
                cases=info.cases,
                manifest_key=info.manifest_key,
            )

        # Fan-out：每 MAX_PARALLEL 個 batch 一組平行跑；每個 batch 各自重試。
        for i in range(0, len(batch_ids), MAX_PARALLEL):
            chunk = batch_ids[i : i + MAX_PARALLEL]
            await asyncio.gather(
                *[
                    workflow.execute_activity(
                        clean_batch,
                        args=[req.dataset, req.version, batch_id, req.force],
                        start_to_close_timeout=timedelta(minutes=30),
                        heartbeat_timeout=timedelta(minutes=1),
                        retry_policy=_RETRY,
                    )
                    for batch_id in chunk
                ]
            )

        # 清掉這段的 Event History，帶著 cursor 續跑（同一個 Workflow ID，新的 Run ID）。
        workflow.continue_as_new(
            GoldenSetRequest(
                dataset=req.dataset,
                version=req.version,
                offset=req.offset + len(batch_ids),
                processed=req.processed + len(batch_ids),
                force=req.force,
            )
        )
