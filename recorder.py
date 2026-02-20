"""
Módulo de gravação de áudio usando PulseAudio/PipeWire + FFmpeg.

Grava o microfone e/ou áudio do sistema, converte para MP3.
"""

import subprocess
import os
import json
import time
import signal
from datetime import datetime


class AudioRecorder:
    def __init__(self, recordings_dir: str):
        self.recordings_dir = recordings_dir
        self.is_recording = False
        self._processes = []
        self._raw_files = []
        self._current_mp3 = None
        self._start_time = None

    def list_sources(self) -> list[dict]:
        """Lista todas as fontes de áudio disponíveis no sistema (mics + monitors)."""
        try:
            result = subprocess.run(
                ["pactl", "-f", "json", "list", "sources"],
                capture_output=True, text=True, timeout=5
            )
            sources = json.loads(result.stdout)
            parsed = []
            for s in sources:
                name = s.get("name", "")
                desc = s.get("description", name)
                state = s.get("state", "IDLE")
                parsed.append({
                    "name": name,
                    "description": desc,
                    "state": state,
                    "is_monitor": ".monitor" in name
                })
            return parsed
        except Exception as e:
            print(f"Erro ao listar fontes de áudio: {e}")
            return []

    def get_default_mic(self) -> str | None:
        """Retorna o nome da fonte padrão do microfone."""
        try:
            result = subprocess.run(
                ["pactl", "get-default-source"],
                capture_output=True, text=True, timeout=5
            )
            source = result.stdout.strip()
            if source and ".monitor" not in source:
                return source
        except Exception:
            pass
        # Fallback: procurar qualquer mic
        for s in self.list_sources():
            if not s["is_monitor"]:
                return s["name"]
        return None

    def get_default_monitor(self) -> str | None:
        """Retorna o monitor de áudio do sistema (saída de som loopback)."""
        try:
            result = subprocess.run(
                ["pactl", "get-default-sink"],
                capture_output=True, text=True, timeout=5
            )
            sink = result.stdout.strip()
            if sink:
                return f"{sink}.monitor"
        except Exception:
            pass
        # Fallback
        for s in self.list_sources():
            if s["is_monitor"]:
                return s["name"]
        return None

    def start(self, record_mic=True, record_system=True):
        """Inicia a gravação de áudio."""
        if self.is_recording:
            return

        self.is_recording = True
        self._processes = []
        self._raw_files = []
        self._start_time = time.time()

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        if record_mic:
            mic_source = self.get_default_mic()
            if mic_source:
                mic_file = os.path.join(self.recordings_dir, f"{timestamp}_mic.wav")
                self._raw_files.append(mic_file)
                proc = subprocess.Popen(
                    ["parecord", "--device", mic_source,
                     "--file-format=wav", mic_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self._processes.append(proc)
                print(f"🎤 Gravando microfone: {mic_source}")
            else:
                print("⚠️  Nenhum microfone encontrado")

        if record_system:
            monitor = self.get_default_monitor()
            if monitor:
                sys_file = os.path.join(self.recordings_dir, f"{timestamp}_system.wav")
                self._raw_files.append(sys_file)
                proc = subprocess.Popen(
                    ["parecord", "--device", monitor,
                     "--file-format=wav", sys_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self._processes.append(proc)
                print(f"🔊 Gravando áudio do sistema: {monitor}")
            else:
                print("⚠️  Nenhum monitor de áudio do sistema encontrado")

    def stop(self) -> str | None:
        """Para a gravação e converte para MP3. Retorna o caminho do MP3."""
        if not self.is_recording:
            return None

        self.is_recording = False

        # Parar todos os processos de gravação
        for proc in self._processes:
            proc.send_signal(signal.SIGINT)

        # Esperar processos terminarem
        for proc in self._processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

        self._processes = []

        # Verificar se temos arquivos gravados
        existing_files = [f for f in self._raw_files if os.path.exists(f) and os.path.getsize(f) > 0]

        if not existing_files:
            print("❌ Nenhum arquivo de áudio foi gerado")
            return None

        # Converter/mixar para MP3 com FFmpeg
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_mp3 = os.path.join(self.recordings_dir, f"plaud_{timestamp}.mp3")

        try:
            if len(existing_files) == 1:
                # Apenas uma fonte — conversão direta
                subprocess.run(
                    ["ffmpeg", "-y", "-i", existing_files[0],
                     "-codec:a", "libmp3lame", "-b:a", "128k", output_mp3],
                    capture_output=True, timeout=120
                )
            else:
                # Duas fontes — mixar com FFmpeg
                subprocess.run(
                    ["ffmpeg", "-y",
                     "-i", existing_files[0],
                     "-i", existing_files[1],
                     "-filter_complex", "amerge=inputs=2,pan=stereo|c0<c0+c2|c1<c1+c3",
                     "-codec:a", "libmp3lame", "-b:a", "128k", output_mp3],
                    capture_output=True, timeout=120
                )
        except Exception as e:
            print(f"❌ Erro na conversão FFmpeg: {e}")
            return None
        finally:
            # Limpar arquivos WAV temporários
            for f in self._raw_files:
                try:
                    os.remove(f)
                except OSError:
                    pass
            self._raw_files = []

        if os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 0:
            self._current_mp3 = output_mp3
            duration = round(time.time() - self._start_time)
            print(f"✅ MP3 gerado: {output_mp3} ({duration}s de gravação)")
            return output_mp3
        else:
            print("❌ Falha ao gerar MP3")
            return None

    def get_elapsed(self) -> int:
        """Retorna segundos decorridos desde o início da gravação."""
        if self._start_time and self.is_recording:
            return int(time.time() - self._start_time)
        return 0
