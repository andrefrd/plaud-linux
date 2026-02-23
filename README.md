# Plaud Linux

> Open-source alternative to Plaud Desktop for Linux.
> Record mic and system audio, convert to MP3, and auto-upload to [web.plaud.ai](https://web.plaud.ai).

## Why?

[Plaud Desktop](https://www.plaud.ai/) has no Linux support and doesn't work via Wine.
This project uses native Linux tools:

- **PulseAudio/PipeWire** for audio capture (any app: Discord, Spotify, etc.)
- **FFmpeg** for MP3 conversion
- **Playwright** for automated upload via RPA

---

## Quick Install

```bash
git clone https://github.com/andrefrd/plaud-linux.git
cd plaud-linux
./install.sh
```

The script installs all dependencies, creates the `plaud-linux` and `plaud-linux-tray` commands globally,
registers the app in the GNOME Launcher, and optionally enables autostart.

---

## Usage

### 🖥️ System Tray (recommended — Ubuntu 24 / Wayland)

```bash
plaud-linux-tray
```

Or open **Plaud Linux** from the GNOME app launcher.

The tray icon appears in the system bar. Right-click to access the menu:

| Icon color | Status                 |
|:----------:|------------------------|
| ⚫ dark    | Ready / idle           |
| 🔴 red     | Recording              |
| 🔵 blue    | Processing / uploading |

**Menu options:**
- `🎙️ Gravar (Mic + Sistema)` — record microphone and system audio
- `🎤 Gravar apenas Mic` — microphone only
- `🔊 Gravar apenas Sistema` — system audio only
- `⏹ Parar Gravação` — stop and auto-upload
- `🔐 Login web.plaud.ai` — open browser for Google SSO login
- `❌ Sair` — quit

> **Wayland note:** The tray app uses **AppIndicator3 / Ayatana** on GNOME/Wayland (Ubuntu 22.04+),
> and falls back to **pystray/XWayland** on X11 sessions. Both backends are installed automatically.

#### Autostart on login

Re-run the installer and answer `s` when asked, or manually:

```bash
cp desktop/plaud-linux-autostart.desktop ~/.config/autostart/plaud-linux.desktop
```

---

### 💻 Terminal (CLI)

```bash
plaud-linux
```

### First run

A browser opens for Google SSO login to web.plaud.ai.
After login, **close the browser**. Session is saved at `~/.plaud-linux/session/`.

### Recording (CLI)

```
  [1] Gravar Mic + Sistema
  [2] Gravar apenas Mic
  [3] Gravar apenas Sistema
  [L] Login web.plaud.ai
  [Q] Sair
```

Press `S` to stop. Audio is converted to MP3 and uploaded automatically.
If upload fails, MP3 is saved at `~/.plaud-linux/recordings/`.

---

## Manual Install

```bash
# System packages
sudo apt install ffmpeg pulseaudio-utils python3 pipx \
    gir1.2-ayatanaappindicator3-0.1 libayatana-appindicator3-1 \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 libnotify-bin

# Install the package
pipx install .
pipx inject plaud-linux pystray Pillow

# Install Playwright Chromium
~/.local/pipx/venvs/plaud-linux/bin/playwright install chromium

# Generate icons
~/.local/pipx/venvs/plaud-linux/bin/python3 generate_icons.py
```

---

## Requirements

| Component | Purpose |
|---|---|
| `ffmpeg` | Audio conversion to MP3 |
| `pactl` (pulseaudio-utils) | Audio source management |
| `playwright` / Chromium | Automated upload via web RPA |
| `Pillow` | Tray icon rendering |
| `pystray` | X11 tray backend (fallback) |
| `gir1.2-ayatanaappindicator3` | Wayland/GNOME tray backend |
| `libnotify-bin` | Desktop notifications (`notify-send`) |

---

## License

MIT
