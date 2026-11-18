import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from activities import fetch_cnblue_news
from shared import TASK_QUEUE
from workflows import CNBlueNewsWorkflow


async def main() -> None:
    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[CNBlueNewsWorkflow],
        activities=[fetch_cnblue_news],
    )
    print(f"Worker started, listening on task queue '{TASK_QUEUE}'...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
