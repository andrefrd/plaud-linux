#!/bin/bash
# Plaud Linux - Installation Script
# Installs plaud-linux + tray app globally with Wayland (Ubuntu 24) support.

set -e

echo "========================================"
echo "  Plaud Linux - Installer"
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ─── 1. System dependencies ───────────────────
echo "[1/6] Checking system dependencies..."

MISSING=""
for pkg in ffmpeg pulseaudio-utils python3 pipx; do
    dpkg -s "$pkg" &>/dev/null || MISSING="$MISSING $pkg"
done

# AppIndicator para Wayland/GNOME Shell (Ubuntu 22.04+)
for pkg in \
    gir1.2-ayatanaappindicator3-0.1 \
    libayatana-appindicator3-1 \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0
do
    dpkg -s "$pkg" &>/dev/null || MISSING="$MISSING $pkg"
done

# libnotify para notify-send (notificações nativas)
dpkg -s "libnotify-bin" &>/dev/null || MISSING="$MISSING libnotify-bin"

if [ -n "$MISSING" ]; then
    echo "  Installing:$MISSING"
    sudo apt update -qq
    sudo apt install -y -qq $MISSING
else
    echo "  All system dependencies found."
fi

# ─── 2. pipx ──────────────────────────────────
echo ""
echo "[2/6] Setting up pipx..."

if ! command -v pipx &>/dev/null; then
    echo "  Installing pipx..."
    sudo apt install -y -qq pipx
    pipx ensurepath
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "  pipx already installed."
fi

# ─── 3. plaud-linux ───────────────────────────
echo ""
echo "[3/6] Installing plaud-linux..."

pipx install "$SCRIPT_DIR" --force

# Inject pystray as optional tray backend (fallback para X11)
PIPX_VENV="$HOME/.local/pipx/venvs/plaud-linux"
"$PIPX_VENV/bin/pip" install --quiet pystray Pillow

# ─── 4. Playwright Chromium ───────────────────
echo ""
echo "[4/6] Installing Playwright Chromium..."

if [ -d "$PIPX_VENV" ]; then
    "$PIPX_VENV/bin/playwright" install chromium
else
    echo "  Warning: pipx venv not found, run 'playwright install chromium' manually."
fi

# ─── 5. Generate icons + register app ─────────
echo ""
echo "[5/6] Generating icons and registering app..."

# Gerar ícones PNG via Pillow
"$PIPX_VENV/bin/python3" "$SCRIPT_DIR/generate_icons.py"

# Instalar ícones no tema do sistema (hicolor)
for sz in 16 22 32 48 64 128 256; do
    ICON_DIR="$HOME/.local/share/icons/hicolor/${sz}x${sz}/apps"
    mkdir -p "$ICON_DIR"
    cp "$SCRIPT_DIR/assets/plaud-idle-${sz}.png" "$ICON_DIR/plaud-linux.png"
done
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

# Instalar .desktop no launcher do GNOME
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
cp "$SCRIPT_DIR/desktop/plaud-linux.desktop" "$APPS_DIR/plaud-linux.desktop"
update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo "  App registrado no GNOME Launcher."

# ─── 6. Autostart (opcional) ──────────────────
echo ""
echo "[6/6] Configuring autostart..."

AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

read -p "  Iniciar Plaud Linux automaticamente com o sistema? [s/N] " REPLY
if [[ "$REPLY" =~ ^[Ss]$ ]]; then
    cp "$SCRIPT_DIR/desktop/plaud-linux-autostart.desktop" "$AUTOSTART_DIR/plaud-linux.desktop"
    echo "  Autostart configurado."
else
    rm -f "$AUTOSTART_DIR/plaud-linux.desktop"
    echo "  Autostart ignorado."
fi

# ─────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Instalação concluída!"
echo "========================================"
echo ""
echo "  Modo Terminal:  plaud-linux"
echo "  Modo Tray:      plaud-linux-tray"
echo ""
echo "  Ou abra pelo Launcher do GNOME:"
echo "  Busque por 'Plaud Linux'"
echo "========================================"
