import asyncio
import nats
from nats.js.api import StreamInfo
from nats.js.client import JetStreamContext

class NatController:
    def __init__(self) -> None:
        self.ns = None
        self.sub = None
        self.js = None

    async def connect(self, natUrl) -> bool:
        self.ns = await nats.connect(natUrl,
                                     error_cb=self.__error_cb,
                                     reconnected_cb=self.__reconnected_cb,
                                     disconnected_cb=self.__disconnected_cb,
                                     closed_cb=self.__closed_cb,)
        if self.ns.is_connected:
            self.js = self.ns.jetstream()

        return self.ns.is_connected

    async def close(self):
        await self.ns.close()

    async def add_stream_subject(self, name, subjects) -> StreamInfo:
        if self.js is None:
            return False
        stream_info = await self.js.add_stream(name=name, subjects=subjects)
        return stream_info  

    async def publish(self, subject, payload, stream = None):
        if self.ns == None or self.ns.is_connected == False:
            return
        else:
            if stream is not None:
                await self.ns.publish(subject=subject, payload=payload.encode())
            else:
                await self.js.publish(subject=subject, payload=payload.encode(), stream=stream)

    async def pull(self, subject, handler):
        self.sub = await self.ns.subscribe(subject=subject, cb=handler)
        # self.ns.flush()

    async def pull_subscribe(self, subject, durable = None) -> JetStreamContext.PullSubscription:
        if durable is not None:
            return await self.js.pull_subscribe(subject=subject, durable=durable)
        else:
            return await self.js.pull_subscribe(subject=subject)

    async def handler(self, msg):
        print(f'Received a message on {msg.subject} {msg.reply}: {msg.data}')
        await msg.respond(b'OK')

    async def __disconnected_cb(self):
        print('Got disconnected!')

    async def __reconnected_cb(self):
        print(f'Got reconnected to {self.nc.connected_url.netloc}')

    async def __error_cb(self, e):
        print(f'There was an error: {e}')

    async def __closed_cb(self):
        print('Connection is closed')
