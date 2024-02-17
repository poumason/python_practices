import asyncio
import nats
from nat_controller import NatController

async def main():
    stream = "myStream"
    subject = "food"
    controller = NatController()
    connected = await controller.connect("nats://localhost:4222")
    print(f'connect: {connected}')

    subscriber = await controller.pull_subscribe(subject=subject, durable="mySubscriber")

    while True:
        try:
            msgs = await subscriber.fetch(1)
            for msg in msgs:
                await msg.ack()
                print(f"=== receive message ===\n{msg}\n======")
            if msgs.count == 0:
                print("no message in stream")
                break
        except Exception as e:
            print(e)
            break
    await controller.close()

async def handleMessage(msg):
    subject = msg.subject
    reply = msg.reply
    data = msg.data.decode()
    print('Received a message on {subject} {reply}: {data}'.format(
        subject=subject, reply=reply, data=data))

if __name__ == '__main__':
    asyncio.run(main())