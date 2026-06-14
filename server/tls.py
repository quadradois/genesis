"""Certificado HTTPS local para acesso mobile."""
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TLS_DIR = BASE_DIR / "config" / "tls"
CERT_PATH = TLS_DIR / "nox-local.crt"
KEY_PATH = TLS_DIR / "nox-local.key"


def ensure_local_cert(ip: str) -> tuple[Path, Path]:
    """Cria um certificado self-signed com SAN para localhost e o IP LAN."""
    if CERT_PATH.exists() and KEY_PATH.exists():
        return CERT_PATH, KEY_PATH

    TLS_DIR.mkdir(parents=True, exist_ok=True)
    san = f"DNS:localhost,IP:127.0.0.1,IP:{ip}"
    cmd = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(KEY_PATH),
        "-out", str(CERT_PATH),
        "-sha256", "-days", "365",
        "-subj", "/CN=Nox Local",
        "-addext", f"subjectAltName={san}",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("openssl não encontrado; instale OpenSSL ou rode sem --https") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"falha ao gerar certificado HTTPS: {detail}") from exc
    return CERT_PATH, KEY_PATH
