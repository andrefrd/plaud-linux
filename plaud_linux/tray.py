"""
System tray icon para controlar o Plaud Linux.

Usa pystray para criar um ícone na bandeja do sistema com menu de controle.
"""

import threading
import pystray
from PIL import Image, ImageDraw

from recorder import AudioRecorder
from uploader import PlaudUploader


def create_icon_image(color="gray"):
    """Cria um ícone simples para a bandeja (círculo colorido)."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    colors = {
        "gray": (150, 150, 150, 255),
        "red": (239, 68, 68, 255),
        "green": (34, 197, 94, 255),
        "blue": (99, 102, 241, 255),
    }
    fill = colors.get(color, colors["gray"])

    # Círculo externo
    draw.ellipse([4, 4, size - 4, size - 4], fill=fill)
    # Círculo interno (mic icon placeholder)
    draw.ellipse([20, 20, size - 20, size - 20], fill=(255, 255, 255, 200))

    return img


class PlaudTray:
    def __init__(self, recorder: AudioRecorder, uploader: PlaudUploader):
        self.recorder = recorder
        self.uploader = uploader
        self._icon = None

    def _on_start_recording(self, icon, item):
        """Inicia a gravação (mic + sistema)."""
        if self.recorder.is_recording:
            return

        self.recorder.start(record_mic=True, record_system=True)
        icon.icon = create_icon_image("red")
        icon.title = "Plaud Linux - Gravando..."

    def _on_stop_recording(self, icon, item):
        """Para a gravação, converte para MP3 e faz upload."""
        if not self.recorder.is_recording:
            return

        icon.icon = create_icon_image("blue")
        icon.title = "Plaud Linux - Processando..."

        def process():
            mp3_path = self.recorder.stop()

            if mp3_path:
                success = self.uploader.upload(mp3_path)
                if success:
                    icon.notify("Upload concluído!", "Plaud Linux")
                else:
                    icon.notify(f"Falha no upload. MP3 salvo em: {mp3_path}", "Plaud Linux")
            else:
                icon.notify("Erro: nenhum áudio gravado.", "Plaud Linux")

            icon.icon = create_icon_image("gray")
            icon.title = "Plaud Linux - Pronto"

        threading.Thread(target=process, daemon=True).start()

    def _on_start_mic_only(self, icon, item):
        """Grava apenas o microfone."""
        if self.recorder.is_recording:
            return
        self.recorder.start(record_mic=True, record_system=False)
        icon.icon = create_icon_image("red")
        icon.title = "Plaud Linux - Gravando mic..."

    def _on_start_system_only(self, icon, item):
        """Grava apenas o áudio do sistema."""
        if self.recorder.is_recording:
            return
        self.recorder.start(record_mic=False, record_system=True)
        icon.icon = create_icon_image("red")
        icon.title = "Plaud Linux - Gravando sistema..."

    def _on_login(self, icon, item):
        """Abre o navegador para login manual."""
        def do_login():
            icon.notify("Abrindo navegador para login...", "Plaud Linux")
            self.uploader.interactive_login()
            icon.notify("Sessão salva!", "Plaud Linux")
        threading.Thread(target=do_login, daemon=True).start()

    def _on_quit(self, icon, item):
        """Encerra o aplicativo."""
        if self.recorder.is_recording:
            self.recorder.stop()
        icon.stop()

    def _is_recording(self, item):
        return self.recorder.is_recording

    def _is_not_recording(self, item):
        return not self.recorder.is_recording

    def run(self):
        """Inicia o ícone na bandeja do sistema."""
        menu = pystray.Menu(
            pystray.MenuItem(
                "🎙️ Gravar (Mic + Sistema)",
                self._on_start_recording,
                visible=self._is_not_recording
            ),
            pystray.MenuItem(
                "🎤 Gravar apenas Mic",
                self._on_start_mic_only,
                visible=self._is_not_recording
            ),
            pystray.MenuItem(
                "🔊 Gravar apenas Sistema",
                self._on_start_system_only,
                visible=self._is_not_recording
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "⏹ Parar Gravação",
                self._on_stop_recording,
                visible=self._is_recording
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔐 Login web.plaud.ai", self._on_login),
            pystray.MenuItem("❌ Sair", self._on_quit),
        )

        self._icon = pystray.Icon(
            name="plaud-linux",
            icon=create_icon_image("gray"),
            title="Plaud Linux - Pronto",
            menu=menu
        )

        self._icon.run()
