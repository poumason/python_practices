"""One entrypoint, three isolated worker roles.

    python worker.py chat         # task queue: chat-orchestration
    python worker.py golden       # task queue: golden-set-etl
    python worker.py simulation   # task queue: agent-simulation

k8s 上是「同一個 image、三個 Deployment」，用 WORKER_ROLE 環境變數決定角色。
每個角色只 import 自己的 workflow / activity 程式碼，所以：
  - chat worker 的 image/process 裡根本沒有批次邏輯，批次程式碼改動不會碰到它
  - 每個角色各自的並行上限（MAX_CONCURRENT_*）互不影響
"""
import argparse
import asyncio
import importlib
import os
import signal
from datetime import timedelta

from temporalio.client import Client
from temporalio.worker import Worker

from common import settings
from common.names import CHAT_QUEUE, GOLDEN_QUEUE, SIM_QUEUE

# role -> (task queue, workflow "module:Class" list, activity module, default max concurrent activities)
ROLES = {
    "chat": (CHAT_QUEUE, ["chat.workflows:ChatOrchestrationWorkflow"], "chat.activities", 100),
    "golden": (GOLDEN_QUEUE, ["golden.workflows:GoldenSetWorkflow"], "golden.activities", 10),
    "simulation": (SIM_QUEUE, ["simulation.workflows:SimulationWorkflow"], "simulation.activities", 5),
}


def _load(spec: str):
    module, name = spec.split(":")
    return getattr(importlib.import_module(module), name)


def build_worker(client: Client, role: str) -> Worker:
    queue, workflow_specs, activity_module, default_activities = ROLES[role]
    mod = importlib.import_module(activity_module)
    activities = [
        fn for fn in vars(mod).values() if callable(fn) and hasattr(fn, "__temporal_activity_definition")
    ]
    return Worker(
        client,
        task_queue=queue,
        workflows=[_load(s) for s in workflow_specs],
        activities=activities,
        max_concurrent_activities=int(os.getenv("MAX_CONCURRENT_ACTIVITIES", default_activities)),
        max_concurrent_workflow_tasks=int(os.getenv("MAX_CONCURRENT_WORKFLOW_TASKS", "50")),
        graceful_shutdown_timeout=timedelta(seconds=int(os.getenv("GRACEFUL_SHUTDOWN_SECONDS", "30"))),
    )


async def main(role: str) -> None:
    client = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
    worker = build_worker(client, role)
    queue = ROLES[role][0]
    print(f"[{role}] worker up: queue={queue} namespace={settings.TEMPORAL_NAMESPACE} at {settings.TEMPORAL_ADDRESS}")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):  # k8s 滾動更新送 SIGTERM：讓進行中的 activity 先收尾
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(worker.shutdown()))
    await worker.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("role", nargs="?", default=os.getenv("WORKER_ROLE"), choices=sorted(ROLES))
    args = parser.parse_args()
    if not args.role:
        parser.error("role required (arg or WORKER_ROLE env)")
    asyncio.run(main(args.role))
