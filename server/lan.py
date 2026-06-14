"""Acesso pela rede local (preview do M4): IP local, URL de pareamento e QR ASCII."""
import socket

from server.auth import get_or_create_token


def local_ip() -> str:
    """IP desta máquina na rede local (sem enviar pacotes de fato)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def pairing_url(port: int, scheme: str = "http") -> str:
    return f"{scheme}://{local_ip()}:{port}/?token={get_or_create_token()}"


def print_pairing(port: int, scheme: str = "http") -> None:
    url = pairing_url(port, scheme)
    print(f"[NOX] 📱 Acesso pelo celular (mesma rede Wi-Fi): {url}")
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except Exception:
        print("[NOX] (instale 'qrcode' para ver o QR no terminal: pip install qrcode)")
    print("[NOX] Celular não conecta? Libere a porta no firewall (uma vez, terminal admin):")
    print(f'[NOX]   netsh advfirewall firewall add rule name="Nox Web UI" dir=in action=allow protocol=TCP localport={port}')
    if scheme == "https":
        print("[NOX] No iPhone, aceite/confiar no certificado local se o Safari avisar.")
