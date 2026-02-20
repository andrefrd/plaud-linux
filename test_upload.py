#!/usr/bin/env python3
"""
Script temporario para testar APENAS o upload RPA.
Usa o ultimo MP3 gravado (ou um especificado) para testar o fluxo completo.
"""

import sys
import os
import glob

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plaud_linux.uploader import PlaudUploader

SESSION_DIR = os.path.expanduser("~/.plaud-linux/session")
RECORDINGS_DIR = os.path.expanduser("~/.plaud-linux/recordings")


def main():
    # Pegar o arquivo MP3 (argumento ou ultimo gravado)
    if len(sys.argv) > 1:
        mp3_path = sys.argv[1]
    else:
        files = sorted(glob.glob(os.path.join(RECORDINGS_DIR, "*.mp3")))
        if not files:
            print("Nenhum MP3 encontrado em ~/.plaud-linux/recordings/")
            return
        mp3_path = files[-1]  # ultimo arquivo

    print(f"Arquivo: {mp3_path}")
    print(f"Tamanho: {os.path.getsize(mp3_path) / 1024 / 1024:.1f} MB")
    print()

    uploader = PlaudUploader(SESSION_DIR)

    if not uploader.has_session():
        print("Sem sessao salva. Abrindo browser para login...")
        uploader.interactive_login()

    print("Iniciando upload (headless=False para debug)...")
    print("Observe o navegador abrir e acompanhe o processo.")
    print()

    success = uploader.upload(mp3_path)

    if success:
        print("\n=== UPLOAD OK ===")
    else:
        print("\n=== UPLOAD FALHOU ===")
        print(f"Arquivo continua em: {mp3_path}")


if __name__ == "__main__":
    main()
