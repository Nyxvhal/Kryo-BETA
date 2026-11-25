/* settings-extra.js — экраны «Интеграции», «Логи», «Сочетания клавиш», «Что нового». */
'use strict';

/* ------------------------------------------------------------ интеграции */
const Integrations = {
  items: [],
  busy: false,

  async load() {
    const box = $('intList');
    if (!box) return;
    if (!this.items.length) box.innerHTML = `<div class="plug-empty">${t('Loading…')}</div>`;
    try {
      const [state, catalogue] = await Promise.all([
        api('/api/integrations'),
        Plugins.loaded ? Promise.resolve({ plugins: Plugins.data }) : api('/api/plugins'),
      ]);
      const byId = new Map((catalogue.plugins || []).map(p => [p.id, p]));
      this.items = (state.items || []).map(item => ({ ...item, plugin: byId.get(item.id) }));
    } catch {
      box.innerHTML = `<div class="plug-empty">${t('Server is not responding')}</div>`;
      return;
    }
    this.render();
  },

  render() {
    const box = $('intList');
    box.innerHTML = '';
    this.items.forEach(item => {
      const plugin = item.plugin || {};
      const card = el('div', 'plug' + (item.enabled ? ' is-on' : ''));

      const head = el('div', 'plug-head');
      head.appendChild(el('div', 'plug-title',
        `<b>${item.name}</b><span class="by">${t('by')} ${item.author}</span>` +
        `<span class="tag t-${item.kind === 'scrobbling' ? 'scrobbling' : 'other'}">` +
        `${t(item.kind === 'scrobbling' ? 'Scrobbling' : 'Integrations')}</span>` +
        (item.live ? `<span class="tag t-core">${t('connected')}</span>` : '')));

      const acts = el('div', 'plug-acts');
      const sw = el('div', 'sw' + (item.enabled ? ' on' : ''));
      sw.onclick = async () => {
        if (!item.installed) await Plugins.install(item.id);
        else await Plugins.toggle(item.id, !item.enabled);
        this.load();
      };
      acts.appendChild(sw);
      const test = el('button', 'btn g sm', t('Test'));
      test.onclick = () => this.test(item.id, test);
      acts.appendChild(test);
      head.appendChild(acts);
      card.appendChild(head);

      if (plugin.description) card.appendChild(el('div', 'plug-desc', t(plugin.description)));

      const form = el('div', 'plug-form');
      (plugin.settings || []).forEach(field => {
        form.appendChild(settingRow(field, async values => {
          await Plugins.save(item.id, values);
          this.load();
        }));
      });
      if ((plugin.settings || []).length) card.appendChild(form);

      const state = el('div', 'plug-meta', item.id + ' · ' +
        (item.enabled ? t('on') : t('off')) + ' · ' +
        (item.configured ? t('configured') : t('not configured')) +
        (item.live && item.account ? ' · ' + t('Connected as') + ' ' + item.account : ''));
      card.appendChild(state);
      // Что именно сейчас видно в профиле Discord: без этого непонятно,
      // показывает Discord нашу карточку или свою «обнаруженную игру».
      if (item.enabled && item.note) {
        card.appendChild(el('div', 'plug-meta', t(item.note)));
      }
      // Почему статус не появился — пишем прямо в карточке, а не только в логах.
      if (item.enabled && item.error) {
        const why = el('div', 'plug-why', t(item.error));
        card.appendChild(why);
      }

      if (item.id === 'mastodon' && item.enabled) {
        const share = el('button', 'btn g sm', t('Share current track'));
        share.style.marginTop = '10px';
        share.onclick = () => this.share();
        card.appendChild(share);
      }
      box.appendChild(card);
    });
  },

  async test(id, button) {
    const label = button.textContent;
    button.textContent = '…';
    button.disabled = true;
    try {
      const data = await api(`/api/integrations/${id}/test`, { method: 'POST' });
      toast(`${id}: ${data.message ? tParts(data.message) : (data.ok ? 'ok' : t('Error'))}`);
    } catch (err) {
      toast(err.message || t('Error'));
    } finally {
      button.textContent = label;
      button.disabled = false;
      this.load();
    }
  },

  async share() {
    if (!Player.current) { toast(t('Nothing is playing')); return; }
    try {
      const data = await api('/api/integrations/mastodon/share',
        { method: 'POST', body: { track: Player.current } });
      toast(data.url ? t('Shared') : t('Error'));
    } catch (err) { toast(err.message || t('Error')); }
  },

  bind() {
    const refresh = $('intRefresh');
    if (refresh) refresh.onclick = () => { this.load(); toast(t('Checking')); };
  },
};

