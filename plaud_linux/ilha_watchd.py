"""
plaud-ilha-watchd — observa a gravação e grava ``state.json`` para a ilha.

Roda como serviço ``systemd --user`` (só stdlib). A cada segundo:

1. Pergunta à tray pelo socket de controle (``status``). Se a tray não
   responde, deduz o estado pelo crescimento dos WAV em
   ``~/.plaud-linux/recordings`` (par ``<prefixo>_mic.wav`` + ``_system.wav``).
2. Calcula bytes, taxa, disco livre, ETA do disco e avisos.
3. A cada 60 s mede o pico dos últimos 30 s de cada trilha (silêncio digital).
4. Grava ``$XDG_RUNTIME_DIR/plaud-ilha/state.json`` de forma atômica.
5. Dispara ``notify-send -u critical`` quando um aviso novo aparece.

O watchd nunca para a gravação: quem para é a tray (``RecordingGuard``), que é
dona do processo de gravação. O watchd só observa e avisa.
"""

from __future__ import annotations

import array
import glob
import json
import os
import re
import struct
import subprocess
import sys
import time
from collections import deque
from datetime import datetime

from plaud_linux import ilha
from plaud_linux.control import query_status

SCHEMA = 1
WAV_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})_(mic|system)\.wav$")
GROWTH_WINDOW_S = 10
SILENCE_CHECK_EVERY_S = 60
SILENCE_TAIL_S = 30
SILENCE_PEAK = 3          # ≈ -80 dBFS em PCM 16-bit
ORPHAN_AGE_S = 3600


def scan_sessions(recordings_dir: str) -> dict[str, dict[str, str]]:
    """``{prefixo: {"mic": caminho, "system": caminho}}``."""
    sessions: dict[str, dict[str, str]] = {}
    for path in glob.glob(os.path.join(recordings_dir, "*.wav")):
        m = WAV_RE.match(os.path.basename(path))
        if m:
            sessions.setdefault(m.group(1), {})[m.group(2)] = path
    return sessions


def prefix_to_ts(prefix: str) -> float | None:
    try:
        return datetime.strptime(prefix, "%Y-%m-%d_%H-%M-%S").timestamp()
    except ValueError:
        return None


def track_name(path: str) -> str:
    m = WAV_RE.match(os.path.basename(path))
    return m.group(2) if m else os.path.basename(path)


def total_size(paths) -> int:
    total = 0
    for p in paths:
        try:
            total += os.stat(p).st_size
        except OSError:
            pass
    return total


