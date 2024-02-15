import asyncio
import nats
from nat_controller import NatController

async def main():
    subject = "food"
    controller = NatController()
    controller.connect("nat://localhost:4222")
    maxCount = 10

    await controller.pull(subject=subject, handler=handleMessage)
    await controller.flush()
    while True:
        print("listening...")
        

async def handleMessage(msg):
    subject = msg.subject
    reply = msg.reply
    data = msg.data.decode()
    print('Received a message on {subject} {reply}: {data}'.format(
        subject=subject, reply=reply, data=data))

if __name__ == '__main__':
    asyncio.run(main())