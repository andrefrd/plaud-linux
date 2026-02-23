"""
System tray icon para controlar o Plaud Linux.

Suporte a Wayland (Ubuntu 24+) via AppIndicator/ayatana e fallback para pystray.
"""

import os
import sys
import threading
import signal
from pathlib import Path

from plaud_linux.recorder import AudioRecorder
from plaud_linux.uploader import PlaudUploader


# Diretório de assets (ícones PNG)
_ASSETS_DIR = Path(__file__).parent.parent / "assets"
_ICON_IDLE = str(_ASSETS_DIR / "plaud-idle-64.png")
_ICON_RECORDING = str(_ASSETS_DIR / "plaud-recording-64.png")
_ICON_UPLOADING = str(_ASSETS_DIR / "plaud-uploading-64.png")


def _is_wayland() -> bool:
    """Detecta se a sessão atual é Wayland."""
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _try_import_appindicator():
    """Tenta importar AppIndicator via GObject Introspection (Wayland/GNOME).

    python3-gi é instalado via apt e pode não estar no venv isolado do pipx.
    Injeta os site-packages do sistema para torná-lo acessível.
    """
    import subprocess as _sp, sys as _sys

    # Descobre o path do gi no Python do sistema e injeta no sys.path
    try:
        result = _sp.run(
            ["python3", "-c",
             "import gi, os; print(os.path.dirname(os.path.dirname(gi.__file__)))"],
            capture_output=True, text=True, timeout=3
        )
        gi_site = result.stdout.strip()
        if gi_site and gi_site not in _sys.path:
            _sys.path.insert(0, gi_site)
    except Exception:
        pass

    try:
        import gi
        gi.require_version("Gtk", "3.0")
        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AppIndicator3
        except (ValueError, ImportError):
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3
        from gi.repository import Gtk
        return AppIndicator3, Gtk
    except Exception:
        return None, None


# ─────────────────────────────────────────────
#  Implementação GTK/AppIndicator (Wayland)
# ─────────────────────────────────────────────

