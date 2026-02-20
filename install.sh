#!/bin/bash
# Plaud Linux - Installation Script
# Installs plaud-linux globally so you can run it from any terminal.

set -e

echo "========================================"
echo "  Plaud Linux - Installer"
echo "========================================"
echo ""

# 1. Check system dependencies
echo "[1/5] Checking system dependencies..."

MISSING=""
if ! command -v ffmpeg &> /dev/null; then
    MISSING="$MISSING ffmpeg"
fi
if ! command -v pactl &> /dev/null; then
    MISSING="$MISSING pulseaudio-utils"
fi
if ! command -v python3 &> /dev/null; then
    MISSING="$MISSING python3"
fi
if ! command -v pip3 &> /dev/null && ! command -v pipx &> /dev/null; then
    MISSING="$MISSING python3-pip"
fi

if [ -n "$MISSING" ]; then
    echo "  Installing missing packages:$MISSING"
    sudo apt update -qq
    sudo apt install -y -qq $MISSING
else
    echo "  All system dependencies found."
fi

# 2. Install pipx if needed
echo ""
echo "[2/5] Setting up pipx..."

if ! command -v pipx &> /dev/null; then
    echo "  Installing pipx..."
    sudo apt install -y -qq pipx
    pipx ensurepath
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "  pipx already installed."
fi

# 3. Install plaud-linux
echo ""
echo "[3/5] Installing plaud-linux..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
pipx install "$SCRIPT_DIR" --force

# 4. Install Playwright Chromium
echo ""
echo "[4/5] Installing Playwright Chromium browser..."

PIPX_VENV="$HOME/.local/pipx/venvs/plaud-linux"
if [ -d "$PIPX_VENV" ]; then
    "$PIPX_VENV/bin/playwright" install chromium
else
    echo "  Warning: Could not find pipx venv, trying global playwright..."
    playwright install chromium 2>/dev/null || echo "  Run 'playwright install chromium' manually."
fi

# 5. Done
echo ""
echo "========================================"
echo "  Installation complete!"
echo "========================================"
echo ""
echo "  Usage: Open any terminal and type:"
echo ""
echo "    plaud-linux"
echo ""
echo "  On first run, a browser will open for"
echo "  Google SSO login to web.plaud.ai."
echo "  After that, it's fully automatic."
echo "========================================"
