"""FastAPI da Web UI do Nox: WebSocket de eventos, REST e arquivos estáticos."""
import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    FastAPI, File, Header, HTTPException, Query, Request,
    UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from server import auth

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "webui" / "dist"
UPLOAD_DIR = BASE_DIR / "home" / "uploads"

_WIN_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)

_PLACEHOLDER = """<!DOCTYPE html><html><body style="background:#020611;color:#9fd8ee;
font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh">
<div><h1>NOX</h1><p>Build da interface ausente. Rode: <code>cd webui && npm install && npm run build</code></p></div>
</body></html>"""


def _client_host(request_or_ws) -> str | None:
    client = getattr(request_or_ws, "client", None)
    return client.host if client else None


def create_app(ui) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        ui.hub.attach_loop(asyncio.get_running_loop())
        yield

    app = FastAPI(title="Nox Web UI", lifespan=_lifespan)

    def _require_access(request_or_ws, token: str | None) -> None:
        if not auth.check_access(_client_host(request_or_ws), token):
            raise HTTPException(status_code=401, detail="token inválido")

    async def _json_body(request: Request) -> dict:
        try:
            return await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido")

    # ---------- WebSocket ----------

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket, token: str | None = Query(default=None)):
        if not auth.check_access(_client_host(ws), token):
            await ws.close(code=4401)
            return
        await ws.accept()
        await ui.hub.register(ws)
        try:
            await ws.send_json(ui.hello())
            while True:
                frame = await ws.receive()
                if frame.get("type") == "websocket.disconnect":
                    break
                if "bytes" in frame and frame["bytes"] is not None:
                    ui.handle_phone_audio(ws, frame["bytes"])
                    continue
                if "text" not in frame or frame["text"] is None:
                    continue
                try:
                    data = json.loads(frame["text"])
                except json.JSONDecodeError:
                    continue
                t = data.get("t")
                if t == "message":
                    ui._handle_user_text(data.get("text", ""))
                elif t == "mute":
                    ui.muted = bool(data.get("muted"))
                elif t == "audio_source":
                    ok = ui.set_audio_source(data.get("source", "pc"), ws)
                    if not ok:
                        await ws.send_json({
                            "t": "err",
                            "message": "phone audio already active on another client",
                        })
                elif t == "dev_tools":
                    from memory.config_manager import set_code_execution_allowed
                    enabled = bool(data.get("enabled"))
                    set_code_execution_allowed(enabled)
                    ui._emit({"t": "dev_tools", "enabled": enabled})
                    ui.write_log(
                        "SYS: Dev tools enabled — generated code may run."
                        if enabled else
                        "SYS: Dev tools disabled — generated code blocked."
                    )
        except WebSocketDisconnect:
            pass
        finally:
            ui.release_audio_source(ws)
            await ui.hub.unregister(ws)

    # ---------- REST ----------

    @app.post("/api/message")
    async def post_message(request: Request, x_nox_token: str | None = Header(default=None)):
        _require_access(request, x_nox_token)
        body = await _json_body(request)
        text = str(body.get("text", ""))
        if not text.strip():
            raise HTTPException(status_code=422, detail="texto vazio")
        ui._handle_user_text(text)
        return {"ok": True}

    @app.get("/api/config")
    async def get_config(request: Request, x_nox_token: str | None = Header(default=None)):
        _require_access(request, x_nox_token)
        cfg = auth.load_config()
        return {
            "setup_complete": bool(cfg.get("os_system")) and bool(
                cfg.get("gemini_api_key") or cfg.get("openrouter_api_key") or cfg.get("moonshot_api_key")
            ),
            "has_gemini": bool(cfg.get("gemini_api_key")),
            "has_openrouter": bool(cfg.get("openrouter_api_key")),
            "os_system": cfg.get("os_system", ""),
        }

    @app.post("/api/config")
    async def post_config(request: Request, x_nox_token: str | None = Header(default=None)):
        _require_access(request, x_nox_token)
        body = await _json_body(request)
        cfg = auth.load_config()
        for key in ("gemini_api_key", "openrouter_api_key", "os_system"):
            val = str(body.get(key, "") or "").strip()
            if val:
                cfg[key] = val
        auth.save_config(cfg)
        ui.notify_config_saved()
        return {"ok": True}

    @app.post("/api/upload")
    async def upload(request: Request, file: UploadFile = File(...), x_nox_token: str | None = Header(default=None)):
        _require_access(request, x_nox_token)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = Path(file.filename or "arquivo").name
        if not safe_name or _WIN_RESERVED.match(safe_name):
            safe_name = f"upload_{safe_name or 'file'}"
        dest = UPLOAD_DIR / safe_name
        n = 1
        while dest.exists():
            dest = UPLOAD_DIR / f"{Path(safe_name).stem}_{n}{Path(safe_name).suffix}"
            n += 1
        dest.write_bytes(await file.read())
        ui.register_upload(dest)
        return {"ok": True, "path": str(dest)}

    # ---------- estáticos ----------

    if DIST_DIR.exists():
        app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

        @app.get("/")
        async def index():
            return FileResponse(DIST_DIR / "index.html")
    else:
        @app.get("/")
        async def index():
            return HTMLResponse(_PLACEHOLDER)

    return app
