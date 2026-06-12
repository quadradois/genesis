import json
import re

from server import auth


def _use_tmp_config(monkeypatch, tmp_path, initial=None):
    cfg = tmp_path / "api_keys.json"
    if initial is not None:
        cfg.write_text(json.dumps(initial), encoding="utf-8")
    monkeypatch.setattr(auth, "CONFIG_PATH", cfg)
    return cfg


def test_get_or_create_token_cria_e_persiste(monkeypatch, tmp_path):
    cfg = _use_tmp_config(monkeypatch, tmp_path, {"gemini_api_key": "abc"})
    tok = auth.get_or_create_token()
    assert re.fullmatch(r"[0-9a-f]{32}", tok)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["web_token"] == tok
    assert data["gemini_api_key"] == "abc"  # preserva chaves existentes
    assert auth.get_or_create_token() == tok  # idempotente


def test_get_or_create_token_sem_config_previo(monkeypatch, tmp_path):
    _use_tmp_config(monkeypatch, tmp_path)  # arquivo nem existe
    tok = auth.get_or_create_token()
    assert re.fullmatch(r"[0-9a-f]{32}", tok)


def test_is_local():
    assert auth.is_local("127.0.0.1") is True
    assert auth.is_local("::1") is True
    assert auth.is_local("192.168.0.10") is False
    assert auth.is_local(None) is False


def test_check_access(monkeypatch, tmp_path):
    _use_tmp_config(monkeypatch, tmp_path)
    tok = auth.get_or_create_token()
    assert auth.check_access("127.0.0.1", None) is True          # local dispensa token
    assert auth.check_access("192.168.0.10", tok) is True        # token correto
    assert auth.check_access("192.168.0.10", "errado") is False  # token errado
    assert auth.check_access("192.168.0.10", None) is False      # sem token
