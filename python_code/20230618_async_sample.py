import asyncio
import requests
import timeit
import threading


def _invoke_api():
    print('thread id:', threading.get_ident())
    url = 'https://data.taipei/api/v1/dataset/cba4734b-3693-46cc-bcc1-61cac76386b9?scope=resourceAquire'
    response = requests.get(url, json={
        'resource_id': 'cba4734b-3693-46cc-bcc1-61cac76386b9'
    }, verify=False)
    print(response.json()['result']['results'][0])


async def sub_function(index: int, loop:asyncio.AbstractEventLoop):
    print(index, 'entry sub function')
    await asyncio.to_thread(_invoke_api)
    # future = loop.run_in_executor(None, _invoke_api)
    # await asyncio.wait_for(future, timeout=3, loop=loop)
    print('leave sub function')


async def main():
    loop = asyncio.get_event_loop()
    # task = loop.create_task(_invoke_api())
    # await asyncio.gather(_invoke_api())
    task = []
    # for i in range(0, 5):
    #     task.append(asyncio.create_task(sub_function(i)))
    task.append(sub_function(1, loop))
    await asyncio.gather(*task)


if __name__ == '__main__':
    start = timeit.default_timer()
    asyncio.run(main())
    end = timeit.default_timer()
    print(start, end, end-start)
