<div align="center">

# 🎙️ Plaud Linux

**Open-source alternative to Plaud Desktop — made for Linux.**

Record mic and system audio, convert to MP3, and auto-upload to [web.plaud.ai](https://web.plaud.ai).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey.svg)](https://kernel.org/)
[![Ubuntu 24 Wayland](https://img.shields.io/badge/Ubuntu%2024-Wayland%20%E2%9C%93-orange.svg)](https://ubuntu.com/)

[🇧🇷 Português](README.pt-BR.md) · [🇪🇸 Español](README.es.md)

</div>

---

## Why?

[Plaud Desktop](https://www.plaud.ai/) has **no Linux support** and doesn't work via Wine.  
Plaud Linux fills that gap using 100% native Linux tools:

| Component | Role |
|---|---|
| **PulseAudio / PipeWire** | Capture mic and system audio from any app |
| **FFmpeg** | Convert raw audio to MP3 |
| **Playwright + Chromium** | Automated upload to web.plaud.ai via browser RPA |
| **AppIndicator3 / pystray** | System tray icon (Wayland & X11) |

No Electron. No Wine. No proprietary blobs.

---

## Features

- 🎙️ **Record mic**, system audio, or both simultaneously
- 📤 **Auto-upload** to your Plaud account right after recording
- 🔔 **Desktop notifications** when upload succeeds or fails
- 🖥️ **System Tray app** — runs silently in the background (GNOME/Wayland & X11)
- 💻 **CLI mode** — works on any terminal, including headless SSH sessions
- 🔐 **Persistent Google SSO session** — login once, auto-upload forever
- 🐧 **Ubuntu 22.04 / 24.04 LTS tested** (Wayland + X11)

---

## Quick Install

```bash
git clone https://github.com/andrefrd/plaud-linux.git
cd plaud-linux
./install.sh
```

The installer will:
1. Install system dependencies (`ffmpeg`, `pactl`, `AppIndicator3`, etc.)
2. Install the Python package via `pipx`
3. Install `pystray` and `Pillow`
4. Install Playwright Chromium
5. Generate tray icons and register the app in the GNOME launcher
6. Optionally configure **autostart at login**

---

## Usage

### 🖥️ System Tray (Recommended)

```bash
plaud-linux-tray
```

Or open **Plaud Linux** from the GNOME app launcher / Activities.

Right-click the tray icon to access the menu:

| Icon | State |
|:---:|---|
| ⚫ | Ready / Idle |
| 🔴 | Recording |
| 🔵 | Processing / Uploading |

**Menu:**
- `🎙️ Record (Mic + System)` — records both sources, mixed to stereo
- `🎤 Record Mic only`
- `🔊 Record System only`
- `⏹ Stop Recording` — stops, converts, uploads
- `📂 Open Recordings` — opens the recordings folder in the file manager
- `🔐 Login web.plaud.ai` — opens browser for Google SSO
- `❌ Quit`

> **Wayland note:** On Ubuntu 22.04+ / 24.04 (GNOME/Wayland), the app uses the
> **AppIndicator3 / Ayatana** backend. On X11 sessions it falls back to **pystray**.
> Both are installed and selected automatically.

#### Autostart on login

The installer will ask. To enable/disable manually:

```bash
# Enable
cp desktop/plaud-linux-autostart.desktop ~/.config/autostart/plaud-linux.desktop

# Disable
rm ~/.config/autostart/plaud-linux.desktop
```

---

### 💻 CLI (Terminal)

```bash
plaud-linux
```

Works on any terminal, including remote SSH sessions (no display required).

#### First run

A browser opens for Google SSO login to web.plaud.ai.  
After login, **close the browser**. The session is saved at `~/.plaud-linux/session/`.

#### Recording menu

```
  [1] Record Mic + System
  [2] Record Mic only
  [3] Record System only
  [L] Login web.plaud.ai
  [Q] Quit
```

Press `S` to stop. Audio is converted to MP3 and uploaded automatically.  
If upload fails, the MP3 is saved at `~/.plaud-linux/recordings/`.

---

## Manual Install

```bash
# 1. System packages
sudo apt install ffmpeg pulseaudio-utils python3 pipx \
    gir1.2-ayatanaappindicator3-0.1 libayatana-appindicator3-1 \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 libnotify-bin

# 2. Install the package
pipx install .
pipx inject plaud-linux pystray Pillow

# 3. Install Playwright Chromium
~/.local/share/pipx/venvs/plaud-linux/bin/playwright install chromium

# 4. Generate tray icons
~/.local/share/pipx/venvs/plaud-linux/bin/python3 generate_icons.py

# 5. (Optional) Register in GNOME launcher
cp desktop/plaud-linux.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/

# 6. (Optional) Autostart
cp desktop/plaud-linux-autostart.desktop ~/.config/autostart/plaud-linux.desktop
```

---

## Requirements

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.10+ | Runtime |
| ffmpeg | any | MP3 conversion |
| pulseaudio-utils (`pactl`) | any | Audio source management |
| Playwright Chromium | latest | Browser RPA for upload |
| Pillow | any | Tray icon rendering |
| pystray | any | X11 tray backend (fallback) |
| gir1.2-ayatanaappindicator3 | 0.1 | Wayland/GNOME tray backend |
| libnotify-bin | any | Desktop notifications |

---

## How Upload Works

The upload is done via **browser automation (RPA)**:

1. Playwright opens Chromium with your saved session
2. Navigates to `web.plaud.ai`
3. Clicks **"Add audio" → "Import audio"**
4. Selects the MP3 file via the file input
5. Waits for the `"Imported"` confirmation
6. Verifies the file appears in Recent files
7. Closes the browser

This approach requires **no private API keys** and works as long as the Plaud web app is available.

---

## File Locations

| Path | Content |
|---|---|
| `~/.plaud-linux/session/` | Persistent browser session (Google SSO) |
| `~/.plaud-linux/recordings/` | Failed upload fallback MP3s |

---

## Contributing

Pull requests are welcome! This project is intentionally simple and hackable.

**Good first issues:**
- Improve the tray icon design
- Add notification sound on upload
- Support multiple Plaud accounts
- Add a recording timer in the tray tooltip
- Package as a `.deb` for easier distribution

**To set up a dev environment:**

```bash
git clone https://github.com/andrefrd/plaud-linux.git
cd plaud-linux
python3 -m venv venv
source venv/bin/activate
pip install -e ".[tray]"
playwright install chromium
```

---

## License

MIT © [Andre Dantas](https://github.com/andrefrd)