def wav_tail_peak(path: str, seconds: float = SILENCE_TAIL_S) -> int | None:
    """Pico absoluto dos últimos ``seconds`` de um WAV PCM 16-bit em crescimento.

    Lê só o cabeçalho ``fmt`` e o fim do arquivo; ignora o tamanho declarado do
    chunk ``data`` (o parecord só o corrige ao fechar). ``None`` se não der.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
            if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
                return None
            pos, fmt, data_start = 12, None, None
            while pos + 8 <= len(head):
                cid, csize = head[pos:pos + 4], struct.unpack("<I", head[pos + 4:pos + 8])[0]
                if cid == b"fmt ":
                    fmt = struct.unpack("<HHIIHH", head[pos + 8:pos + 24])
                elif cid == b"data":
                    data_start = pos + 8
                    break
                pos += 8 + csize + (csize & 1)
            if not fmt or data_start is None:
                return None
            audio_format, channels, rate, _, block_align, bits = fmt
            if audio_format not in (1, 0xFFFE) or bits != 16 or block_align <= 0:
                return None
            size = os.fstat(f.fileno()).st_size
            want = int(rate * seconds) * block_align
            start = max(data_start, size - want)
            start -= (start - data_start) % block_align
            f.seek(start)
            raw = f.read(size - start)
    except OSError:
        return None
    raw = raw[: len(raw) - len(raw) % 2]
    if not raw:
        return None
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    return max(max(samples), -min(samples))


def notify(title: str, body: str):
    try:
        subprocess.Popen(
            ["notify-send", "-u", "critical", "-a", "Plaud Linux",
             "--icon=audio-input-microphone", title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


WARN_TEXT = {
    "duracao>3h": "Gravação passou de {warn_hours:g} h",
    "duracao>6h": "Gravação passou de {critical_hours:g} h — pare se não for intencional",
    "disco<15gb": "Pouco disco livre: {disk_free_gb:.1f} GB",
    "disco<5gb": "Disco quase cheio: {disk_free_gb:.1f} GB — a tray vai parar a gravação",
    "sem-audio": "Sem áudio há {silence_min} min (silêncio digital)",
    "travado": "Arquivo parou de crescer — o gravador pode ter morrido",
    "sessao-antiga": "Há gravação antiga (WAV) não convertida em {recordings_dir}",
}


def iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


class Watcher:
    def __init__(self, recordings_dir: str = ilha.RECORDINGS_DIR,
                 state_file: str | None = None, control_path: str | None = None,
                 status_fn=None, notify_fn=notify, clock=time.time):
        self.recordings_dir = recordings_dir
        self.state_file = state_file or ilha.state_path()
        self.control_path = control_path
        self.status_fn = status_fn or (lambda: query_status(self.control_path))
        self.notify_fn = notify_fn
        self.clock = clock
        self.session_key: str | None = None
        self.samples: deque[tuple[float, int]] = deque(maxlen=GROWTH_WINDOW_S + 1)
        self.last_bytes = -1
        self.last_growth: float | None = None
        self.last_silence_check = 0.0
        self.silent_since: float | None = None
        self.active_warns: set[str] = set()
        self.orphan_notified_day: str | None = None

    # ── coleta ──────────────────────────────────────────────

    def _reset_session(self, key: str | None):
        self.session_key = key
        self.samples.clear()
        self.last_bytes = -1
        self.last_growth = None
        self.last_silence_check = 0.0
        self.silent_since = None

    def tick(self) -> dict:
        now = self.clock()
        cfg = ilha.load_config()
        tray = self.status_fn()
        sessions = scan_sessions(self.recordings_dir)

        files: list[str] = []
        started: float | None = None
        phase = "idle"
        source = "files"

        tray_busy = tray is not None and (tray.get("phase") or "idle") != "idle"
        if tray_busy:
            source = "tray"
            phase = tray.get("phase") or "idle"
            if phase == "stopping":
                phase = "recording"
            files = [f for f in tray.get("files") or [] if isinstance(f, str)]
            started = tray.get("started")
            if not isinstance(started, (int, float)):
                started = None
            if not started and files:
                m = WAV_RE.match(os.path.basename(files[0]))
                started = prefix_to_ts(m.group(1)) if m else None
        elif sessions:
            key = max(sessions)
            files = sorted(sessions[key].values())
            started = prefix_to_ts(key)

        key = "|".join(files) or None
        if key != self.session_key:
            self._reset_session(key)

        size = total_size(files)
        if size != self.last_bytes:
            if self.last_bytes >= 0 and size > self.last_bytes:
                self.last_growth = now
            elif self.last_bytes < 0:
                self.last_growth = now if tray_busy else None
            self.last_bytes = size
        self.samples.append((now, size))

        growing = self.last_growth is not None and now - self.last_growth <= GROWTH_WINDOW_S
        if not tray_busy:
            phase = "recording" if growing else "idle"

        bytes_per_s = 0.0
        if len(self.samples) >= 2:
            (t0, b0), (t1, b1) = self.samples[0], self.samples[-1]
            if t1 > t0 and b1 >= b0:
                bytes_per_s = (b1 - b0) / (t1 - t0)

        free = ilha.disk_free_bytes(self.recordings_dir)
        disk_free_gb = free / 1e9
        eta_disk_h = (free / bytes_per_s / 3600) if (phase == "recording" and bytes_per_s > 0) else None
        elapsed = int(now - started) if (phase == "recording" and started) else 0

        silence_s = 0
        if phase == "recording" and files:
            silence_s = self._check_silence(now, files)

        warn: list[str] = []
        if phase == "recording":
            if elapsed >= cfg["warn_hours"] * 3600:
                warn.append("duracao>3h")
            if elapsed >= cfg["critical_hours"] * 3600:
                warn.append("duracao>6h")
            if disk_free_gb < cfg["disk_warn_gb"]:
                warn.append("disco<15gb")
            if cfg["disk_stop_gb"] > 0 and disk_free_gb < cfg["disk_stop_gb"]:
                warn.append("disco<5gb")
            if silence_s >= cfg["silence_warn_min"] * 60:
                warn.append("sem-audio")
            if (tray_busy and tray.get("phase") == "recording"
                    and now - (self.last_growth or now) >= cfg["stall_warn_min"] * 60):
                warn.append("travado")

        orphans = self._orphans(sessions, files if phase != "idle" else [], now)
        if orphans:
            warn.append("sessao-antiga")

        state = {
            "schema": SCHEMA,
            "state": phase if phase in ("recording", "converting", "uploading") else "idle",
            "phase": phase,
            "source": source,
            "session_started": iso(started) if phase == "recording" else None,
            "session_started_ts": started if phase == "recording" else None,
            "elapsed_s": elapsed,
            "bytes": size if phase == "recording" else 0,
            "bytes_per_s": round(bytes_per_s),
            "tracks": [track_name(f) for f in files] if phase == "recording" else [],
            "files": files,
            "recordings_dir": self.recordings_dir,
            "disk_free_gb": round(disk_free_gb, 1),
            "eta_disk_h": round(eta_disk_h, 1) if eta_disk_h is not None else None,
            "digital_silence_s": silence_s,
            "warn": warn,
            "orphans": orphans,
            "limits": {k: cfg[k] for k in ("warn_hours", "critical_hours", "auto_stop_hours",
                                           "disk_warn_gb", "disk_stop_gb", "silence_warn_min",
                                           "stall_warn_min")},
            "control": tray is not None,
            "updated": iso(now),
            "updated_ts": now,
        }
        if state["state"] == "converting":
            state["state"] = "uploading"
        self._notify_new(state, cfg, now)
        return state

    def _check_silence(self, now: float, files: list[str]) -> int:
        if now - self.last_silence_check >= SILENCE_CHECK_EVERY_S:
            self.last_silence_check = now
            peaks = [wav_tail_peak(f) for f in files]
            peaks = [p for p in peaks if p is not None]
            if peaks and max(peaks) <= SILENCE_PEAK:
                if self.silent_since is None:
                    self.silent_since = now - SILENCE_TAIL_S
            elif peaks:
                self.silent_since = None
        return int(now - self.silent_since) if self.silent_since is not None else 0

    def _orphans(self, sessions: dict, active: list[str], now: float) -> list[str]:
        active_set = set(active)
        out = []
        for key, tracks in sorted(sessions.items()):
            paths = list(tracks.values())
            if active_set.intersection(paths):
                continue
            try:
                mtime = max(os.stat(p).st_mtime for p in paths)
            except OSError:
                continue
            if now - mtime >= ORPHAN_AGE_S:
                out.append(key)
        return out

    def _notify_new(self, state: dict, cfg: dict, now: float):
        current = set(state["warn"])
        new = current - self.active_warns
        self.active_warns = current
        ctx = dict(cfg, disk_free_gb=state["disk_free_gb"],
                   silence_min=state["digital_silence_s"] // 60,
                   recordings_dir=self.recordings_dir)
        for code in sorted(new):
            if code == "sessao-antiga":
                day = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
                if self.orphan_notified_day == day:
                    continue
                self.orphan_notified_day = day
            self.notify_fn("⚠️ Plaud Linux", WARN_TEXT[code].format(**ctx))

    # ── saída ──────────────────────────────────────────────

    def write(self, state: dict):
        d = os.path.dirname(self.state_file)
        os.makedirs(d, mode=0o700, exist_ok=True)
        tmp = f"{self.state_file}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, self.state_file)

    def run(self, interval: float = 1.0):
        while True:
            started = time.monotonic()
            try:
                self.write(self.tick())
            except Exception as e:
                print(f"plaud-ilha-watchd: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            time.sleep(max(0.0, interval - (time.monotonic() - started)))


def main():
    ilha.ensure_runtime_dir()
    print(f"plaud-ilha-watchd: observando {ilha.RECORDINGS_DIR} → {ilha.state_path()}", flush=True)
    try:
        Watcher().run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
