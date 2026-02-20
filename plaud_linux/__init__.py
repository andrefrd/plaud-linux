"""
Plaud Linux - Gravador de audio com upload automatico para web.plaud.ai
"""

import subprocess
import sys
import os

from plaud_linux.recorder import AudioRecorder
from plaud_linux.uploader import PlaudUploader
from plaud_linux.cli import PlaudCLI


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


def main():
    ensure_dirs()
    check_dependencies()

    recorder = AudioRecorder(RECORDINGS_DIR)
    uploader = PlaudUploader(SESSION_DIR)

    if not uploader.has_session():
        print("Primeira execucao - abrindo navegador para login no web.plaud.ai...")
        print("Faca login via Google SSO e feche o navegador quando terminar.")
        uploader.interactive_login()
        print("Sessao salva! Proximas execucoes serao automaticas.")

    app = PlaudCLI(recorder=recorder, uploader=uploader)
    app.run()


if __name__ == "__main__":
    main()
