import asyncio
import nats
from datetime import datetime
import time
from nat_controller import NatController


async def main():
    stream = "myStream"
    subject = "food"
    controller = NatController()
    connected = await controller.connect("nats://localhost:4222")
    print(f'connect: {connected}')

    stream_obj = await controller.add_stream_subject(stream, [subject])

    print(stream_obj)

    maxCount = 20

    while maxCount > 0:
        msg_payload = f"send message: {datetime.now().strftime('%Y-%m-%d-%H:%M:%S')}"
        await controller.publish(
            subject, 
            msg_payload,
            stream)
        await controller.ns.flush()
        print(msg_payload)
        time.sleep(5)
        maxCount -= 1

    await controller.close()

if __name__ == '__main__':
    asyncio.run(main())
