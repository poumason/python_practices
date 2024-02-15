import asyncio
import nats
from datetime import datetime
import time
from nat_controller import NatController


async def main():
    subject = "food"
    controller = NatController()
    controller.connect("nat://localhost:4222")
    maxCount = 10

    while maxCount > 0:
        await controller.publish(
            subject, f"send message: {datetime.now().strftime('%Y-%m-%d-%H:%M:%S')}")
        # await controller.ns.flush()
        time.sleep(5)
        maxCount -= 1

if __name__ == '__main__':
    asyncio.run(main())
