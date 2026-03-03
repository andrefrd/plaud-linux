<div align="center">

# 🎙️ Plaud Linux

**Alternativa de código abierto al Plaud Desktop — hecha para Linux.**

Graba el micrófono y el audio del sistema, convierte a MP3 y sube automáticamente a [web.plaud.ai](https://web.plaud.ai).

[![Licencia: MIT](https://img.shields.io/badge/Licencia-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Plataforma: Linux](https://img.shields.io/badge/plataforma-Linux-lightgrey.svg)](https://kernel.org/)
[![Ubuntu 24 Wayland](https://img.shields.io/badge/Ubuntu%2024-Wayland%20%E2%9C%93-orange.svg)](https://ubuntu.com/)

[🇺🇸 English](README.md) · [🇧🇷 Português](README.pt-BR.md)

</div>

---

## ¿Por qué existe esto?

[Plaud Desktop](https://www.plaud.ai/) **no tiene soporte para Linux** y no funciona con Wine.  
Plaud Linux soluciona esto usando herramientas 100% nativas de Linux:

| Componente | Función |
|---|---|
| **PulseAudio / PipeWire** | Captura el micrófono y el audio del sistema de cualquier app |
| **FFmpeg** | Convierte el audio crudo a MP3 |
| **Playwright + Chromium** | Subida automatizada a web.plaud.ai mediante RPA |
| **AppIndicator3 / pystray** | Ícono en la bandeja del sistema (Wayland & X11) |

Sin Electron. Sin Wine. Sin dependencias propietarias.

---

## Funcionalidades

- 🎙️ **Graba micrófono**, audio del sistema, o ambos simultáneamente
- 📤 **Subida automática** a tu cuenta Plaud tras la grabación
- 🔔 **Notificaciones de escritorio** cuando la subida termina o falla
- 🖥️ **App en la bandeja del sistema** — corre en segundo plano (GNOME/Wayland & X11)
- 💻 **Modo CLI** — funciona en cualquier terminal, incluso vía SSH remoto
- 🔐 **Sesión Google SSO persistente** — inicia sesión una vez, subida automática para siempre
- 🐧 **Probado en Ubuntu 22.04 / 24.04 LTS** (Wayland + X11)

---

## Instalación Rápida

```bash
git clone https://github.com/andrefrd/plaud-linux.git
cd plaud-linux
./install.sh
```

El instalador:
1. Instala las dependencias del sistema (`ffmpeg`, `pactl`, `AppIndicator3`, etc.)
2. Instala el paquete Python con `pipx`
3. Instala `pystray` y `Pillow`
4. Instala Playwright Chromium
5. Genera íconos y registra la app en el lanzador de GNOME
6. Pregunta si deseas **iniciar automáticamente con el sistema**

---

## Uso

### 🖥️ Bandeja del Sistema (Recomendado)

```bash
plaud-linux-tray
```

O abre **Plaud Linux** desde el lanzador de GNOME (Actividades).

Haz clic derecho en el ícono para acceder al menú:

| Ícono | Estado |
|:---:|---|
| ⚫ | Listo / Inactivo |
| 🔴 | Grabando |
| 🔵 | Procesando / Subiendo |

**Menú:**
- `🎙️ Grabar (Mic + Sistema)` — graba ambas fuentes en estéreo
- `🎤 Solo Micrófono`
- `🔊 Solo Sistema`
- `⏹ Detener Grabación` — detiene, convierte y sube
- `📂 Acceder a Grabaciones` — abre la carpeta de grabaciones en el administrador de archivos
- `🔐 Iniciar sesión web.plaud.ai` — abre el navegador para Google SSO
- `❌ Salir`

> **Nota Wayland:** En Ubuntu 22.04+ / 24.04 (GNOME/Wayland), la app usa el backend
> **AppIndicator3 / Ayatana**. En sesiones X11 usa **pystray** como alternativa.
> Ambos se instalan y seleccionan automáticamente.

#### Inicio automático con el sistema

El instalador lo pregunta. Para configurarlo manualmente:

```bash
# Activar
cp desktop/plaud-linux-autostart.desktop ~/.config/autostart/plaud-linux.desktop

# Desactivar
rm ~/.config/autostart/plaud-linux.desktop
```

---

### 💻 CLI (Terminal)

```bash
plaud-linux
```

Funciona en cualquier terminal, incluso por SSH remoto (sin pantalla necesaria).

#### Primer uso

Se abre un navegador para iniciar sesión con Google SSO en web.plaud.ai.  
Tras iniciar sesión, **cierra el navegador**. La sesión se guarda en `~/.plaud-linux/session/`.

#### Menú de grabación

```
  [1] Grabar Mic + Sistema
  [2] Solo Micrófono
  [3] Solo Sistema
  [L] Iniciar sesión web.plaud.ai
  [Q] Salir
```

Presiona `S` para detener. El audio se convierte a MP3 y se sube automáticamente.  
Si la subida falla, el MP3 se guarda en `~/.plaud-linux/recordings/`.

---

## Instalación Manual

```bash
# 1. Paquetes del sistema
sudo apt install ffmpeg pulseaudio-utils python3 pipx \
    gir1.2-ayatanaappindicator3-0.1 libayatana-appindicator3-1 \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 libnotify-bin

# 2. Instalar el paquete
pipx install .
pipx inject plaud-linux pystray Pillow

# 3. Instalar Playwright Chromium
~/.local/share/pipx/venvs/plaud-linux/bin/playwright install chromium

# 4. Generar íconos de la bandeja
~/.local/share/pipx/venvs/plaud-linux/bin/python3 generate_icons.py

# 5. (Opcional) Registrar en el lanzador de GNOME
cp desktop/plaud-linux.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/

# 6. (Opcional) Autostart
cp desktop/plaud-linux-autostart.desktop ~/.config/autostart/plaud-linux.desktop
```

---

## Requisitos

| Requisito | Versión | Propósito |
|---|---|---|
| Python | 3.10+ | Runtime |
| ffmpeg | cualquiera | Conversión a MP3 |
| pulseaudio-utils (`pactl`) | cualquiera | Gestión de fuentes de audio |
| Playwright Chromium | latest | RPA para subida |
| Pillow | cualquiera | Renderizado de íconos |
| pystray | cualquiera | Backend de bandeja X11 (alternativa) |
| gir1.2-ayatanaappindicator3 | 0.1 | Backend de bandeja Wayland/GNOME |
| libnotify-bin | cualquiera | Notificaciones de escritorio |

---

## Cómo Funciona la Subida

La subida usa **automatización del navegador (RPA)**:

1. Playwright abre Chromium con tu sesión guardada
2. Navega a `web.plaud.ai`
3. Hace clic en **"Add audio" → "Import audio"**
4. Selecciona el archivo MP3 mediante el input de archivo
5. Espera la confirmación `"Imported"`
6. Verifica que el archivo aparece en Archivos Recientes
7. Cierra el navegador

Este enfoque **no requiere claves de API privadas** y funciona mientras el web app de Plaud esté disponible.

---

## Ubicación de Archivos

| Ruta | Contenido |
|---|---|
| `~/.plaud-linux/session/` | Sesión del navegador (Google SSO) |
| `~/.plaud-linux/recordings/` | MP3s con error de subida |

---

## Contribuciones

¡Los pull requests son bienvenidos! Este proyecto está diseñado para ser simple y fácil de modificar.

**Buenas primeras contribuciones:**
- Mejorar el diseño de los íconos
- Agregar sonido de notificación al subir
- Soporte para múltiples cuentas Plaud
- Agregar temporizador de grabación en el tooltip de la bandeja
- Empaquetar como `.deb` para distribución más fácil

**Para configurar el entorno de desarrollo:**

```bash
git clone https://github.com/andrefrd/plaud-linux.git
cd plaud-linux
python3 -m venv venv
source venv/bin/activate
pip install -e ".[tray]"
playwright install chromium
```

---

## Licencia

MIT © [Andre Dantas](https://github.com/andrefrd)
