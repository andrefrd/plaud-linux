"""
Configuração e caminhos compartilhados da "ilha" de gravação.

Só stdlib: é importado pelo ``plaud-ilha-watchd`` (serviço systemd) e pela
tray. A extensão do GNOME Shell lê apenas o ``state.json`` que o watchd grava.

``~/.config/plaud-ilha/config.json`` (opcional, todas as chaves opcionais)::

    {
      "warn_hours": 3,          # ilha âmbar + notificação
      "critical_hours": 6,      # ilha vermelha + notificação crítica
      "auto_stop_hours": 8,     # tray para a gravação sozinha (0 desativa)
      "disk_warn_gb": 15,       # aviso de disco
      "disk_stop_gb": 5,        # tray para a gravação sozinha (0 desativa)
      "silence_warn_min": 10,   # aviso de silêncio digital
      "stall_warn_min": 5       # aviso de arquivo que parou de crescer
    }
"""

from __future__ import annotations

import json
import os

DEFAULTS = {
    "warn_hours": 3,
    "critical_hours": 6,
    "auto_stop_hours": 8,
    "disk_warn_gb": 15,
    "disk_stop_gb": 5,
    "silence_warn_min": 10,
    "stall_warn_min": 5,
}

CONFIG_PATH = os.path.expanduser("~/.config/plaud-ilha/config.json")
RECORDINGS_DIR = os.path.expanduser("~/.plaud-linux/recordings")


def runtime_dir() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return os.path.join(base, "plaud-ilha")


def state_path() -> str:
    return os.path.join(runtime_dir(), "state.json")


def control_socket_path() -> str:
    return os.path.join(runtime_dir(), "control.sock")


def ensure_runtime_dir() -> str:
    d = runtime_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def load_config(path: str = CONFIG_PATH) -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return cfg
    if isinstance(data, dict):
        for key, default in DEFAULTS.items():
            value = data.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cfg[key] = value
    return cfg


def disk_free_bytes(path: str) -> int:
    probe = path
    while probe and not os.path.exists(probe):
        probe = os.path.dirname(probe)
    st = os.statvfs(probe or "/")
    return st.f_bavail * st.f_frsize
