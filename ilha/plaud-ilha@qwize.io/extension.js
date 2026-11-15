// Plaud Ilha — "notch" de gravação para GNOME Shell 46–50 (Wayland).
//
// Lê $XDG_RUNTIME_DIR/plaud-ilha/state.json (escrito pelo plaud-ilha-watchd)
// uma vez por segundo e desenha um notch preso embaixo do relógio do painel,
// com botão de parar e de ocultar (recolhe para um mini notch).
// Nunca pega foco de teclado; todo callback é protegido por try/catch porque
// uma exceção não tratada aqui derruba a sessão inteira.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const TAG = 'plaud-ilha';
const STALE_S = 5;
const MISSING_GRACE_S = 5;
const STOP_TIMEOUT_S = 120;
const CONFIRM_S = 4;
const MODES = ['recording', 'warn', 'critical', 'silence', 'stalled', 'stale', 'uploading', 'nostate', 'collapsed'];
const DEFAULT_LIMITS = {
    warn_hours: 3, critical_hours: 6, disk_warn_gb: 15, disk_stop_gb: 5,
};

function runtimeFile(name) {
    return GLib.build_filenamev([GLib.get_user_runtime_dir(), 'plaud-ilha', name]);
}

function pad(n) {
    return String(n).padStart(2, '0');
}

function fmtClock(total) {
    total = Math.max(0, Math.floor(total));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    return `${pad(h)}:${pad(m)}:${pad(total % 60)}`;
}

function fmtNum(value, digits) {
    return Number(value).toFixed(digits).replace('.', ',');
}

function fmtHours(h) {
    return Number.isInteger(h) ? `${h}` : fmtNum(h, 1);
}

function iconButton(iconName, styleClass, label = null) {
    const box = new St.BoxLayout({style_class: 'plaud-ilha-btn-box'});
    box.add_child(new St.Icon({icon_name: iconName, style_class: 'plaud-ilha-btn-icon'}));
    let text = null;
    if (label !== null) {
        text = new St.Label({text: label, y_align: Clutter.ActorAlign.CENTER});
        box.add_child(text);
    }
    const button = new St.Button({
        style_class: `plaud-ilha-btn ${styleClass}`,
        child: box,
        reactive: true,
        can_focus: false,
        track_hover: true,
        y_align: Clutter.ActorAlign.CENTER,
    });
    return [button, text];
}

