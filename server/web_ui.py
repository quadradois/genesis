"""Adapter WebUI: mesma interface da NoxUI (ui.py), mas emitindo eventos WebSocket."""
import logging
import threading
from collections import deque
from pathlib import Path

from server.auth import load_config
from server.ws import Hub

logger = logging.getLogger("nox.web")

VALID_STATES = {"INITIALISING", "LISTENING", "THINKING", "SPEAKING", "MUTED"}


def parse_log_line(text: str) -> tuple[str, str]:
    """Mapeia os prefixos de log usados pelo backend para papéis de chat."""
    if text.startswith("You:"):
        return "user", text[4:].strip()
    if text.startswith("Nox:"):
        return "nox", text[4:].strip()
    low = text.lower()
    if low.startswith("file:"):
        return "file", text[5:].strip()
    if text.startswith("ERR:"):
        return "err", text[4:].strip()
    if text.startswith("[Err"):
        return "err", text
    if text.startswith("SYS:"):
        return "sys", text[4:].strip()
    return "sys", text


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _config_valida() -> bool:
    d = load_config()
    if not d.get("os_system"):
        return False
    return bool(d.get("gemini_api_key") or d.get("openrouter_api_key") or d.get("moonshot_api_key"))


class WebUI:
    def __init__(self, port: int | None = None, hub: Hub | None = None, start_server: bool = True):
        self.hub = hub or Hub()
        self.port = int(port or load_config().get("web_port", 8765))
        self.on_text_command = None
        self._muted = False
        self._state = "INITIALISING"
        self._current_file: str | None = None
        self.history: deque = deque(maxlen=200)
        self._ready = threading.Event()
        if _config_valida():
            self._ready.set()
        self._server = None
        if start_server:
            self._start_server()

    # ---------- contrato NoxUI ----------

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        if state not in VALID_STATES:
            return
        self._state = state
        self._emit({"t": "state", "state": state})

    def write_log(self, text: str) -> None:
        role, msg = parse_log_line(str(text))
        self._emit({"t": "chat", "role": role, "text": msg})

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, v: bool) -> None:
        v = bool(v)
        if v == self._muted:
            return
        self._muted = v
        self._emit({"t": "mute", "muted": v})
        if v:
            self.set_state("MUTED")
            self.write_log("SYS: Microphone muted.")
        else:
            self.set_state("LISTENING")
            self.write_log("SYS: Microphone active.")

    @property
    def current_file(self) -> str | None:
        return self._current_file

    def wait_for_api_key(self) -> None:
        self._ready.wait()

    def start_speaking(self) -> None:
        self.set_state("SPEAKING")

    def stop_speaking(self) -> None:
        if not self.muted:
            self.set_state("LISTENING")

    # ---------- hooks novos (opcionais para o backend) ----------

    def on_audio_level(self, level: float) -> None:
        # Bypassa _emit de propósito: eventos viz são de alta frequência e não devem entrar no history.
        self.hub.broadcast({"t": "viz", "level": round(float(level), 3)})

    def tool_event(self, name: str, status: str, ms: int | None = None) -> None:
        self._emit({"t": "tool", "name": name, "status": status, "ms": ms})

    # ---------- usados pelo servidor HTTP/WS ----------

    def _emit(self, payload: dict) -> None:
        if payload.get("t") == "chat":
            self.history.append(payload)
        self.hub.broadcast(payload)

    def _dispatch_callback(self, text: str) -> None:
        if not self.on_text_command:
            return

        def _run():
            try:
                self.on_text_command(text)
            except Exception:
                logger.exception("on_text_command falhou para: %.60s", text)

        threading.Thread(target=_run, daemon=True).start()

    def _handle_user_text(self, text: str) -> None:
        text = str(text).strip()
        if not text:
            return
        self.write_log(f"You: {text}")
        self._dispatch_callback(text)

    def register_upload(self, path: Path) -> None:
        path = Path(path)
        try:
            size = _fmt_size(path.stat().st_size)
        except OSError:
            self.write_log(f"[Err] Upload não encontrado: {path.name}")
            return
        self._current_file = str(path)
        self.write_log(f"FILE: {path.name} ({size}) loaded")
        msg = (
            f"[FILE_UPLOADED] path={path} | name={path.name} | "
            f"type={path.suffix.lstrip('.')} | size={size} | "
            f"Briefly tell the user you can see the file '{path.name}' "
            f"({size}) has been uploaded and ask what they'd like to do with it."
        )
        self._dispatch_callback(msg)

    def notify_config_saved(self) -> None:
        os_name = load_config().get("os_system", "windows")
        self.write_log(f"SYS: Initialised. OS={os_name.upper()}. NOX online.")
        self.set_state("LISTENING")
        self._ready.set()

    def hello(self) -> dict:
        from memory.config_manager import code_execution_allowed
        return {
            "t": "hello",
            "state": self._state,
            "muted": self._muted,
            "dev_tools": code_execution_allowed(),
            "setup_complete": _config_valida(),
            "history": list(self.history),
        }

    # ---------- ciclo de vida ----------

    def _start_server(self) -> None:
        import uvicorn
        from server.app import create_app  # import tardio: evita ciclo

        config = uvicorn.Config(
            create_app(self), host="127.0.0.1", port=self.port, log_level="warning"
        )
        self._server = uvicorn.Server(config)
        threading.Thread(target=self._server.run, daemon=True).start()

    def run_forever(self) -> None:
        from desktop import run_window
        run_window(f"http://127.0.0.1:{self.port}")
