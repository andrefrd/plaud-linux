# Plaud Linux 🎙️

> Alternativa open-source ao Plaud Desktop para Linux.  
> Grava áudio do microfone e/ou sistema, converte para MP3 e faz upload automático para [web.plaud.ai](https://web.plaud.ai).

## Por que este projeto?

O [Plaud Desktop](https://www.plaud.ai/) oficial não tem suporte a Linux e não funciona via Wine.
Este projeto resolve isso usando ferramentas nativas do Linux:

- **PulseAudio/PipeWire** para captura de áudio (qualquer app: Discord, Spotify, etc.)
- **FFmpeg** para conversão para MP3
- **Playwright** para upload automático via RPA

## Requisitos

- Python 3.10+
- FFmpeg (`sudo apt install ffmpeg`)
- PulseAudio utils (`sudo apt install pulseaudio-utils`)
- Ambiente gráfico com system tray (GNOME, KDE, XFCE, etc.)

## Instalação

```bash
git clone https://github.com/seu-usuario/plaud-linux.git
cd plaud-linux
pip install -r requirements.txt
playwright install chromium
```

## Uso

```bash
python main.py
```

### Primeira execução
Na primeira vez, o app abrirá um navegador Chromium para você fazer login no web.plaud.ai via Google SSO.
Após o login, **feche o navegador**. A sessão será salva em `~/.plaud-linux/session/`.

### Uso normal
1. Um ícone aparecerá na bandeja do sistema
2. Clique com o botão direito para ver as opções:
   - 🎙️ **Gravar (Mic + Sistema)** — grava tudo
   - 🎤 **Gravar apenas Mic** — só microfone
   - 🔊 **Gravar apenas Sistema** — só áudio do sistema (Discord, etc.)
3. Clique em **⏹ Parar Gravação** quando terminar
4. O áudio será convertido para MP3 e enviado automaticamente para web.plaud.ai
5. Se o upload falhar, o MP3 fica salvo em `~/.plaud-linux/recordings/`

## Estrutura

```
plaud-linux/
├── main.py          # Entry point
├── recorder.py      # Gravação via PulseAudio + FFmpeg
├── uploader.py      # Upload RPA via Playwright
├── tray.py          # Interface system tray
├── requirements.txt
└── README.md
```

## Problemas conhecidos

- Se a sessão do web.plaud.ai expirar, use a opção "Login web.plaud.ai" no menu da bandeja
- Em alguns ambientes (Wayland puro), o tray icon pode precisar de uma extensão como `AppIndicator`

## Licença

MIT
