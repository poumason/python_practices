import asyncio
import sys
import uuid

from temporalio.client import Client

from shared import TASK_QUEUE
from workflows import CNBlueNewsWorkflow


async def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "CNBLUE news"

    client = await Client.connect("localhost:7233")
    result = await client.execute_workflow(
        CNBlueNewsWorkflow.run,
        query,
        id=f"cnblue-news-{uuid.uuid4()}",
        task_queue=TASK_QUEUE,
    )
    print(f"CSV written to: {result}")


if __name__ == "__main__":
    asyncio.run(main())
