"""Hub de conexões WebSocket com broadcast thread-safe.

Contrato de threading: `broadcast()` pode ser chamado de qualquer thread;
`attach_loop`, `register`, `unregister` e `_broadcast` pertencem ao loop do
servidor. Entrega é melhor-esforço (sem fila antes do startup).
"""
import asyncio
import logging
import threading
from typing import Protocol

logger = logging.getLogger("nox.web")


class WsLike(Protocol):
    async def send_json(self, payload: dict) -> None: ...


class Hub:
    def __init__(self):
        self._conns: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop

    async def register(self, ws: WsLike) -> None:
        with self._lock:
            self._conns.add(ws)

    async def unregister(self, ws: WsLike) -> None:
        with self._lock:
            self._conns.discard(ws)

    async def _broadcast(self, payload: dict) -> None:
        with self._lock:
            conns = list(self._conns)
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                # CancelledError é BaseException: propaga corretamente.
                await self.unregister(ws)

    def broadcast(self, payload: dict) -> None:
        """Pode ser chamado de qualquer thread; melhor esforço."""
        with self._lock:
            loop = self._loop
        if loop is None or loop.is_closed():
            return
        future = asyncio.run_coroutine_threadsafe(self._broadcast(payload), loop)
        future.add_done_callback(_log_broadcast_failure)


def _log_broadcast_failure(future) -> None:
    try:
        exc = future.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        logger.warning("broadcast falhou: %r", exc)
