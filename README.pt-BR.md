<div align="center">

# 🎙️ Plaud Linux

**Alternativa open-source ao Plaud Desktop — feita para Linux.**

Grava o microfone e o áudio do sistema, converte para MP3 e faz upload automático para o [web.plaud.ai](https://web.plaud.ai).

[![License: MIT](https://img.shields.io/badge/Licença-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Plataforma: Linux](https://img.shields.io/badge/plataforma-Linux-lightgrey.svg)](https://kernel.org/)
[![Ubuntu 24 Wayland](https://img.shields.io/badge/Ubuntu%2024-Wayland%20%E2%9C%93-orange.svg)](https://ubuntu.com/)

[🇺🇸 English](README.md) · [🇪🇸 Español](README.es.md)

</div>

---

## Por que isso existe?

O [Plaud Desktop](https://www.plaud.ai/) **não tem suporte para Linux** e não funciona via Wine.  
O Plaud Linux resolve isso usando ferramentas 100% nativas do Linux:

| Componente | Função |
|---|---|
| **PulseAudio / PipeWire** | Captura microfone e áudio do sistema de qualquer app |
| **FFmpeg** | Converte o áudio bruto para MP3 |
| **Playwright + Chromium** | Upload automatizado para web.plaud.ai via RPA |
| **AppIndicator3 / pystray** | Ícone na bandeja do sistema (Wayland & X11) |

Sem Electron. Sem Wine. Sem dependências proprietárias.

---

## Funcionalidades

- 🎙️ **Grava microfone**, áudio do sistema, ou ambos simultaneamente
- 📤 **Upload automático** para sua conta Plaud após a gravação
- 🔔 **Notificações desktop** quando o upload termina ou falha
- 🖥️ **App na Bandeja do Sistema** — roda em segundo plano (GNOME/Wayland & X11)
- 💻 **Modo CLI** — funciona em qualquer terminal, inclusive via SSH
- 🔐 **Sessão Google SSO persistente** — faça login uma vez, upload automático para sempre
- 🐧 **Testado no Ubuntu 22.04 / 24.04 LTS** (Wayland + X11)

---

## Instalação Rápida

```bash
git clone https://github.com/andrefrd/plaud-linux.git
cd plaud-linux
./install.sh
```

O instalador irá:
1. Instalar dependências do sistema (`ffmpeg`, `pactl`, `AppIndicator3`, etc.)
2. Instalar o pacote Python via `pipx`
3. Instalar `pystray` e `Pillow`
4. Instalar o Playwright Chromium
5. Gerar ícones e registrar o app no launcher do GNOME
6. Perguntar se deseja **iniciar automaticamente com o sistema**

---

## Uso

### 🖥️ Bandeja do Sistema (Recomendado)

```bash
plaud-linux-tray
```

Ou abra **Plaud Linux** pelo launcher do GNOME (Atividades).

Clique com o botão direito no ícone para acessar o menu:

| Ícone | Estado |
|:---:|---|
| ⚫ | Pronto / Inativo |
| 🔴 | Gravando |
| 🔵 | Processando / Enviando |

**Menu:**
- `🎙️ Gravar (Mic + Sistema)` — grava as duas fontes em estéreo
- `🎤 Gravar apenas Mic`
- `🔊 Gravar apenas Sistema`
- `⏹ Parar Gravação` — para, converte e faz upload
- `📂 Acessar Gravações` — abre a pasta de gravações no gerenciador de arquivos
- `🔐 Login web.plaud.ai` — abre o navegador para o Google SSO
- `❌ Sair`

> **Nota Wayland:** No Ubuntu 22.04+ / 24.04 (GNOME/Wayland), o app usa o backend
> **AppIndicator3 / Ayatana**. Em sessões X11 usa **pystray** como fallback.
> Ambos são instalados e selecionados automaticamente.

#### Iniciar automaticamente com o sistema

O instalador pergunta. Para configurar manualmente:

```bash
# Ativar
cp desktop/plaud-linux-autostart.desktop ~/.config/autostart/plaud-linux.desktop

# Desativar
rm ~/.config/autostart/plaud-linux.desktop
```

---

### 💻 CLI (Terminal)

```bash
plaud-linux
```

Funciona em qualquer terminal, inclusive por SSH remoto (sem display necessário).

#### Primeiro uso

Um navegador abre para o login via Google SSO no web.plaud.ai.  
Após o login, **feche o navegador**. A sessão é salva em `~/.plaud-linux/session/`.

#### Menu de gravação

```
  [1] Gravar Mic + Sistema
  [2] Gravar apenas Mic
  [3] Gravar apenas Sistema
  [L] Login web.plaud.ai
  [Q] Sair
```

Pressione `S` para parar. O áudio é convertido para MP3 e enviado automaticamente.  
Se o upload falhar, o MP3 é salvo em `~/.plaud-linux/recordings/`.

---

## Instalação Manual

```bash
# 1. Pacotes do sistema
sudo apt install ffmpeg pulseaudio-utils python3 pipx \
    gir1.2-ayatanaappindicator3-0.1 libayatana-appindicator3-1 \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 libnotify-bin

# 2. Instalar o pacote
pipx install .
pipx inject plaud-linux pystray Pillow

# 3. Instalar o Playwright Chromium
~/.local/share/pipx/venvs/plaud-linux/bin/playwright install chromium

# 4. Gerar ícones da bandeja
~/.local/share/pipx/venvs/plaud-linux/bin/python3 generate_icons.py

# 5. (Opcional) Registrar no launcher do GNOME
cp desktop/plaud-linux.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/

# 6. (Opcional) Autostart
cp desktop/plaud-linux-autostart.desktop ~/.config/autostart/plaud-linux.desktop
```

---

## Requisitos

| Requisito | Versão | Finalidade |
|---|---|---|
| Python | 3.10+ | Runtime |
| ffmpeg | qualquer | Conversão para MP3 |
| pulseaudio-utils (`pactl`) | qualquer | Gerenciamento de fontes de áudio |
| Playwright Chromium | latest | RPA para upload |
| Pillow | qualquer | Renderização de ícones |
| pystray | qualquer | Backend de bandeja X11 (fallback) |
| gir1.2-ayatanaappindicator3 | 0.1 | Backend de bandeja Wayland/GNOME |
| libnotify-bin | qualquer | Notificações desktop |

---

## Como o Upload Funciona

O upload usa **automação de navegador (RPA)**:

1. Playwright abre o Chromium com sua sessão salva
2. Acessa `web.plaud.ai`
3. Clica em **"Add audio" → "Import audio"**
4. Seleciona o arquivo MP3 via input de arquivo
5. Aguarda a confirmação `"Imported"`
6. Verifica se o arquivo aparece nos Arquivos Recentes
7. Fecha o navegador

Essa abordagem **não requer chaves de API privadas** e funciona enquanto o web app do Plaud estiver disponível.

---

## Localização dos Arquivos

| Caminho | Conteúdo |
|---|---|
| `~/.plaud-linux/session/` | Sessão do navegador (Google SSO) |
| `~/.plaud-linux/recordings/` | MP3s com falha de upload |

---

## Contribuindo

Pull requests são bem-vindos! O projeto é intencionalmente simples e fácil de hackear.

**Boas primeiras contribuições:**
- Melhorar o design dos ícones
- Adicionar som de notificação no upload
- Suportar múltiplas contas Plaud
- Adicionar timer de gravação no tooltip da bandeja
- Empacotar como `.deb` para distribuição mais fácil

**Para montar o ambiente de desenvolvimento:**

```bash
git clone https://github.com/andrefrd/plaud-linux.git
cd plaud-linux
python3 -m venv venv
source venv/bin/activate
pip install -e ".[tray]"
playwright install chromium
```

---

## Licença

MIT © [Andre Dantas](https://github.com/andrefrd)
