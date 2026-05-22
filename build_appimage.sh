#!/usr/bin/env bash
# Script para compilar o Plaud Linux como AppImage

set -e

# Configurações
APP_NAME="plaud-linux"
VERSION="0.2.0"
APP_DIR="AppDir"
BUILD_VENV="build_venv"

echo "========================================"
echo "  Plaud Linux - Compilador AppImage"
echo "========================================"

# Limpar compilações anteriores
echo "Limpando diretórios temporários..."
rm -rf "$APP_DIR" "$BUILD_VENV" dist build *.spec

# Criar e ativar venv temporário para isolamento PEP 668
echo "Criando ambiente virtual temporário para compilação..."
python3 -m venv "$BUILD_VENV"
source "$BUILD_VENV"/bin/activate

# Garantir dependências de compilação no venv
echo "Instalando dependências de compilação..."
pip install --upgrade pip
pip install pyinstaller Pillow pystray playwright

# Roda o PyInstaller
echo "Executando PyInstaller..."
pyinstaller --onedir \
            --noconsole \
            --name "$APP_NAME" \
            --add-data "assets:assets" \
            --clean \
            plaud_app.py

# Estruturar o AppDir
echo "Criando estrutura do AppDir..."
mkdir -p "$APP_DIR/usr/bin"
mkdir -p "$APP_DIR/usr/share/applications"
mkdir -p "$APP_DIR/usr/share/icons/hicolor/256x256/apps"

# Copiar os arquivos gerados pelo PyInstaller
cp -r dist/plaud-linux/* "$APP_DIR/usr/bin/"

# Copiar ícones e arquivo desktop
cp assets/plaud-idle-256.png "$APP_DIR/usr/share/icons/hicolor/256x256/apps/plaud-linux.png"
cp assets/plaud-idle-256.png "$APP_DIR/plaud-linux.png" # Ícone obrigatório na raiz

# Criar arquivo desktop na raiz e na estrutura padrão do sistema
cat <<EOF > "$APP_DIR/plaud-linux.desktop"
[Desktop Entry]
Name=Plaud Linux
Comment=Gravador de áudio com upload automático para web.plaud.ai
Exec=plaud-linux
Icon=plaud-linux
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Recorder;
Keywords=plaud;audio;recorder;upload;
StartupWMClass=plaud-linux
EOF
cp "$APP_DIR/plaud-linux.desktop" "$APP_DIR/usr/share/applications/"

# Criar script AppRun (entrypoint do AppImage)
cat <<'EOF' > "$APP_DIR/AppRun"
#!/bin/sh
SELF=$(readlink -f "$0")
HERE=$(dirname "$0")
exec "$HERE/usr/bin/plaud-linux" "$@"
EOF
chmod +x "$APP_DIR/AppRun"

# Baixar o appimagetool se não estiver disponível
if [ ! -s "appimagetool" ]; then
    echo "Baixando appimagetool..."
    wget -q --show-progress -O appimagetool https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool
fi

# Gerar o AppImage
echo "Gerando AppImage..."
export ARCH=x86_64
./appimagetool "$APP_DIR" "${APP_NAME}-${VERSION}-x86_64.AppImage"

# Desativar e remover venv temporário
echo "Desativando ambiente virtual e limpando temporários..."
deactivate
rm -rf "$APP_DIR" "$BUILD_VENV" dist build *.spec

echo "========================================"
echo "  Sucesso! AppImage gerado com sucesso:"
echo "  $(pwd)/${APP_NAME}-${VERSION}-x86_64.AppImage"
echo "========================================"
