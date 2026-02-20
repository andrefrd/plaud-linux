# Plaud Linux

> Open-source alternative to Plaud Desktop for Linux.
> Record mic and system audio, convert to MP3, and auto-upload to [web.plaud.ai](https://web.plaud.ai).

## Why?

[Plaud Desktop](https://www.plaud.ai/) has no Linux support and doesn't work via Wine.
This project uses native Linux tools:

- **PulseAudio/PipeWire** for audio capture (any app: Discord, Spotify, etc.)
- **FFmpeg** for MP3 conversion
- **Playwright** for automated upload via RPA

## Requirements

- Python 3.10+
- FFmpeg: `sudo apt install ffmpeg`
- PulseAudio utils: `sudo apt install pulseaudio-utils`

## Install

```bash
git clone https://github.com/andrefrd/plaud-linux.git
cd plaud-linux
pip install .
playwright install chromium
```

## Usage

```bash
plaud-linux
```

### First run

A Chromium browser will open for you to log in to web.plaud.ai via Google SSO.
After login, **close the browser**. Your session is saved at `~/.plaud-linux/session/`.

### Recording

```
==================================================
  PLAUD LINUX - Gravador + Upload
==================================================

  [1] Gravar Mic + Sistema
  [2] Gravar apenas Mic
  [3] Gravar apenas Sistema

  [L] Login web.plaud.ai
  [Q] Sair
```

1. Pick a recording mode (`1`, `2`, or `3`)
2. Press `S` to stop
3. Audio is converted to MP3 and uploaded to web.plaud.ai
4. If upload fails, MP3 is saved at `~/.plaud-linux/recordings/`

## Project Structure

```
plaud-linux/
├── plaud_linux/
│   ├── __init__.py    # Entry point + main()
│   ├── recorder.py    # PulseAudio + FFmpeg
│   ├── uploader.py    # Playwright RPA
│   ├── cli.py         # Terminal interface
│   └── tray.py        # System tray (optional)
├── pyproject.toml
├── requirements.txt
└── README.md
```

## License

MIT
