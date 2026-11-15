// Plaud Ilha — indicador flutuante de gravação para GNOME Shell 46 (Wayland).
//
// Lê $XDG_RUNTIME_DIR/plaud-ilha/state.json (escrito pelo plaud-ilha-watchd)
// uma vez por segundo e desenha uma "ilha" no topo do monitor principal.
// Nunca pega foco de teclado; todo callback é protegido por try/catch porque
// uma exceção não tratada aqui derruba a sessão inteira.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const TAG = 'plaud-ilha';
const STALE_S = 5;
const MISSING_GRACE_S = 5;
const STOP_TIMEOUT_S = 120;
const MARGIN = 8;
const MODES = ['recording', 'warn', 'critical', 'silence', 'stalled', 'stale', 'uploading', 'nostate'];
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

export default class PlaudIlhaExtension extends Extension {
    enable() {
        this._state = null;
        this._failSince = null;
        this._loading = false;
        this._stopping = null;
        this._anim = null;
        this._unredirectOff = false;
        this._signals = [];

        this._dot = new St.Label({text: '●', style_class: 'plaud-ilha-dot', y_align: Clutter.ActorAlign.CENTER});
        this._timer = new St.Label({text: '', style_class: 'plaud-ilha-timer', y_align: Clutter.ActorAlign.CENTER});
        this._info = new St.Label({text: '', style_class: 'plaud-ilha-info', y_align: Clutter.ActorAlign.CENTER});

        const box = new St.BoxLayout({style_class: 'plaud-ilha-box', y_align: Clutter.ActorAlign.CENTER});
        box.add_child(this._dot);
        box.add_child(this._timer);
        box.add_child(this._info);

        this._island = new St.Button({
            style_class: 'plaud-ilha',
            child: box,
            reactive: true,
            can_focus: false,
            track_hover: true,
            visible: false,
        });
        this._island.connect('clicked', () => this._safe(() => this._menu.toggle()));

        Main.layoutManager.addChrome(this._island, {
            affectsStruts: false,
            affectsInputRegion: true,
            // true esconderia a ilha em fullscreen (layout.js#_updateActorVisibility)
            trackFullscreen: false,
        });

        this._buildMenu();

        this._signals.push([this._island, this._island.connect('notify::width', () => this._safe(() => this._reposition()))]);
        this._signals.push([Main.layoutManager, Main.layoutManager.connect('monitors-changed', () => this._safe(() => this._reposition()))]);
        this._signals.push([global.display, global.display.connect('workareas-changed', () => this._safe(() => this._reposition()))]);

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

        this._menuManager = null;
        this._menu?.destroy();
        this._menu = null;
        if (this._island) {
            Main.layoutManager.removeChrome(this._island);
            this._island.destroy();
        }
        this._island = this._dot = this._timer = this._info = null;
        this._stopItem = this._openItem = this._copyItem = null;
        this._state = null;
    }

    _safe(fn) {
        try {
            fn();
        } catch (e) {
            console.error(TAG, e);
        }
    }

    // ── menu ───────────────────────────────────────────────

    _buildMenu() {
        this._menu = new PopupMenu.PopupMenu(this._island, 0.5, St.Side.TOP);
        Main.uiGroup.add_child(this._menu.actor);
        this._menu.actor.hide();
        this._menuManager = new PopupMenu.PopupMenuManager(this._island);
        this._menuManager.addMenu(this._menu);

        this._stopItem = new PopupMenu.PopupMenuItem('Parar gravação');
        this._stopItem.connect('activate', () => this._safe(() => this._requestStop()));
        this._menu.addMenuItem(this._stopItem);

        this._openItem = new PopupMenu.PopupMenuItem('Abrir pasta de gravações');
        this._openItem.connect('activate', () => this._safe(() => this._openFolder()));
        this._menu.addMenuItem(this._openItem);

        this._copyItem = new PopupMenu.PopupMenuItem('Copiar caminho do arquivo');
        this._copyItem.connect('activate', () => this._safe(() => this._copyPath()));
        this._menu.addMenuItem(this._copyItem);
    }

    _updateMenu() {
        const s = this._state;
        const canStop = !!(s && s.control && s.phase === 'recording' && !this._stopping);
        this._stopItem.setSensitive(canStop);
        this._stopItem.label.text = s && !s.control
            ? 'Parar gravação (requer plaud-ilha-control)'
            : this._stopping ? 'Parando…' : 'Parar gravação';
        this._copyItem.setSensitive(!!(s && s.files && s.files.length));
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

    _openFolder() {
        const dir = this._state?.recordings_dir ?? GLib.build_filenamev([GLib.get_home_dir(), '.plaud-linux', 'recordings']);
        Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(dir, null),
            global.create_app_launch_context(0, -1));
    }

    _copyPath() {
        const files = this._state?.files ?? [];
        if (files.length)
            St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, files.join('\n'));
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
                this._show('nostate', '', 'sem estado — plaud-ilha-watchd está rodando?', null);
            else
                this._hide();
            return;
        }

        const updated = typeof s.updated_ts === 'number' ? s.updated_ts : Date.parse(s.updated) / 1000;
        const age = Number.isFinite(updated) ? now - updated : Infinity;
        if (age > STALE_S) {
            this._show('stale', '', 'estado desatualizado — watchd parado', null);
            return;
        }

        if (s.state === 'uploading') {
            this._stopping = null;
            this._show('uploading', '', s.phase === 'converting' ? 'convertendo…' : 'enviando…', null, '↑');
            return;
        }
        if (s.state !== 'recording') {
            this._stopping = null;
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
        if (warn.has('sessao-antiga'))
            parts.push('há WAV antigo');
        if (this._stopping)
            parts.splice(0, parts.length, 'parando…');

        this._show(mode, fmtClock(elapsed), `· ${parts.join(' · ')}`, anim);
    }

    _show(mode, timer, info, anim, dot = '●') {
        for (const m of MODES) {
            if (m === mode)
                this._island.add_style_class_name(m);
            else
                this._island.remove_style_class_name(m);
        }
        this._dot.text = dot;
        this._timer.text = timer;
        this._timer.visible = timer !== '';
        this._info.text = info;
        this._setAnim(anim);
        this._updateMenu();
        if (!this._island.visible) {
            this._island.show();
            this._setUnredirect(true);
        }
        this._reposition();
    }

    _hide() {
        if (this._island.visible) {
            this._menu.close();
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
    // (unredirect/scanout) e pular a composição — a ilha sumiria.
    _setUnredirect(visible) {
        if (visible === this._unredirectOff)
            return;
        this._unredirectOff = visible;
        if (visible)
            Meta.disable_unredirect_for_display(global.display);
        else
            Meta.enable_unredirect_for_display(global.display);
    }

    _reposition() {
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor || !this._island)
            return;
        const width = this._island.width;
        const x = Math.max(monitor.x + MARGIN, monitor.x + Math.floor((monitor.width - width) / 2));
        const y = monitor.y + Main.layoutManager.panelBox.height + MARGIN;
        this._island.set_position(x, y);
    }
}
