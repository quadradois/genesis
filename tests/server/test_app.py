import json
import threading

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import auth
from server.web_ui import WebUI
from server.app import create_app
import server.app as app_mod


@pytest.fixture()
def env(monkeypatch, tmp_path):
    cfg = tmp_path / "api_keys.json"
    cfg.write_text(json.dumps({"os_system": "windows", "gemini_api_key": "k"}), encoding="utf-8")
    monkeypatch.setattr(auth, "CONFIG_PATH", cfg)
    monkeypatch.setattr(app_mod, "UPLOAD_DIR", tmp_path / "uploads")
    ui = WebUI(port=0, start_server=False)
    tok = auth.get_or_create_token()
    # IMPORTANTE: usar context manager — é ele que dispara o evento de startup
    # (que chama hub.attach_loop). Sem `with`, broadcasts nunca chegam e o
    # teste de WS trava esperando para sempre.
    with TestClient(create_app(ui)) as client:
        yield ui, client, tok


def test_ws_exige_token_quando_nao_local(env):
    ui, client, tok = env
    # TestClient conecta como host "testclient" (não-local) → sem token deve recusar
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws"):
            pass
    assert exc_info.value.code == 4401


def test_ws_hello_e_broadcast(env):
    ui, client, tok = env
    with client.websocket_connect(f"/ws?token={tok}") as ws:
        hello = ws.receive_json()
        assert hello["t"] == "hello"
        assert hello["setup_complete"] is True
        ui.write_log("Nox: oi")  # chamada vinda de outra thread (a do teste)
        ev = ws.receive_json()
        assert ev == {"t": "chat", "role": "nox", "text": "oi"}


def test_ws_message_despacha_para_callback(env):
    ui, client, tok = env
    got = threading.Event()
    received = {}
    ui.on_text_command = lambda t: (received.update(t=t), got.set())
    with client.websocket_connect(f"/ws?token={tok}") as ws:
        ws.receive_json()  # hello
        ws.send_json({"t": "message", "text": "olá nox"})
        assert got.wait(timeout=2)
        assert received["t"] == "olá nox"
        echo = ws.receive_json()  # eco do chat do usuário
        assert echo["role"] == "user"


def test_ws_phone_audio_source_recebe_bytes(env):
    ui, client, tok = env
    got = threading.Event()
    received = {}
    ui.on_phone_audio = lambda data: (received.update(data=data), got.set())
    with client.websocket_connect(f"/ws?token={tok}") as ws:
        ws.receive_json()  # hello
        ws.send_json({"t": "audio_source", "source": "phone"})
        ev = ws.receive_json()
        assert ev == {"t": "audio_source", "source": "phone"}
        ws.receive_json()  # log SYS
        ws.send_bytes(b"pcm")
        assert got.wait(timeout=2)
        assert received["data"] == b"pcm"


def test_ws_phone_audio_source_rejeita_segundo_cliente(env):
    ui, client, tok = env
    with client.websocket_connect(f"/ws?token={tok}") as ws1:
        ws1.receive_json()
        ws1.send_json({"t": "audio_source", "source": "phone"})
        ws1.receive_json()
        ws1.receive_json()
        with client.websocket_connect(f"/ws?token={tok}") as ws2:
            ws2.receive_json()
            ws2.send_json({"t": "audio_source", "source": "phone"})
            assert ws2.receive_json()["t"] == "err"


def test_post_message_rest(env):
    ui, client, tok = env
    got = threading.Event()
    ui.on_text_command = lambda t: got.set()
    r = client.post("/api/message", json={"text": "oi"}, headers={"x-nox-token": tok})
    assert r.status_code == 200
    assert got.wait(timeout=2)


def test_post_message_sem_token_recusa(env):
    ui, client, tok = env
    r = client.post("/api/message", json={"text": "oi"})
    assert r.status_code == 401


def test_get_config_nao_vaza_segredos(env):
    ui, client, tok = env
    r = client.get("/api/config", headers={"x-nox-token": tok})
    assert r.status_code == 200
    body = r.json()
    assert body["setup_complete"] is True
    assert body["has_gemini"] is True
    assert "gemini_api_key" not in body


def test_post_config_salva_e_libera_ready(env, monkeypatch):
    ui, client, tok = env
    ui._ready.clear()
    r = client.post(
        "/api/config",
        json={"gemini_api_key": "nova", "os_system": "windows"},
        headers={"x-nox-token": tok},
    )
    assert r.status_code == 200
    assert ui._ready.is_set()
    assert auth.load_config()["gemini_api_key"] == "nova"


def test_upload_salva_e_registra(env):
    ui, client, tok = env
    got = threading.Event()
    ui.on_text_command = lambda t: got.set()
    r = client.post(
        "/api/upload",
        files={"file": ("nota.txt", b"conteudo", "text/plain")},
        headers={"x-nox-token": tok},
    )
    assert r.status_code == 200
    assert ui.current_file and ui.current_file.endswith("nota.txt")
    assert got.wait(timeout=2)


def test_index_sem_dist_mostra_placeholder(env):
    ui, client, tok = env
    r = client.get("/")
    assert r.status_code == 200
    assert "NOX" in r.text


def test_upload_nome_reservado_windows_e_neutralizado(env):
    ui, client, tok = env
    r = client.post(
        "/api/upload",
        files={"file": ("NUL", b"dados reais", "application/octet-stream")},
        headers={"x-nox-token": tok},
    )
    assert r.status_code == 200
    assert ui.current_file is not None
    assert ui.current_file.endswith("upload_NUL")
    from pathlib import Path as _P
    assert _P(ui.current_file).read_bytes() == b"dados reais"


def test_json_malformado_retorna_400(env):
    ui, client, tok = env
    r = client.post(
        "/api/message",
        content=b"{json quebrado",
        headers={"x-nox-token": tok, "content-type": "application/json"},
    )
    assert r.status_code == 400
