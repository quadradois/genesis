import json
import re

from server import auth, lan


def test_pairing_url_tem_ip_porta_e_token(monkeypatch, tmp_path):
    cfg = tmp_path / "api_keys.json"
    cfg.write_text(json.dumps({"web_token": "a" * 32}), encoding="utf-8")
    monkeypatch.setattr(auth, "CONFIG_PATH", cfg)
    url = lan.pairing_url(8765)
    assert re.fullmatch(r"http://\d+\.\d+\.\d+\.\d+:8765/\?token=a{32}", url)


def test_local_ip_e_ipv4():
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", lan.local_ip())
