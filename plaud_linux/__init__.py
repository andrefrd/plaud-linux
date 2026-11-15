"""
Plaud Linux - Gravador de audio com upload automatico para web.plaud.ai
"""

import subprocess
import sys
import os

# Imports pesados (playwright) ficam dentro dos entry points: o
# plaud-ilha-watchd importa o pacote e deve rodar só com a stdlib.


SESSION_DIR = os.path.expanduser("~/.plaud-linux/session")
RECORDINGS_DIR = os.path.expanduser("~/.plaud-linux/recordings")


def ensure_dirs():
    os.makedirs(SESSION_DIR, exist_ok=True)
    os.makedirs(RECORDINGS_DIR, exist_ok=True)


def check_dependencies():
    """Verifica se ffmpeg e pactl estao instalados."""
    missing = []
    for cmd in ["ffmpeg", "pactl"]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        except FileNotFoundError:
            missing.append(cmd)
    if missing:
        print(f"Erro: Dependencias nao encontradas: {', '.join(missing)}")
        print("Instale com: sudo apt install ffmpeg pulseaudio-utils")
        sys.exit(1)


def check_playwright():
    """Garante que o Chromium do Playwright está instalado."""
    # Cada versão do playwright exige uma revisão própria do Chromium; checar
    # só "existe algum chromium-*" deixava o upload quebrado após um upgrade.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            has_chromium = os.path.exists(p.chromium.executable_path)
    except Exception:
        has_chromium = False

    if not has_chromium:
        print("Navegador Chromium para o Playwright nao detectado.")
        print("Instalando Chromium automaticamente (isso ocorre apenas na primeira execucao)...")
        try:
            from playwright.cli.main import main as playwright_main
            try:
                playwright_main(["install", "chromium"])
            except SystemExit as e:
                if e.code != 0:
                    raise
        except Exception as e:
            print(f"Erro ao instalar via modulo interno: {e}. Tentando via subprocesso...")
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("Instalacao do Chromium concluida com sucesso.")


def main():
    """Entry point principal — modo CLI (terminal)."""
    from plaud_linux.recorder import AudioRecorder
    from plaud_linux.uploader import PlaudUploader
    from plaud_linux.cli import PlaudCLI

    ensure_dirs()
    check_dependencies()
    check_playwright()

    recorder = AudioRecorder(RECORDINGS_DIR)
    uploader = PlaudUploader(SESSION_DIR)

    if not uploader.has_session():
        print("Primeira execucao - abrindo navegador para login no web.plaud.ai...")
        print("Faca login via Google SSO e feche o navegador quando terminar.")
        uploader.interactive_login()
        print("Sessao salva! Proximas execucoes serao automaticas.")

    app = PlaudCLI(recorder=recorder, uploader=uploader)
    app.run()


def main_tray():
    """Entry point para modo System Tray (GNOME/Wayland/X11)."""
    from plaud_linux.recorder import AudioRecorder
    from plaud_linux.uploader import PlaudUploader

    ensure_dirs()
    check_dependencies()
    check_playwright()

    recorder = AudioRecorder(RECORDINGS_DIR)
    uploader = PlaudUploader(SESSION_DIR)

    if not uploader.has_session():
        print("Primeira execucao - abrindo navegador para login no web.plaud.ai...")
        print("Faca login via Google SSO e feche o navegador quando terminar.")
        uploader.interactive_login()
        print("Sessao salva!")

    from plaud_linux.tray import PlaudTray
    app = PlaudTray(recorder=recorder, uploader=uploader)
    app.run()


if __name__ == "__main__":
    main()
