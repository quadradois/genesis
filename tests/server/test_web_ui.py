import threading

from server.web_ui import WebUI, parse_log_line, _fmt_size


class FakeHub:
    def __init__(self):
        self.events = []
        self.bytes_sent = []

    def broadcast(self, payload):
        self.events.append(payload)

    def send_bytes_threadsafe(self, ws, data):
        self.bytes_sent.append((ws, data))


def make_ui():
    hub = FakeHub()
    ui = WebUI(port=0, hub=hub, start_server=False)
    return ui, hub


def test_parse_log_line():
    assert parse_log_line("You: oi") == ("user", "oi")
    assert parse_log_line("Nox: olá") == ("nox", "olá")
    assert parse_log_line("FILE: a.pdf (2 KB) loaded") == ("file", "a.pdf (2 KB) loaded")
    assert parse_log_line("[Err] deu ruim") == ("err", "[Err] deu ruim")
    assert parse_log_line("ERR: file_controller — boom") == ("err", "file_controller — boom")
    assert parse_log_line("SYS: NOX online.") == ("sys", "NOX online.")
    assert parse_log_line("qualquer coisa") == ("sys", "qualquer coisa")


def test_fmt_size():
    assert _fmt_size(512) == "512 B"
    assert _fmt_size(2048) == "2.0 KB"
    assert _fmt_size(5 * 1024 * 1024) == "5.0 MB"


def test_write_log_emite_chat_e_guarda_historico():
    ui, hub = make_ui()
    ui.write_log("Nox: resposta")
    assert {"t": "chat", "role": "nox", "text": "resposta"} in hub.events
    assert list(ui.history)[-1]["text"] == "resposta"


def test_set_state_emite_e_atualiza():
    ui, hub = make_ui()
    ui.set_state("THINKING")
    assert ui.state == "THINKING"
    assert {"t": "state", "state": "THINKING"} in hub.events


def test_muted_setter_replica_toggle_mute():
    ui, hub = make_ui()
    ui.muted = True
    assert ui.muted is True
    assert {"t": "mute", "muted": True} in hub.events
    assert ui.state == "MUTED"
    assert any(e.get("text") == "Microphone muted." for e in hub.events)
    ui.muted = False
    assert ui.state == "LISTENING"
    ui.muted = False  # repetir não duplica eventos
    assert sum(1 for e in hub.events if e.get("t") == "mute") == 2


def test_handle_user_text_loga_e_despacha_em_thread():
    ui, hub = make_ui()
    got = threading.Event()
    received = {}

    def cb(text):
        received["text"] = text
        got.set()

    ui.on_text_command = cb
    ui._handle_user_text("  abrir bloco de notas  ")
    assert got.wait(timeout=2), "callback não foi chamado"
    assert received["text"] == "abrir bloco de notas"
    assert {"t": "chat", "role": "user", "text": "abrir bloco de notas"} in hub.events


def test_register_upload_seta_current_file_e_despacha(tmp_path):
    ui, hub = make_ui()
    got = threading.Event()
    received = {}
    ui.on_text_command = lambda t: (received.update(msg=t), got.set())
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"x" * 2048)
    ui.register_upload(f)
    assert ui.current_file == str(f)
    assert got.wait(timeout=2)
    assert received["msg"].startswith("[FILE_UPLOADED] path=")
    assert "name=doc.pdf" in received["msg"]
    assert any(e.get("role") == "file" for e in hub.events)


def test_wait_for_api_key_desbloqueia_com_notify():
    ui, hub = make_ui()
    ui._ready.clear()
    done = threading.Event()
    threading.Thread(target=lambda: (ui.wait_for_api_key(), done.set()), daemon=True).start()
    assert not done.wait(timeout=0.3)
    ui.notify_config_saved()
    assert done.wait(timeout=2)
    assert ui.state == "LISTENING"


def test_hooks_opcionais_emitem():
    ui, hub = make_ui()
    ui.on_audio_level(0.5)
    ui.tool_event("file_controller", "ok", 400)
    assert {"t": "viz", "level": 0.5} in hub.events
    assert {"t": "tool", "name": "file_controller", "status": "ok", "ms": 400} in hub.events


def test_register_upload_arquivo_inexistente_nao_explode(tmp_path):
    ui, hub = make_ui()
    ui.register_upload(tmp_path / "nada.pdf")
    assert ui.current_file is None
    assert any(e.get("role") == "err" for e in hub.events)


def test_on_audio_level_throttla_mas_zera_sempre(monkeypatch):
    ui, hub = make_ui()
    clock = {"v": 100.0}
    monkeypatch.setattr("server.web_ui.time.monotonic", lambda: clock["v"])
    ui.on_audio_level(0.5)   # passa (primeiro evento)
    ui.on_audio_level(0.6)   # bloqueado (dentro da janela de 1/30s)
    clock["v"] += 0.05
    ui.on_audio_level(0.7)   # passa (janela vencida)
    ui.on_audio_level(0.0)   # zero passa sempre
    viz = [e for e in hub.events if e["t"] == "viz"]
    assert [v["level"] for v in viz] == [0.5, 0.7, 0.0]


def test_audio_source_phone_roteia_bytes_e_libera():
    ui, hub = make_ui()
    ws = object()
    got = {}
    ui.on_phone_audio = lambda data: got.update(data=data)
    assert ui.set_audio_source("phone", ws) is True
    assert ui.audio_source == "phone"
    ui.handle_phone_audio(ws, b"mic")
    assert got["data"] == b"mic"
    assert ui.send_phone_audio(b"tts") is True
    assert hub.bytes_sent == [(ws, b"tts")]
    ui.release_audio_source(ws)
    assert ui.audio_source == "pc"
