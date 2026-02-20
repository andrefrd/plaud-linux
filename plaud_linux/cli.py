"""
Interface interativa via terminal para controlar o Plaud Linux.
Funciona em qualquer distribuição Linux sem depender de system tray.
"""

import threading
import sys
import os

from plaud_linux.recorder import AudioRecorder
from plaud_linux.uploader import PlaudUploader


class PlaudCLI:
    def __init__(self, recorder: AudioRecorder, uploader: PlaudUploader):
        self.recorder = recorder
        self.uploader = uploader
        self._upload_thread = None

    def print_header(self):
        os.system("clear")
        print("=" * 50)
        print("  PLAUD LINUX - Gravador + Upload")
        print("=" * 50)
        print()

    def print_menu(self):
        if self.recorder.is_recording:
            elapsed = self.recorder.get_elapsed()
            mins = elapsed // 60
            secs = elapsed % 60
            print(f"  ** GRAVANDO ** [{mins:02d}:{secs:02d}]")
            print()
            print("  [S] Parar Gravacao")
            print("  [Q] Sair (cancela gravacao)")
        else:
            print("  Opcoes de Gravacao:")
            print("  [1] Gravar Mic + Sistema")
            print("  [2] Gravar apenas Mic")
            print("  [3] Gravar apenas Sistema")
            print()
            print("  Outras opcoes:")
            print("  [L] Login web.plaud.ai")
            print("  [Q] Sair")
        print()

    def handle_stop(self):
        print("\n  Parando gravacao...")
        mp3_path = self.recorder.stop()

        if mp3_path:
            print(f"  MP3 salvo: {mp3_path}")
            print("  Iniciando upload para web.plaud.ai...")

            def do_upload():
                success = self.uploader.upload(mp3_path)
                if success:
                    print("\n  Upload concluido com sucesso!")
                else:
                    print(f"\n  Falha no upload. MP3 salvo em: {mp3_path}")
                print("  Pressione Enter para continuar...")

            self._upload_thread = threading.Thread(target=do_upload, daemon=False)
            self._upload_thread.start()
            self._upload_thread.join()  # Espera o upload terminar (Playwright tem timeout interno de 120s)
        else:
            print("  Erro: nenhum audio gravado.")

    def run(self):
        while True:
            self.print_header()
            self.print_menu()

            try:
                choice = input("  > ").strip().upper()
            except (KeyboardInterrupt, EOFError):
                choice = "Q"

            if self.recorder.is_recording:
                if choice == "S":
                    self.handle_stop()
                    input("  Pressione Enter para continuar...")
                elif choice == "Q":
                    self.recorder.stop()
                    print("  Ate logo!")
                    break
                else:
                    # Mostrar timer atualizado
                    continue
            else:
                if choice == "1":
                    self.recorder.start(record_mic=True, record_system=True)
                    print("\n  Gravando Mic + Sistema... Pressione Enter e depois [S] para parar.")
                    input()
                elif choice == "2":
                    self.recorder.start(record_mic=True, record_system=False)
                    print("\n  Gravando Mic... Pressione Enter e depois [S] para parar.")
                    input()
                elif choice == "3":
                    self.recorder.start(record_mic=False, record_system=True)
                    print("\n  Gravando Sistema... Pressione Enter e depois [S] para parar.")
                    input()
                elif choice == "L":
                    print("\n  Abrindo navegador para login...")
                    self.uploader.interactive_login()
                    print("  Sessao salva!")
                    input("  Pressione Enter para continuar...")
                elif choice == "Q":
                    print("  Ate logo!")
                    break
