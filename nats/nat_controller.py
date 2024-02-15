import asyncio
import nats


class NatController:
    def __init__(self) -> None:
        self.ns = None
        self.sub = None

    async def connect(self, natUrl) -> bool:
        self.ns = await nats.connect(natUrl,
                                     error_cb=self.error_cb,
                                     reconnected_cb=self.reconnected_cb,
                                     disconnected_cb=self.disconnected_cb,
                                     closed_cb=self.closed_cb,)
        return self.ns.is_connected

    async def close(self):
        await self.ns.close()

    async def publish(self, subject, payload):
        if self.ns == None or self.ns.is_connected == False:
            return
        else:
            await self.ns.publish(subject=subject, payload=payload)

    async def pull(self, subject, handler):
        self.sub = await self.ns.subscribe(subject=subject, cb=handler)
        # self.ns.flush()

    async def handler(self, msg):
        print(f'Received a message on {msg.subject} {msg.reply}: {msg.data}')
        await msg.respond(b'OK')

    async def disconnected_cb(self):
        print('Got disconnected!')

    async def __reconnected_cb(self):
        print(f'Got reconnected to {self.nc.connected_url.netloc}')

    async def __error_cb(self, e):
        print(f'There was an error: {e}')

    async def __closed_cb(self):
        print('Connection is closed')
