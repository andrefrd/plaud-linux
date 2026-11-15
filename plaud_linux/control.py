"""
Canal de controle da tray para a ilha (Fase 2) e guarda de duração/disco.

Socket AF_UNIX em ``$XDG_RUNTIME_DIR/plaud-ilha/control.sock``, protocolo de
uma linha por conexão:

``status``  → JSON com o estado da tray (``phase``, ``started``, ``files``…)
``stop``    → ``ok stopping`` ou ``err not-recording``

O diretório é 0700, então só o próprio usuário fala com a tray.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from typing import Callable

from plaud_linux import ilha


def send_command(command: str, path: str | None = None, timeout: float = 2.0) -> str | None:
    """Envia um comando à tray. Retorna a resposta ou ``None`` se ninguém escuta."""
    path = path or ilha.control_socket_path()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(path)
            s.sendall(command.strip().encode() + b"\n")
            chunks = []
            while True:
                data = s.recv(4096)
                if not data:
                    break
                chunks.append(data)
                if data.endswith(b"\n"):
                    break
            return b"".join(chunks).decode(errors="replace").strip()
    except OSError:
        return None


def query_status(path: str | None = None) -> dict | None:
    reply = send_command("status", path)
    if not reply:
        return None
    try:
        data = json.loads(reply)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class ControlServer:
    """Servidor do socket de controle, em thread daemon."""

    def __init__(self, status_fn: Callable[[], dict], stop_fn: Callable[[], bool],
                 path: str | None = None):
        self.status_fn = status_fn
        self.stop_fn = stop_fn
        self.path = path or ilha.control_socket_path()
        self._sock: socket.socket | None = None

    def start(self) -> bool:
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        if send_command("status", self.path, timeout=0.5) is not None:
            print("⚠️  Outra instância já atende o socket de controle da ilha")
            return False
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.path)
        os.chmod(self.path, 0o600)
        sock.listen(4)
        self._sock = sock
        threading.Thread(target=self._serve, name="plaud-ilha-control", daemon=True).start()
        return True

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
                try:
                    os.unlink(self.path)
                except OSError:
                    pass

    def _serve(self):
        while self._sock is not None:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(2)
                    line = conn.recv(256).decode(errors="replace").strip().lower()
                    conn.sendall(self.handle(line).encode() + b"\n")
                except OSError:
                    pass

    def handle(self, line: str) -> str:
        try:
            if line == "status":
                return json.dumps(self.status_fn())
            if line == "stop":
                return "ok stopping" if self.stop_fn() else "err not-recording"
            return "err unknown-command"
        except Exception as e:  # nunca derrubar a tray por causa do socket
            return f"err {type(e).__name__}"


class RecordingGuard:
    """Para a gravação sozinho ao estourar a duração máxima ou o disco mínimo."""

    def __init__(self, recorder, stop_fn: Callable[[], bool],
                 notify_fn: Callable[[str, str], None], interval: float = 30.0):
        self.recorder = recorder
        self.stop_fn = stop_fn
        self.notify_fn = notify_fn
        self.interval = interval

    def start(self):
        threading.Thread(target=self._loop, name="plaud-ilha-guard", daemon=True).start()

    def _loop(self):
        while True:
            time.sleep(self.interval)
            try:
                self.check()
            except Exception as e:
                print(f"⚠️  Guarda da gravação: {e}")

    def check(self) -> str | None:
        """Retorna o motivo da parada, ou ``None`` se nada foi feito."""
        if not self.recorder.is_recording:
            return None
        cfg = ilha.load_config()
        reason = None
        max_h = cfg["auto_stop_hours"]
        if max_h > 0 and self.recorder.get_elapsed() >= max_h * 3600:
            reason = f"Gravação passou de {max_h:g} h e foi parada automaticamente."
        else:
            min_gb = cfg["disk_stop_gb"]
            free_gb = ilha.disk_free_bytes(self.recorder.recordings_dir) / 1e9
            if min_gb > 0 and free_gb < min_gb:
                reason = f"Disco com {free_gb:.1f} GB livres — gravação parada automaticamente."
        if reason and self.stop_fn():
            self.notify_fn("⏹ Plaud Linux", reason)
            return reason
        return None