/* ------------------------------------------------------------------ логи */
const Logs = {
  level: '',
  query: '',
  items: [],
  timer: null,

  async load() {
    const box = $('logList');
    if (!box) return;
    const params = new URLSearchParams({ limit: '300' });
    if (this.level) params.set('level', this.level);
    if (this.query.trim()) params.set('q', this.query.trim());
    try {
      const data = await api('/api/logs?' + params.toString());
      this.items = data.items || [];
      const counts = data.counts || {};
      const counter = $('logCount');
      if (counter) {
        counter.textContent =
          `${counts.total || 0} · ${t('errors')}: ${(counts.error || 0) + (counts.critical || 0)}`;
      }
      this.buildLevels(data.levels || []);
    } catch {
      box.innerHTML = `<div class="plug-empty">${t('Server is not responding')}</div>`;
      return;
    }
    this.render();
  },

  buildLevels(levels) {
    const box = $('logLevels');
    if (!box || box.dataset.ready) return;
    box.dataset.ready = '1';
    [['', 'All'], ...levels.map(l => [l, l[0].toUpperCase() + l.slice(1)])]
      .forEach(([id, label]) => {
        const chip = el('button', 'chip' + (this.level === id ? ' on' : ''), t(label));
        chip.dataset.level = id;
        chip.onclick = () => {
          this.level = id;
          box.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', c === chip));
          this.load();
        };
        box.appendChild(chip);
      });
  },

  render() {
    const box = $('logList');
    box.innerHTML = '';
    if (!this.items.length) {
      box.innerHTML = `<div class="plug-empty">${t('The log is empty')}</div>`;
      return;
    }
    const frag = document.createDocumentFragment();
    this.items.forEach(item => {
      const row = el('div', 'log-row lv-' + item.level);
      row.innerHTML =
        `<span class="log-t">${item.time.slice(11)}</span>` +
        `<span class="log-l">${item.level}</span>` +
        `<span class="log-s">${esc(item.logger)}</span>` +
        `<span class="log-m">${esc(typeof tLog === 'function' ? tLog(item.message) : item.message)}</span>`;
      frag.appendChild(row);
    });
    box.appendChild(frag);
    if (S.logFollow !== false) box.scrollTop = box.scrollHeight;
  },

  start() {
    this.load();
    this.stop();
    this.timer = setInterval(() => {
      if (S.logFollow !== false && $('mSettings').classList.contains('on')
          && document.querySelector('.pane[data-pane=logs]').classList.contains('on')) {
        this.load();
      }
    }, 4000);
  },

  stop() { if (this.timer) { clearInterval(this.timer); this.timer = null; } },

  bind() {
    const search = $('logSearch');
    if (search) {
      search.addEventListener('input', debounce(() => {
        this.query = search.value;
        this.load();
      }, 200));
    }
    const refresh = $('logRefresh');
    if (refresh) refresh.onclick = () => this.load();
    const clear = $('logClear');
    if (clear) {
      clear.onclick = async () => {
        await api('/api/logs', { method: 'DELETE' }).catch(() => {});
        this.load();
        toast(t('Log cleared'));
      };
    }
    const copy = $('logCopy');
    if (copy) {
      copy.onclick = async () => {
        const text = this.items.map(i =>
          `${i.time} ${i.level.toUpperCase()} ${i.logger}: ${i.message}`).join('\n');
        try {
          await navigator.clipboard.writeText(text);
          toast(t('Copied'));
        } catch { toast(t('Error')); }
      };
    }
  },
};

/* -------------------------------------------------------- горячие клавиши */
const HOTKEYS = [
  ['Space', 'Play / pause'],
  ['→ / ←', 'Seek 5 seconds'],
  ['Shift + → / ←', 'Next / previous track'],
  ['↑ / ↓', 'Volume'],
  ['L', 'Like the current track'],
  ['Q', 'Queue'],
  ['S', 'Shuffle'],
  ['R', 'Repeat'],
  ['F', 'Full-screen player'],
  ['M', 'Mixer and equalizer'],
  ['T', 'Nudge the lyrics to the beat'],
  ['/', 'Focus search'],
  ['F11', 'Full screen'],
  ['Ctrl + Alt + ← / →', 'Snap the window to the left or right half'],
  ['Ctrl + Alt + ↑', 'Maximize or restore the window'],
  ['Ctrl + Alt + ↓', 'Center the window'],
  ['Esc', 'Close panels'],
  ['Space', 'Clips: pause the video'],
  ['J / L', 'Clips: 10 seconds back or forward'],
  ['0 … 9', 'Clips: jump across the video'],
  ['F', 'Clips: full screen'],
  ['N', 'Clips: next video'],
];

const Hotkeys = {
  build() {
    const box = $('keysList');
    if (!box) return;
    // Список строим заново на каждый заход: раньше стоял флаг dataset.ready,
    // и после смены языка подписи оставались на прежнем языке.
    box.innerHTML = '';
    HOTKEYS.forEach(([key, what]) => {
      const row = el('div', 'set');
      row.appendChild(el('div', '', `<div class="l">${t(what)}</div>`));
      // Названия клавиш тоже переводятся: «Space» и «Esc» на русском читаются
      // как «Пробел» и «Esc», стрелки остаются стрелками.
      row.appendChild(el('div', 'c', `<kbd>${esc(t(key))}</kbd>`));
      box.appendChild(row);
    });
  },
};

/* ------------------------------------------------------------ что нового
   Сборка 1.0.0 ещё не выпущена, и список изменений в ней не ведётся:
   экран показывает только отметку о предварительной версии. */
const News = {
  build() {
    const box = $('newsList');
    if (!box) return;
    // Блок перерисовываем заново: иначе после смены языка тут остаётся
    // текст на прежнем языке.
    // Список обновлений пока пуст: это первая версия.
    box.innerHTML = '';
  },
};
