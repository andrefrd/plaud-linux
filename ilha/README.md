# Ilha de gravação (GNOME Shell / Wayland)

Notch preso embaixo do relógio do painel enquanto o Plaud Linux grava: tempo, tamanho,
disco livre, avisos e botões **Parar** / **Ocultar**. Fica acima de janelas maximizadas e de fullscreen e nunca pega
o foco do teclado. É um segundo canal: o ícone da bandeja continua existindo.

```
plaud-linux-tray ──► ~/.plaud-linux/recordings/*.wav
      │  └─ $XDG_RUNTIME_DIR/plaud-ilha/control.sock   (status / stop)
      ▼
plaud-ilha-watchd (systemd --user) ──► $XDG_RUNTIME_DIR/plaud-ilha/state.json
      ▼
extensão plaud-ilha@qwize.io (lê 1×/s e desenha)
```

| Peça | Onde |
|---|---|
| `plaud-ilha-watchd` | `plaud_linux/ilha_watchd.py` (só stdlib; entry point do pacote) |
| Socket de controle + guarda | `plaud_linux/control.py`, ligado em `plaud_linux/tray.py` |
| Configuração | `plaud_linux/ilha.py` |
| Extensão | `ilha/plaud-ilha@qwize.io/` (GNOME Shell 46) |
| Serviço | `ilha/plaud-ilha-watchd.service` |

## Instalar

```bash
./install.sh            # instala o pacote (publica ~/.local/bin/plaud-ilha-watchd)
./ilha/install.sh       # serviço systemd --user + extensão
# Wayland: logout/login para a extensão carregar
```

Remover: `./ilha/install.sh --uninstall`.

## Estados

| Ilha | Quando |
|---|---|
| invisível | sem gravação |
| ● vermelho pulsando `01:12:05 · 1,6 GB · livre 32 GB` | gravando |
| âmbar, borda vermelha, `PASSOU DE 3 H` / `DISCO BAIXO` | ≥ 3 h ou disco < 15 GB |
| fundo vermelho, `PASSOU DE 6 H` / `DISCO QUASE CHEIO` | ≥ 6 h ou disco < 5 GB |
| âmbar sólido, `SEM ÁUDIO HÁ N MIN` | últimos 30 s de todas as trilhas abaixo de −80 dBFS por 10 min |
| âmbar piscando, `arquivo parou de crescer` | tray diz que grava, mas os WAV não crescem há 5 min |
| azul `↑ convertendo…` / `enviando…` | conversão MP3 e upload |
| cinza `estado desatualizado` | `state.json` com mais de 5 s (watchd parado) |
| cinza `sem estado` | `state.json` ausente ou corrompido por 5 s |

- **Parar**: dois cliques (o primeiro vira "Confirmar" por 4 s), via socket da tray.
- **Ocultar** (˄): recolhe para um mini notch `● 01:12:05`; clique nele expande. Um aviso
  novo (3 h, disco, silêncio…) reabre o notch sozinho, e cada gravação nova começa expandida.

Cada aviso novo dispara `notify-send -u critical` uma vez. WAV antigo não convertido
(gravação órfã) gera um aviso por dia.

## Guarda (tray)

A tray, dona do processo de gravação, para sozinha quando:

- a gravação chega a `auto_stop_hours` (padrão 8 h);
- o disco das gravações fica abaixo de `disk_stop_gb` (padrão 5 GB).

## Configuração

`~/.config/plaud-ilha/config.json` — todas as chaves opcionais; `0` desativa as paradas automáticas.

```json
{
  "warn_hours": 3,
  "critical_hours": 6,
  "auto_stop_hours": 8,
  "disk_warn_gb": 15,
  "disk_stop_gb": 5,
  "silence_warn_min": 10,
  "stall_warn_min": 5
}
```

Os códigos em `warn` são estáveis mesmo com limites alterados
(`duracao>3h` significa "passou do limite de aviso").

## Contrato do `state.json` (schema 1)

```json
{
  "schema": 1,
  "state": "recording",
  "phase": "recording",
  "source": "tray",
  "session_started": "2026-11-10T09:44:39-03:00",
  "session_started_ts": 1794321879.0,
  "elapsed_s": 3725,
  "bytes": 2360000000,
  "bytes_per_s": 352800,
  "tracks": ["mic", "system"],
  "files": ["/home/…/2026-11-10_09-44-39_mic.wav", "…_system.wav"],
  "recordings_dir": "/home/…/.plaud-linux/recordings",
  "disk_free_gb": 32.4,
  "eta_disk_h": 25.1,
  "digital_silence_s": 0,
  "warn": ["duracao>3h"],
  "orphans": [],
  "limits": {"warn_hours": 3, "critical_hours": 6, "…": "…"},
  "control": true,
  "updated": "2026-11-14T19:47:44-03:00",
  "updated_ts": 1794696464.1
}
```

- `state` ∈ `idle | recording | uploading` (conversão aparece como `uploading`, com `phase: "converting"`); `stale` é decidido pela extensão a partir de `updated_ts`.
- `warn` ∈ `duracao>3h`, `duracao>6h`, `disco<15gb`, `disco<5gb`, `sem-audio`, `travado`, `sessao-antiga`.
- `source: "files"` = tray não respondeu (ou está ociosa); estado deduzido pelo crescimento dos WAV — cobre gravações feitas pelo modo CLI.
- Gravação atômica (`tmp` + `os.replace`).

## Socket de controle

`$XDG_RUNTIME_DIR/plaud-ilha/control.sock` (diretório 0700), uma linha por conexão:

```bash
python3 -c 'from plaud_linux.control import send_command as s; print(s("status"))'
python3 -c 'from plaud_linux.control import send_command as s; print(s("stop"))'
```

## Notas de plataforma (GNOME 46)

- `trackFullscreen: true` no `addChrome` **esconde** o ator quando o monitor está em
  fullscreen (`layout.js#_updateActorVisibility`); a ilha usa `false` e desliga o
  unredirect (`Meta.disable_unredirect_for_display`) enquanto está visível, para não
  sumir atrás de vídeo/jogo em scanout direto.
- No Wayland não existe `Alt+F2 r`: mudança na extensão exige logout/login.

## Testar

```bash
python3 -m unittest discover -s tests -v

# shell isolado e sem janela (não toca na sessão real)
XDG_DATA_HOME=/tmp/ilha-data GSETTINGS_BACKEND=memory \
  dbus-run-session -- gnome-shell --headless --wayland --no-x11 --virtual-monitor 1280x720

journalctl --user -f -o cat | grep plaud-ilha
```

Forçar um estado manualmente: `systemctl --user stop plaud-ilha-watchd` e editar
`$XDG_RUNTIME_DIR/plaud-ilha/state.json` (com `updated_ts` atual).
