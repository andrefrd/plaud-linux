"""
Testes do watchd da ilha e do socket de controle da tray.

Rodar::

    python -m unittest discover -s tests -v
"""

import json
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plaud_linux import control, ilha  # noqa: E402
from plaud_linux import ilha_watchd as w  # noqa: E402


def write_wav(path, samples, rate=44100, channels=2, declared_size=0xFFFFFFFF):
    data = struct.pack(f"<{len(samples)}h", *samples)
    block = channels * 2
    header = (b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE"
              + b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * block, block, 16)
              + b"data" + struct.pack("<I", declared_size))
    with open(path, "wb") as f:
        f.write(header + data)


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class BaseWatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.clock = Clock()
        self.notes = []
        self.tray = None
        cfg = mock.patch.object(ilha, "load_config", return_value=dict(ilha.DEFAULTS))
        cfg.start()
        self.addCleanup(cfg.stop)
        disk = mock.patch.object(ilha, "disk_free_bytes", return_value=100e9)
        self.disk = disk.start()
        self.addCleanup(disk.stop)
        self.watch = w.Watcher(self.dir, state_file=os.path.join(self.dir, "rt", "state.json"),
                               status_fn=lambda: self.tray,
                               notify_fn=lambda t, b: self.notes.append(b), clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def grow(self, path, n):
        with open(path, "ab") as f:
            f.write(b"\x01\x00" * n)


class TestFileFallback(BaseWatch):
    def test_idle_without_wavs(self):
        s = self.watch.tick()
        self.assertEqual(s["state"], "idle")
        self.assertEqual(s["warn"], [])

    def test_recording_while_growing_then_idle(self):
        mic = os.path.join(self.dir, "2026-11-10_09-44-39_mic.wav")
        sysw = os.path.join(self.dir, "2026-11-10_09-44-39_system.wav")
        write_wav(mic, [1] * 100)
        write_wav(sysw, [1] * 100)
        self.watch.tick()
        self.clock.t += 1
        self.grow(mic, 1000)
        s = self.watch.tick()
        self.assertEqual(s["state"], "recording")
        self.assertEqual(sorted(s["tracks"]), ["mic", "system"])
        self.assertEqual(s["source"], "files")
        self.clock.t += w.GROWTH_WINDOW_S + 1
        self.assertEqual(self.watch.tick()["state"], "idle")

    def test_latest_session_wins_and_old_is_orphan(self):
        old = os.path.join(self.dir, "2026-11-01_08-00-00_mic.wav")
        write_wav(old, [1] * 10)
        os.utime(old, (self.clock.t - 7200, self.clock.t - 7200))
        new = os.path.join(self.dir, "2026-11-14_08-00-00_mic.wav")
        write_wav(new, [1] * 10)
        self.watch.tick()
        self.clock.t += 1
        self.grow(new, 100)
        s = self.watch.tick()
        self.assertEqual(s["files"], [new])
        self.assertEqual(s["orphans"], ["2026-11-01_08-00-00"])
        self.assertIn("sessao-antiga", s["warn"])


class TestTrayMode(BaseWatch):
    def start_tray(self, started_offset=0):
        self.mic = os.path.join(self.dir, "2026-11-14_10-00-00_mic.wav")
        write_wav(self.mic, [1000, -1000] * 10)
        self.tray = {"phase": "recording", "recording": True,
                     "started": self.clock.t - started_offset, "files": [self.mic]}

    def test_duration_warnings_and_notify_once(self):
        self.start_tray(started_offset=3 * 3600 + 5)
        s = self.watch.tick()
        self.assertEqual(s["state"], "recording")
        self.assertIn("duracao>3h", s["warn"])
        self.assertNotIn("duracao>6h", s["warn"])
        self.clock.t += 1
        self.watch.tick()
        self.assertEqual(len([n for n in self.notes if "3 h" in n]), 1)

    def test_disk_warnings(self):
        self.disk.return_value = 4e9
        self.start_tray()
        s = self.watch.tick()
        self.assertIn("disco<15gb", s["warn"])
        self.assertIn("disco<5gb", s["warn"])

    def test_stall_after_minutes_without_growth(self):
        self.start_tray()
        self.watch.tick()
        self.clock.t += 4 * 60
        self.assertNotIn("travado", self.watch.tick()["warn"])
        self.clock.t += 61
        self.assertIn("travado", self.watch.tick()["warn"])
        self.grow(self.mic, 10)
        self.clock.t += 1
        self.assertNotIn("travado", self.watch.tick()["warn"])

    def test_digital_silence(self):
        self.start_tray()
        write_wav(self.mic, [0] * 44100 * 2 * 31)
        for _ in range(11):
            s = self.watch.tick()
            self.clock.t += 60
        self.assertGreaterEqual(s["digital_silence_s"], 600)
        self.assertIn("sem-audio", s["warn"])
        write_wav(self.mic, [0] * 44100 * 2 * 31 + [9000] * 100)
        s = self.watch.tick()
        self.assertEqual(s["digital_silence_s"], 0)

    def test_converting_maps_to_uploading(self):
        self.start_tray()
        self.tray["phase"] = "converting"
        self.assertEqual(self.watch.tick()["state"], "uploading")

    def test_tray_idle_falls_back_to_files(self):
        self.tray = {"phase": "idle", "recording": False, "files": []}
        s = self.watch.tick()
        self.assertEqual(s["state"], "idle")
        self.assertTrue(s["control"])

    def test_atomic_write(self):
        self.start_tray()
        self.watch.write(self.watch.tick())
        with open(self.watch.state_file) as f:
            data = json.load(f)
        self.assertEqual(data["schema"], 1)
        self.assertEqual(os.listdir(os.path.dirname(self.watch.state_file)), ["state.json"])


class TestWavPeak(unittest.TestCase):
    def test_peak_reads_tail_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x_mic.wav")
            write_wav(p, [20000] * 10 + [0] * 44100 * 2 * 31, declared_size=0)
            self.assertEqual(w.wav_tail_peak(p), 0)
            write_wav(p, [0] * 1000 + [-12000])
            self.assertEqual(w.wav_tail_peak(p), 12000)

    def test_not_a_wav(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.wav")
            with open(p, "wb") as f:
                f.write(b"garbage")
            self.assertIsNone(w.wav_tail_peak(p))


class FakeRecorder:
    def __init__(self, recording=True, elapsed=0):
        self.is_recording = recording
        self.elapsed = elapsed
        self.recordings_dir = "/tmp"

    def get_elapsed(self):
        return self.elapsed


class TestControl(unittest.TestCase):
    def test_status_and_stop_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "control.sock")
            stopped = threading.Event()

            def stop():
                stopped.set()
                return True

            srv = control.ControlServer(lambda: {"phase": "recording"}, stop, path=path)
            self.assertTrue(srv.start())
            try:
                self.assertEqual(control.query_status(path), {"phase": "recording"})
                self.assertEqual(control.send_command("stop", path), "ok stopping")
                self.assertTrue(stopped.is_set())
                self.assertEqual(control.send_command("nope", path), "err unknown-command")
                second = control.ControlServer(lambda: {}, stop, path=path)
                self.assertFalse(second.start())
            finally:
                srv.close()
            self.assertIsNone(control.send_command("status", path))

    def test_guard_auto_stop_by_duration_and_disk(self):
        calls = []
        cfg = dict(ilha.DEFAULTS)
        with mock.patch.object(ilha, "load_config", return_value=cfg), \
                mock.patch.object(ilha, "disk_free_bytes", return_value=100e9) as disk:
            g = control.RecordingGuard(FakeRecorder(elapsed=8 * 3600), lambda: calls.append(1) or True,
                                       lambda t, b: None)
            self.assertIsNotNone(g.check())
            g.recorder = FakeRecorder(elapsed=60)
            self.assertIsNone(g.check())
            disk.return_value = 4e9
            self.assertIsNotNone(g.check())
            cfg["disk_stop_gb"] = 0
            cfg["auto_stop_hours"] = 0
            g.recorder = FakeRecorder(elapsed=99 * 3600)
            self.assertIsNone(g.check())
        self.assertEqual(len(calls), 2)


class TestConfig(unittest.TestCase):
    def test_partial_and_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.json")
            with open(p, "w") as f:
                json.dump({"warn_hours": 2, "auto_stop_hours": "x", "disk_warn_gb": True}, f)
            cfg = ilha.load_config(p)
            self.assertEqual(cfg["warn_hours"], 2)
            self.assertEqual(cfg["auto_stop_hours"], 8)
            self.assertEqual(cfg["disk_warn_gb"], 15)
            with open(p, "w") as f:
                f.write("{corrompido")
            self.assertEqual(ilha.load_config(p), ilha.DEFAULTS)


if __name__ == "__main__":
    unittest.main()
