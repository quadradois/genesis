import asyncio
import threading

from server.ws import Hub


class FakeWS:
    def __init__(self):
        self.sent = []
        self.fail = False

    async def send_json(self, payload):
        if self.fail:
            raise RuntimeError("conexão morta")
        self.sent.append(payload)


def test_broadcast_sem_loop_nao_explode():
    hub = Hub()
    hub.broadcast({"t": "state", "state": "LISTENING"})  # não deve lançar


def test_broadcast_entrega_e_remove_mortas():
    async def run():
        hub = Hub()
        hub.attach_loop(asyncio.get_running_loop())
        ok, dead = FakeWS(), FakeWS()
        dead.fail = True
        await hub.register(ok)
        await hub.register(dead)
        await hub._broadcast({"t": "chat", "role": "sys", "text": "oi"})
        assert ok.sent == [{"t": "chat", "role": "sys", "text": "oi"}]
        assert dead not in hub._conns
    asyncio.run(run())


def test_broadcast_de_outra_thread_entrega():
    async def run():
        hub = Hub()
        hub.attach_loop(asyncio.get_running_loop())
        ok = FakeWS()
        await hub.register(ok)
        t = threading.Thread(target=hub.broadcast, args=({"t": "viz", "level": 0.5},))
        t.start()
        t.join()
        for _ in range(50):
            if ok.sent:
                break
            await asyncio.sleep(0.01)
        assert ok.sent == [{"t": "viz", "level": 0.5}]
    asyncio.run(run())