export default class PlaudIlhaExtension extends Extension {
    enable() {
        this._state = null;
        this._failSince = null;
        this._loading = false;
        this._stopping = null;
        this._confirmUntil = 0;
        this._collapsedKey = null;
        this._collapsedWarn = new Set();
        this._anim = null;
        this._unredirectOff = false;
        this._signals = [];

        this._dot = new St.Label({text: '●', style_class: 'plaud-ilha-dot', y_align: Clutter.ActorAlign.CENTER});
        this._timer = new St.Label({text: '', style_class: 'plaud-ilha-timer', y_align: Clutter.ActorAlign.CENTER});
        this._info = new St.Label({text: '', style_class: 'plaud-ilha-info', y_align: Clutter.ActorAlign.CENTER});

        [this._stopBtn, this._stopLabel] = iconButton('media-playback-stop-symbolic', 'plaud-ilha-stop', 'Parar');
        this._stopBtn.connect('clicked', () => this._safe(() => this._onStopClicked()));
        [this._hideBtn] = iconButton('go-up-symbolic', 'plaud-ilha-hide');
        this._hideBtn.connect('clicked', () => this._safe(() => this._collapse()));

        this._island = new St.BoxLayout({
            style_class: 'plaud-ilha',
            reactive: true,
            track_hover: true,
            visible: false,
        });
        this._island.add_child(this._dot);
        this._island.add_child(this._timer);
        this._island.add_child(this._info);
        this._island.add_child(this._stopBtn);
        this._island.add_child(this._hideBtn);

        // Clique no mini notch expande de novo.
        this._island.connect('button-release-event', () => {
            this._safe(() => {
                if (this._isCollapsed()) {
                    this._collapsedKey = null;
                    this._render();
                }
            });
            return Clutter.EVENT_PROPAGATE;
        });

        Main.layoutManager.addChrome(this._island, {
            // affectsInputRegion: padrão true no 46 e removido no 50 — não passar.
            affectsStruts: false,
            // true esconderia o notch em fullscreen (layout.js#_updateActorVisibility)
            trackFullscreen: false,
        });

        const reposition = () => this._safe(() => this._reposition());
        this._signals.push([this._island, this._island.connect('notify::width', reposition)]);
        this._signals.push([Main.layoutManager, Main.layoutManager.connect('monitors-changed', reposition)]);
        this._signals.push([global.display, global.display.connect('workareas-changed', reposition)]);
        this._signals.push([global.display, global.display.connect('in-fullscreen-changed', reposition)]);

        this._timeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            this._safe(() => this._poll());
            return GLib.SOURCE_CONTINUE;
        });
        this._safe(() => this._poll());
    }

    disable() {
        if (this._timeoutId) {
            GLib.source_remove(this._timeoutId);
            this._timeoutId = 0;
        }
        for (const [obj, id] of this._signals ?? [])
            obj.disconnect(id);
        this._signals = [];
        this._setUnredirect(false);

        if (this._island) {
            Main.layoutManager.removeChrome(this._island);
            this._island.destroy();
        }
        this._island = this._dot = this._timer = this._info = null;
        this._stopBtn = this._stopLabel = this._hideBtn = null;
        this._state = null;
    }

    _safe(fn) {
        try {
            fn();
        } catch (e) {
            console.error(TAG, e);
        }
    }

    // ── ações ──────────────────────────────────────────────

    _sessionKey() {
        const s = this._state;
        return s ? String(s.session_started_ts ?? s.session_started ?? s.state) : null;
    }

    _isCollapsed() {
        return this._collapsedKey !== null && this._collapsedKey === this._sessionKey();
    }

    _collapse() {
        this._collapsedKey = this._sessionKey();
        this._collapsedWarn = this._currentWarn ?? new Set();
        this._confirmUntil = 0;
        this._render();
    }

    // Primeiro clique arma, segundo (em até 4 s) para — evita parar reunião sem querer.
    _onStopClicked() {
        const now = Date.now() / 1000;
        if (now > this._confirmUntil) {
            this._confirmUntil = now + CONFIRM_S;
            this._render();
            GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, CONFIRM_S, () => {
                this._safe(() => this._render());
                return GLib.SOURCE_REMOVE;
            });
            return;
        }
        this._confirmUntil = 0;
        this._requestStop();
    }

    _requestStop() {
        this._stopping = Date.now() / 1000;
        this._render();
        this._sendControl('stop', reply => {
            if (!reply || !reply.startsWith('ok')) {
                console.error(TAG, `stop recusado: ${reply}`);
                this._stopping = null;
                Main.notifyError('Plaud Ilha', `Não foi possível parar a gravação (${reply ?? 'tray sem resposta'})`);
            }
            this._render();
        });
    }

    _sendControl(cmd, done) {
        const client = new Gio.SocketClient();
        const address = Gio.UnixSocketAddress.new(runtimeFile('control.sock'));
        client.connect_async(address, null, (c, res) => {
            let conn = null;
            try {
                conn = c.connect_finish(res);
            } catch (e) {
                console.error(TAG, e);
                this._safe(() => done(null));
                return;
            }
            const bytes = new GLib.Bytes(new TextEncoder().encode(`${cmd}\n`));
            conn.get_output_stream().write_bytes_async(bytes, GLib.PRIORITY_DEFAULT, null, (out, r) => {
                try {
                    out.write_bytes_finish(r);
                    const input = Gio.DataInputStream.new(conn.get_input_stream());
                    input.read_line_async(GLib.PRIORITY_DEFAULT, null, (ins, r2) => {
                        let line = null;
                        try {
                            [line] = ins.read_line_finish_utf8(r2);
                        } catch (e) {
                            console.error(TAG, e);
                        }
                        try {
                            conn.close(null);
                        } catch (e) {}
                        this._safe(() => done(line));
                    });
                } catch (e) {
                    console.error(TAG, e);
                    this._safe(() => done(null));
                }
            });
        });
    }

    // ── leitura do estado ─────────────────────────────────

    _poll() {
        if (this._loading || !this._island)
            return;
        this._loading = true;
        const file = Gio.File.new_for_path(runtimeFile('state.json'));
        file.load_contents_async(null, (f, res) => {
            this._loading = false;
            if (!this._island)
                return;
            this._safe(() => {
                let state = null;
                try {
                    const [, contents] = f.load_contents_finish(res);
                    state = JSON.parse(new TextDecoder().decode(contents));
                    if (!state || typeof state !== 'object' || typeof state.state !== 'string')
                        state = null;
                } catch (e) {
                    state = null;
                }
                if (state) {
                    this._state = state;
                    this._failSince = null;
                } else {
                    this._state = null;
                    this._failSince ??= Date.now() / 1000;
                }
                this._render();
            });
        });
    }

    // ── desenho ───────────────────────────────────────────

    _render() {
        if (!this._island)
            return;
        const now = Date.now() / 1000;
        const s = this._state;

        if (!s) {
            if (this._failSince !== null && now - this._failSince >= MISSING_GRACE_S)
                this._show({mode: 'nostate', info: 'sem estado — plaud-ilha-watchd está rodando?'});
            else
                this._hide();
            return;
        }

        const updated = typeof s.updated_ts === 'number' ? s.updated_ts : Date.parse(s.updated) / 1000;
        const age = Number.isFinite(updated) ? now - updated : Infinity;
        if (age > STALE_S) {
            this._show({mode: 'stale', info: 'estado desatualizado — watchd parado'});
            return;
        }

        if (s.state === 'uploading') {
            this._stopping = null;
            this._show({mode: 'uploading', dot: '↑', info: s.phase === 'converting' ? 'convertendo…' : 'enviando…'});
            return;
        }
        if (s.state !== 'recording') {
            this._stopping = null;
            this._collapsedKey = null;
            this._hide();
            return;
        }
        if (this._stopping && now - this._stopping > STOP_TIMEOUT_S)
            this._stopping = null;

        const limits = Object.assign({}, DEFAULT_LIMITS, s.limits ?? {});
        const elapsed = (Number(s.elapsed_s) || 0) + Math.max(0, Math.floor(age));
        const free = Number(s.disk_free_gb);
        const warn = new Set(Array.isArray(s.warn) ? s.warn : []);
        if (elapsed >= limits.warn_hours * 3600)
            warn.add('duracao>3h');
        if (elapsed >= limits.critical_hours * 3600)
            warn.add('duracao>6h');
        if (Number.isFinite(free) && free < limits.disk_warn_gb)
            warn.add('disco<15gb');
        if (Number.isFinite(free) && limits.disk_stop_gb > 0 && free < limits.disk_stop_gb)
            warn.add('disco<5gb');
        warn.delete('sessao-antiga');
        this._currentWarn = warn;

        // Aviso novo reabre o notch recolhido — ocultar não pode esconder um alerta.
        if (this._isCollapsed() && [...warn].some(w => !this._collapsedWarn.has(w)))
            this._collapsedKey = null;

        const parts = [];
        if (Number.isFinite(Number(s.bytes)))
            parts.push(`${fmtNum(Number(s.bytes) / 1e9, 1)} GB`);
        if (Number.isFinite(free))
            parts.push(`livre ${Math.round(free)} GB`);

        let mode = 'recording';
        let anim = 'pulse';
        if (warn.has('travado')) {
            mode = 'stalled';
            anim = 'blink';
            parts.splice(0, parts.length, 'arquivo parou de crescer — recorder pode ter morrido');
        } else if (warn.has('sem-audio')) {
            mode = 'silence';
            anim = null;
            const min = Math.floor((Number(s.digital_silence_s) || 0) / 60);
            parts.splice(0, parts.length, `SEM ÁUDIO HÁ ${min} MIN`);
        } else if (warn.has('duracao>6h') || warn.has('disco<5gb')) {
            mode = 'critical';
            if (warn.has('duracao>6h'))
                parts.push(`PASSOU DE ${fmtHours(limits.critical_hours)} H`);
            if (warn.has('disco<5gb'))
                parts.push('DISCO QUASE CHEIO');
        } else if (warn.has('duracao>3h') || warn.has('disco<15gb')) {
            mode = 'warn';
            if (warn.has('duracao>3h'))
                parts.push(`PASSOU DE ${fmtHours(limits.warn_hours)} H`);
            if (warn.has('disco<15gb'))
                parts.push('DISCO BAIXO');
        }
        if (this._stopping)
            parts.splice(0, parts.length, 'parando…');

        this._show({
            mode,
            timer: fmtClock(elapsed),
            info: `· ${parts.join(' · ')}`,
            anim,
            stop: true,
            collapsed: this._isCollapsed(),
        });
    }

    _show({mode, timer = '', info = '', anim = null, dot = '●', stop = false, collapsed = false}) {
        for (const m of MODES) {
            const on = m === mode || (m === 'collapsed' && collapsed);
            if (on)
                this._island.add_style_class_name(m);
            else
                this._island.remove_style_class_name(m);
        }
        this._dot.text = dot;
        this._timer.text = timer;
        this._timer.visible = timer !== '';
        this._info.text = info;
        this._info.visible = !collapsed;
        this._hideBtn.visible = stop && !collapsed;

        const s = this._state;
        const canStop = !!(s && s.control && s.phase === 'recording' && !this._stopping);
        const confirming = canStop && Date.now() / 1000 <= this._confirmUntil;
        this._stopBtn.visible = stop && !collapsed;
        this._stopBtn.reactive = canStop;
        this._stopLabel.text = !s?.control ? 'sem controle'
            : this._stopping ? 'parando…'
                : confirming ? 'Confirmar' : 'Parar';
        if (confirming)
            this._stopBtn.add_style_class_name('confirm');
        else
            this._stopBtn.remove_style_class_name('confirm');
        if (canStop)
            this._stopBtn.remove_style_class_name('disabled');
        else
            this._stopBtn.add_style_class_name('disabled');

        this._setAnim(anim);
        if (!this._island.visible) {
            this._island.show();
            this._setUnredirect(true);
        }
        this._reposition();
    }

    _hide() {
        if (this._island.visible) {
            this._island.hide();
            this._setAnim(null);
            this._setUnredirect(false);
        }
    }

    _setAnim(anim) {
        if (anim === this._anim)
            return;
        this._anim = anim;
        this._dot.remove_all_transitions();
        this._dot.opacity = 255;
        if (!anim)
            return;
        this._dot.ease({
            opacity: 140, // 0,55
            duration: anim === 'blink' ? 250 : 1000,
            mode: Clutter.AnimationMode.EASE_IN_OUT_SINE,
            repeatCount: -1,
            autoReverse: true,
        });
    }

    // Em fullscreen o Mutter pode mandar a janela direto para a tela
    // (unredirect/scanout) e pular a composição — o notch sumiria.
    _setUnredirect(visible) {
        if (visible === this._unredirectOff)
            return;
        this._unredirectOff = visible;
        // GNOME 47+: global.compositor; 46: Meta.*_for_display.
        const comp = global.compositor;
        if (comp?.disable_unredirect) {
            if (visible)
                comp.disable_unredirect();
            else
                comp.enable_unredirect();
        } else if (visible) {
            Meta.disable_unredirect_for_display(global.display);
        } else {
            Meta.enable_unredirect_for_display(global.display);
        }
    }

    // Centralizado sob o relógio, colado na borda de baixo do painel; em
    // fullscreen (painel escondido) cola no topo do monitor.
    _reposition() {
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor || !this._island)
            return;
        const panel = Main.layoutManager.panelBox;
        const panelVisible = panel.visible && !monitor.inFullscreen;
        let centerX = monitor.x + monitor.width / 2;
        const clock = Main.panel?.statusArea?.dateMenu;
        if (clock && panelVisible) {
            const [cx] = clock.get_transformed_position();
            if (clock.width > 0)
                centerX = cx + clock.width / 2;
        }
        const width = this._island.width;
        const x = Math.max(monitor.x, Math.min(monitor.x + monitor.width - width, Math.round(centerX - width / 2)));
        const y = monitor.y + (panelVisible ? panel.height : 0);
        this._island.set_position(x, y);
    }
}