class _GTKTray:
    """Backend AppIndicator3 — compatível com Wayland/GNOME Shell."""

    def __init__(self, recorder: AudioRecorder, uploader: PlaudUploader,
                 AppIndicator3, Gtk):
        self.recorder = recorder
        self.uploader = uploader
        self.AppIndicator3 = AppIndicator3
        self.Gtk = Gtk
        self._indicator = None

    def _notify(self, title: str, body: str):
        """Envia notificação desktop via notify-send."""
        os.popen(f'notify-send "{title}" "{body}" --icon=audio-input-microphone -a "Plaud Linux"')

    def _set_icon(self, state: str):
        """Troca o ícone do indicador."""
        icons = {
            "idle": _ICON_IDLE,
            "recording": _ICON_RECORDING,
            "uploading": _ICON_UPLOADING,
        }
        icon_path = icons.get(state, _ICON_IDLE)
        if os.path.exists(icon_path):
            self._indicator.set_icon_full(icon_path, f"Plaud Linux - {state}")
        else:
            # Fallback para ícone de tema do sistema
            self._indicator.set_icon_full("audio-input-microphone", "Plaud Linux")

    def _start_recording(self, widget, mode):
        if self.recorder.is_recording:
            return
        mic = mode in ("mic", "both")
        system = mode in ("system", "both")
        self.recorder.start(record_mic=mic, record_system=system)
        self._set_icon("recording")
        self._notify("⏺ Plaud Linux", "Gravando...")
        self._rebuild_menu()

    def _stop_recording(self, widget):
        if not self.recorder.is_recording:
            return
        self._set_icon("uploading")

        def process():
            mp3_path = self.recorder.stop()
            if mp3_path:
                self._notify("📤 Plaud Linux", "Fazendo upload…")
                success = self.uploader.upload(mp3_path)
                if success:
                    self._notify("✅ Plaud Linux", "Upload concluído!")
                else:
                    self._notify("⚠️ Plaud Linux", f"Falha no upload. MP3: {mp3_path}")
            else:
                self._notify("❌ Plaud Linux", "Nenhum áudio gravado.")
            self._set_icon("idle")
            self.Gtk.main_iteration_do(False)
            self._rebuild_menu()

        threading.Thread(target=process, daemon=True).start()

    def _do_login(self, widget):
        def login():
            self._notify("🔐 Plaud Linux", "Abrindo navegador para login…")
            self.uploader.interactive_login()
            self._notify("✅ Plaud Linux", "Sessão salva!")
        threading.Thread(target=login, daemon=True).start()

    def _do_quit(self, widget):
        if self.recorder.is_recording:
            self.recorder.stop()
        self.Gtk.main_quit()

    def _rebuild_menu(self):
        """Reconstrói o menu de acordo com o estado atual."""
        Gtk = self.Gtk
        menu = Gtk.Menu()

        if not self.recorder.is_recording:
            item1 = Gtk.MenuItem(label="🎙️  Gravar Mic + Sistema")
            item1.connect("activate", self._start_recording, "both")
            menu.append(item1)

            item2 = Gtk.MenuItem(label="🎤  Gravar apenas Mic")
            item2.connect("activate", self._start_recording, "mic")
            menu.append(item2)

            item3 = Gtk.MenuItem(label="🔊  Gravar apenas Sistema")
            item3.connect("activate", self._start_recording, "system")
            menu.append(item3)
        else:
            item_stop = Gtk.MenuItem(label="⏹  Parar Gravação")
            item_stop.connect("activate", self._stop_recording)
            menu.append(item_stop)

        sep = Gtk.SeparatorMenuItem()
        menu.append(sep)

        item_login = Gtk.MenuItem(label="🔐  Login web.plaud.ai")
        item_login.connect("activate", self._do_login)
        menu.append(item_login)

        item_quit = Gtk.MenuItem(label="❌  Sair")
        item_quit.connect("activate", self._do_quit)
        menu.append(item_quit)

        menu.show_all()
        self._indicator.set_menu(menu)

    def run(self):
        AppIndicator3 = self.AppIndicator3
        Gtk = self.Gtk

        icon_path = _ICON_IDLE if os.path.exists(_ICON_IDLE) else "audio-input-microphone"

        self._indicator = AppIndicator3.Indicator.new(
            "plaud-linux",
            icon_path,
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_title("Plaud Linux")

        self._rebuild_menu()

        # Captura Ctrl+C para sair limpo
        signal.signal(signal.SIGINT, lambda *_: Gtk.main_quit())
        signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())

        Gtk.main()


# ─────────────────────────────────────────────
#  Implementação pystray (X11 / fallback)
# ─────────────────────────────────────────────

