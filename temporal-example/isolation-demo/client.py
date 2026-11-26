"""Trigger workflows. 每種 workflow 都明確指定自己的 task queue。

    python client.py chat "How do I get a refund for my invoice?"
    python client.py golden --dataset demo --version v1            # 事件觸發（冪等）
    python client.py golden --dataset demo --version v1 --rerun 2  # 整批重做：換 workflow ID
    python client.py golden --dataset demo --version v1 --rerun 2 --force
    python client.py simulate --dataset demo --golden-version v1 --variant mock-flaky
"""
import argparse
import asyncio
import time
import uuid
from dataclasses import asdict

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from chat.workflows import ChatOrchestrationWorkflow
from common import settings
from common.models import ChatRequest, GoldenSetRequest, SimulationRequest
from common.names import CHAT_QUEUE, GOLDEN_QUEUE, SIM_QUEUE
from golden.workflows import GoldenSetWorkflow
from simulation.workflows import SimulationWorkflow


async def run_chat(client: Client, args) -> None:
    result = await client.execute_workflow(
        ChatOrchestrationWorkflow.run,
        ChatRequest(question=args.question),
        id=f"chat-{uuid.uuid4()}",
        task_queue=CHAT_QUEUE,
    )
    print(result.summary)
    print("agents:", result.agents)


async def run_golden(client: Client, args) -> None:
    # Workflow ID 由「資料集 + 版本」決定 => 同一個事件重複送達不會重複啟動。
    workflow_id = f"golden-{args.dataset}-{args.version}" + (f"-r{args.rerun}" if args.rerun else "")
    try:
        handle = await client.start_workflow(
            GoldenSetWorkflow.run,
            GoldenSetRequest(dataset=args.dataset, version=args.version, force=args.force),
            id=workflow_id,
            task_queue=GOLDEN_QUEUE,
            # 只有「失敗」的才允許用同一個 ID 再啟動；成功的/執行中的會被擋下 = 冪等
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
        )
    except WorkflowAlreadyStartedError:
        print(f"{workflow_id} already exists (running or completed) -> skipped. Use --rerun N to redo.")
        return
    print(f"started {workflow_id}; waiting...")
    print(await handle.result())  # 預設會跟著 Continue-As-New 的後續 run


async def run_simulation(client: Client, args) -> None:
    workflow_id = f"sim-{args.dataset}-{args.golden_version}-{args.variant}-{int(time.time())}"
    result = await client.execute_workflow(
        SimulationWorkflow.run,
        SimulationRequest(
            dataset=args.dataset,
            golden_version=args.golden_version,
            agent_variant=args.variant,
        ),
        id=workflow_id,
        task_queue=SIM_QUEUE,
    )
    print(asdict(result))


async def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("chat")
    p.add_argument("question")

    p = sub.add_parser("golden")
    p.add_argument("--dataset", default="demo")
    p.add_argument("--version", default="v1")
    p.add_argument("--rerun", type=int, default=0, help="N>0: workflow ID 加 -rN，整批重做")
    p.add_argument("--force", action="store_true", help="已存在的輸出也覆寫重做")

    p = sub.add_parser("simulate")
    p.add_argument("--dataset", default="demo")
    p.add_argument("--golden-version", default="v1")
    p.add_argument("--variant", default="mock-good", choices=["mock-good", "mock-flaky"])

    args = parser.parse_args()
    client = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
    await {"chat": run_chat, "golden": run_golden, "simulate": run_simulation}[args.cmd](client, args)


if __name__ == "__main__":
    asyncio.run(main())
