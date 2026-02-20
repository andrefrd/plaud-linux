# Plaud Linux

> Open-source alternative to Plaud Desktop for Linux.
> Record mic and system audio, convert to MP3, and auto-upload to [web.plaud.ai](https://web.plaud.ai).

## Why?

[Plaud Desktop](https://www.plaud.ai/) has no Linux support and doesn't work via Wine.
This project uses native Linux tools:

- **PulseAudio/PipeWire** for audio capture (any app: Discord, Spotify, etc.)
- **FFmpeg** for MP3 conversion
- **Playwright** for automated upload via RPA

## Quick Install

```bash
git clone https://github.com/andrefrd/plaud-linux.git
cd plaud-linux
./install.sh
```

The script installs all dependencies, the `plaud-linux` command globally, and Playwright Chromium.

## Usage

```bash
plaud-linux
```

### First run

A browser opens for Google SSO login to web.plaud.ai.
After login, **close the browser**. Session is saved at `~/.plaud-linux/session/`.

### Recording

```
  [1] Gravar Mic + Sistema
  [2] Gravar apenas Mic
  [3] Gravar apenas Sistema
  [L] Login web.plaud.ai
  [Q] Sair
```

Press `S` to stop. Audio is converted to MP3 and uploaded automatically.
If upload fails, MP3 is saved at `~/.plaud-linux/recordings/`.

## Manual Install

```bash
sudo apt install ffmpeg pulseaudio-utils pipx
pipx install .
pipx runpip plaud-linux -- install playwright
~/.local/pipx/venvs/plaud-linux/bin/playwright install chromium
```

## License

MIT