class _PystrayTray:
    """Backend pystray — funciona em X11 ou Wayland com XWayland."""

    def __init__(self, recorder: AudioRecorder, uploader: PlaudUploader):
        import pystray
        from PIL import Image, ImageDraw
        self.recorder = recorder
        self.uploader = uploader
        self.pystray = pystray
        self.Image = Image
        self.ImageDraw = ImageDraw
        self._icon_obj = None

    def _load_or_create_icon(self, state: str):
        """Carrega ícone PNG do assets ou gera um fallback simples."""
        paths = {
            "idle": _ICON_IDLE,
            "recording": _ICON_RECORDING,
            "uploading": _ICON_UPLOADING,
        }
        path = paths.get(state, _ICON_IDLE)
        if os.path.exists(path):
            return self.Image.open(path)
        return self._make_icon(state)

    def _make_icon(self, state: str):
        size = 64
        colors = {"idle": (45, 45, 55), "recording": (220, 38, 38), "uploading": (37, 99, 235)}
        fill = colors.get(state, colors["idle"])
        img = self.Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = self.ImageDraw.Draw(img)
        draw.ellipse([2, 2, size-2, size-2], fill=(*fill, 255))
        mx = size // 2
        draw.rounded_rectangle([mx-7, 8, mx+7, 28], radius=7, fill=(255, 255, 255, 240))
        draw.arc([mx-12, 22, mx+12, 40], start=0, end=180, fill=(255, 255, 255, 220), width=3)
        draw.line([mx, 40, mx, 48], fill=(255, 255, 255, 220), width=3)
        draw.line([mx-8, 48, mx+8, 48], fill=(255, 255, 255, 220), width=3)
        return img

    def _notify(self, title: str, body: str):
        os.popen(f'notify-send "{title}" "{body}" --icon=audio-input-microphone -a "Plaud Linux"')

    def _on_start_recording(self, icon, item):
        if self.recorder.is_recording:
            return
        self.recorder.start(record_mic=True, record_system=True)
        icon.icon = self._load_or_create_icon("recording")
        icon.title = "Plaud Linux - Gravando..."
        self._notify("⏺ Plaud Linux", "Gravando...")

    def _on_start_mic_only(self, icon, item):
        if self.recorder.is_recording:
            return
        self.recorder.start(record_mic=True, record_system=False)
        icon.icon = self._load_or_create_icon("recording")
        icon.title = "Plaud Linux - Gravando mic..."
        self._notify("⏺ Plaud Linux", "Gravando Mic...")

    def _on_start_system_only(self, icon, item):
        if self.recorder.is_recording:
            return
        self.recorder.start(record_mic=False, record_system=True)
        icon.icon = self._load_or_create_icon("recording")
        icon.title = "Plaud Linux - Gravando sistema..."
        self._notify("⏺ Plaud Linux", "Gravando Sistema...")

    def _on_stop_recording(self, icon, item):
        if not self.recorder.is_recording:
            return
        icon.icon = self._load_or_create_icon("uploading")
        icon.title = "Plaud Linux - Processando..."

        def process():
            mp3_path = self.recorder.stop()
            if mp3_path:
                success = self.uploader.upload(mp3_path)
                if success:
                    icon.notify("Upload concluído!", "Plaud Linux")
                else:
                    icon.notify(f"Falha no upload. MP3: {mp3_path}", "Plaud Linux")
            else:
                icon.notify("Erro: nenhum áudio gravado.", "Plaud Linux")
            icon.icon = self._load_or_create_icon("idle")
            icon.title = "Plaud Linux - Pronto"

        threading.Thread(target=process, daemon=True).start()

    def _on_login(self, icon, item):
        def do_login():
            icon.notify("Abrindo navegador para login...", "Plaud Linux")
            self.uploader.interactive_login()
            icon.notify("Sessão salva!", "Plaud Linux")
        threading.Thread(target=do_login, daemon=True).start()

    def _on_quit(self, icon, item):
        if self.recorder.is_recording:
            self.recorder.stop()
        icon.stop()

    def run(self):
        pystray = self.pystray
        menu = pystray.Menu(
            pystray.MenuItem("🎙️  Gravar (Mic + Sistema)", self._on_start_recording,
                             visible=lambda _: not self.recorder.is_recording),
            pystray.MenuItem("🎤  Gravar apenas Mic", self._on_start_mic_only,
                             visible=lambda _: not self.recorder.is_recording),
            pystray.MenuItem("🔊  Gravar apenas Sistema", self._on_start_system_only,
                             visible=lambda _: not self.recorder.is_recording),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("⏹  Parar Gravação", self._on_stop_recording,
                             visible=lambda _: self.recorder.is_recording),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔐  Login web.plaud.ai", self._on_login),
            pystray.MenuItem("❌  Sair", self._on_quit),
        )

        self._icon_obj = pystray.Icon(
            name="plaud-linux",
            icon=self._load_or_create_icon("idle"),
            title="Plaud Linux - Pronto",
            menu=menu,
        )
        self._icon_obj.run()


# ─────────────────────────────────────────────
#  Entry-point público
# ─────────────────────────────────────────────

class PlaudTray:
    """
    Seleciona automaticamente o backend correto:
      - AppIndicator3 (GTK)  → Wayland/GNOME (Ubuntu 24+) 
      - pystray              → X11 ou XWayland (fallback)
    """

    def __init__(self, recorder: AudioRecorder, uploader: PlaudUploader):
        self.recorder = recorder
        self.uploader = uploader

    def run(self):
        AppIndicator3, Gtk = _try_import_appindicator()

        if AppIndicator3 is not None:
            print("ℹ️  Backend: AppIndicator3 (Wayland/GNOME)")
            backend = _GTKTray(self.recorder, self.uploader, AppIndicator3, Gtk)
        else:
            print("ℹ️  Backend: pystray (X11/XWayland)")
            backend = _PystrayTray(self.recorder, self.uploader)

        backend.run()
