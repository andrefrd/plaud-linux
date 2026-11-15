#!/bin/bash
# Instala (ou remove, com --uninstall) a ilha de gravação:
#   - serviço systemd --user plaud-ilha-watchd
#   - extensão GNOME Shell plaud-ilha@qwize.io
# Requer o plaud-linux já instalado via pipx (../install.sh), que publica
# o executável ~/.local/bin/plaud-ilha-watchd.
set -euo pipefail

UUID="plaud-ilha@qwize.io"
HERE="$(cd "$(dirname "$0")" && pwd)"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$UUID"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="plaud-ilha-watchd.service"

enable_extension() {
    if gnome-extensions enable "$UUID" 2>/dev/null; then
        return
    fi
    # Extensão recém-copiada só é conhecida pelo shell após novo login (Wayland);
    # registra direto no gsettings para ela subir no próximo login.
    python3 - "$UUID" <<'PY'
import ast, subprocess, sys
uuid = sys.argv[1]
cur = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                     capture_output=True, text=True, check=True).stdout.strip()
items = [] if cur.startswith("@as") else ast.literal_eval(cur)
if uuid not in items:
    items.append(uuid)
    subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(items)], check=True)
PY
}

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now "$UNIT" 2>/dev/null || true
    rm -f "$UNIT_DIR/$UNIT"
    systemctl --user daemon-reload
    gnome-extensions disable "$UUID" 2>/dev/null || true
    rm -rf "$EXT_DIR"
    rm -rf "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/plaud-ilha/state.json"
    echo "Ilha removida. Faça logout/login para descarregar a extensão."
    exit 0
fi

if ! command -v plaud-ilha-watchd >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/plaud-ilha-watchd" ]; then
    echo "plaud-ilha-watchd não encontrado. Rode ../install.sh (pipx install) antes." >&2
    exit 1
fi

echo "[1/2] Serviço plaud-ilha-watchd (systemd --user)"
mkdir -p "$UNIT_DIR"
install -m 0644 "$HERE/$UNIT" "$UNIT_DIR/$UNIT"
systemctl --user daemon-reload
systemctl --user enable "$UNIT" >/dev/null
systemctl --user restart "$UNIT"

echo "[2/2] Extensão GNOME Shell $UUID"
mkdir -p "$EXT_DIR"
install -m 0644 "$HERE/$UUID/metadata.json" "$HERE/$UUID/extension.js" "$HERE/$UUID/stylesheet.css" "$EXT_DIR/"
enable_extension

echo ""
echo "Pronto. No Wayland a extensão só carrega após logout/login."
echo "Logs:  journalctl --user -f -o cat | grep plaud-ilha"
