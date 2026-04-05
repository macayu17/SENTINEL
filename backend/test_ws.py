import asyncio
import websockets

async def test():
    async with websockets.connect('ws://127.0.0.1:8001/ws') as ws:
        print(await ws.recv())

asyncio.run(test())
