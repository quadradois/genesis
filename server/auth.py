"""Token de acesso da Web UI e verificação de origem."""
import json
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def save_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_or_create_token() -> str:
    cfg = load_config()
    tok = cfg.get("web_token", "")
    if not tok:
        tok = secrets.token_hex(16)
        cfg["web_token"] = tok
        save_config(cfg)
    return tok


def is_local(host: str | None) -> bool:
    return host in _LOCAL_HOSTS


def check_access(host: str | None, token: str | None) -> bool:
    if is_local(host):
        return True
    if not token:
        return False
    return secrets.compare_digest(token, get_or_create_token())
