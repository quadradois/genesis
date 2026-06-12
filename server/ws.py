"""Hub de conexões WebSocket com broadcast thread-safe."""
import asyncio
import threading


class Hub:
    def __init__(self):
        self._conns: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def register(self, ws) -> None:
        with self._lock:
            self._conns.add(ws)

    async def unregister(self, ws) -> None:
        with self._lock:
            self._conns.discard(ws)

    async def _broadcast(self, payload: dict) -> None:
        with self._lock:
            conns = list(self._conns)
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.unregister(ws)

    def broadcast(self, payload: dict) -> None:
        """Pode ser chamado de qualquer thread; melhor esforço."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), loop)
