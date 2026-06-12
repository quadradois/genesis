"""Casca desktop do Nox: janela pywebview (WebView2) com fallback para o navegador."""
import time
import webbrowser


def run_window(url: str) -> None:
    try:
        import webview  # pywebview
        webview.create_window(
            "NOX",
            url,
            width=1100,
            height=720,
            min_size=(420, 580),
            background_color="#020611",
        )
        webview.start()
    except Exception as e:
        print(f"[NOX] pywebview indisponível ({e}); abrindo no navegador padrão.")
        print("[NOX] Instale o runtime WebView2 da Microsoft para usar a janela nativa.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")
