/* plugins.js — каталог плагинов: «Установлено» / «Магазин», поиск, категории. */
'use strict';

/* Короткий туториал над полем: пронумерованные шаги и кнопка-ссылка.
   Поле описывает его само (ключи guide / guide_title / link), поэтому
   каталог остаётся единственным местом, где живёт текст подсказки. */
function settingGuide(field) {
  if (!field.guide && !field.link) return null;
  const box = el('div', 'plug-guide');
  if (field.guide_title) box.appendChild(el('b', '', t(field.guide_title)));
  if ((field.guide || []).length) {
    const list = el('ol');
    field.guide.forEach(step => list.appendChild(el('li', '', t(step))));
    box.appendChild(list);
  }
  if (field.link && field.link.url) {
    const link = el('a', 'btn sm plug-link', t(field.link.label || field.link.url));
    link.href = field.link.url;
    link.target = '_blank';
    link.rel = 'noreferrer';
    box.appendChild(link);
  }
  return box;
}

/* Одна строка настроек плагина. Текст и пароль — поле ввода, checkbox —
   такой же переключатель, как у самого плагина: значение уходит булевым и
   применяется сразу, без перезапуска. */
function settingRow(field, save) {
  if (field.type === 'checkbox') {
    const row = el('div', 'plug-field is-check');
    row.appendChild(el('span', '', t(field.label)));
    const sw = el('div', 'sw sm' + (field.value ? ' on' : ''));
    sw.setAttribute('role', 'switch');
    sw.setAttribute('aria-checked', field.value ? 'true' : 'false');
    sw.setAttribute('aria-label', t(field.label));
    sw.onclick = () => {
      const next = !sw.classList.contains('on');
      sw.classList.toggle('on', next);
      sw.setAttribute('aria-checked', next ? 'true' : 'false');
      save({ [field.key]: next });
    };
    row.appendChild(sw);
    if (field.hint) row.appendChild(el('small', '', t(field.hint)));
    return row;
  }
  /* Список вариантов: раньше такого типа не было совсем, и любой выбор
     приходилось изображать текстовым полем, куда надо вписать значение
     руками. */
  if (field.type === 'select') {
    const row = el('label', 'plug-field');
    row.innerHTML = `<span>${t(field.label)}</span>`;
    const pick = el('select');
    (field.options || []).forEach(option => {
      const node = document.createElement('option');
      node.value = option.value;
      node.textContent = t(option.label || option.value);
      pick.appendChild(node);
    });
    pick.value = field.value || field.default || '';
    pick.onchange = () => { field.value = pick.value; save({ [field.key]: pick.value }); };
    row.appendChild(pick);
    if (field.hint) row.appendChild(el('small', '', t(field.hint)));
    return row;
  }
  const row = el('label', 'plug-field');
  row.innerHTML = `<span>${t(field.label)}</span>`;
  const input = el('input');
  input.type = field.type === 'password' ? 'password' : 'text';
  input.value = field.value || '';
  input.placeholder = field.placeholder || '';
  // Сохраняем и по Enter: иначе значение уходит только после клика мимо поля,
  // и пользователь думает, что ключ не принялся.
  const commit = () => {
    const value = input.value.trim();
    if (value === (field.value || '')) return;
    field.value = value;
    save({ [field.key]: value });
  };
  input.onchange = commit;
  input.onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); commit(); } };
  row.appendChild(input);
  if (field.hint) row.appendChild(el('small', '', t(field.hint)));
  return row;
}

const Plugins = {
  data: [],
  categories: [],
  tab: 'installed',
  cat: 'all',
  query: '',
  loaded: false,
  busy: new Set(),
  tests: {},          /* id → результат живой проверки */
  testing: new Set(),

  async load(force = false) {
    if (this.loaded && !force) { this.render(); return; }
    const box = $('plugList');
    if (box && !this.loaded) box.innerHTML = `<div class="plug-empty">${t('Loading…')}</div>`;
    try {
      const data = await api('/api/plugins');
      this.data = data.plugins || [];
      this.categories = data.categories || [];
      this.loaded = true;
    } catch {
      if (box) box.innerHTML = `<div class="plug-empty">${t('Server is not responding')}</div>`;
      return;
    }
    this.renderCategories();
    this.render();
  },

  get(id) { return this.data.find(p => p.id === id); },

  /* ------------------------------------------------------------ категории */
  renderCategories() {
    const box = $('plugCats');
    if (!box) return;
    box.innerHTML = '';
    this.categories.forEach(cat => {
      const chip = el('button', 'chip' + (this.cat === cat.id ? ' on' : ''), t(cat.name));
      chip.onclick = () => { this.cat = cat.id; this.renderCategories(); this.render(); };
      box.appendChild(chip);
    });
  },

  visible() {
    const query = this.query.trim().toLowerCase();
    return this.data.filter(plugin => {
      if (this.tab === 'installed' && !plugin.installed) return false;
      if (this.cat !== 'all' && !plugin.categories.includes(this.cat)) return false;
      if (!query) return true;
      return (plugin.name + ' ' + plugin.description + ' ' + plugin.categories.join(' '))
        .toLowerCase().includes(query);
    });
  },

  /* ---------------------------------------------------------------- карта */
  card(plugin) {
    const card = el('div', 'plug' + (plugin.installed ? ' is-on' : '') +
                             (plugin.installed && !plugin.enabled ? ' is-off' : ''));

    const head = el('div', 'plug-head');
    const title = el('div', 'plug-title');
    const madeBy = plugin.plugin_author && plugin.plugin_author !== plugin.author
      ? `<span class="by">${t('plugin by')} ${plugin.plugin_author}</span>` : '';
    title.innerHTML =
      `<b>${plugin.name}</b>` +
      `<span class="by">${t('by')} ${plugin.author}</span>` +
      madeBy +
      `<span class="ver">v${plugin.version}</span>` +
      plugin.categories.map(c => `<span class="tag t-${c}">${t(this.catName(c))}</span>`).join('') +
      (plugin.core ? `<span class="tag t-core">${t('built-in')}</span>` : '');
    head.appendChild(title);

    const acts = el('div', 'plug-acts');
    if (plugin.installed) {
      const sw = el('div', 'sw' + (plugin.enabled ? ' on' : ''));
      sw.title = plugin.enabled ? t('Turn off') : t('Turn on');
      sw.onclick = () => this.toggle(plugin.id, !plugin.enabled);
      acts.appendChild(sw);
      const check = el('button', 'btn g sm', t('Test'));
      check.disabled = this.testing.has(plugin.id);
      check.onclick = () => this.test(plugin.id);
      acts.appendChild(check);
      const btn = el('button', 'btn g sm', plugin.core ? t('Installed') : t('Remove'));
      btn.disabled = !!plugin.core || this.busy.has(plugin.id);
      if (!plugin.core) btn.onclick = () => this.uninstall(plugin.id);
      acts.appendChild(btn);
    } else {
      const btn = el('button', 'btn sm', t('Install'));
      btn.disabled = this.busy.has(plugin.id);
      btn.onclick = () => this.install(plugin.id);
      acts.appendChild(btn);
    }
    head.appendChild(acts);
    card.appendChild(head);

    card.appendChild(el('div', 'plug-desc', t(plugin.description)));

    const meta = el('div', 'plug-meta');
    const bits = [];
    if (plugin.homepage) {
      bits.push(`<a href="${plugin.homepage}" target="_blank" rel="noreferrer">` +
                `${plugin.homepage.replace(/^https?:\/\//, '')}</a>`);
    }
    if (plugin.api) bits.push(`${t('API')}: ${plugin.api}`);
    if ((plugin.credits || []).length) {
      bits.push(`${t('Uses')}: ` + plugin.credits.map(c =>
        c.url ? `<a href="${c.url}" target="_blank" rel="noreferrer">${c.name}</a>` : c.name
      ).join(', '));
    }
    if (bits.length) {
      meta.innerHTML = bits.join(' · ');
      card.appendChild(meta);
    }

    if (!plugin.ready && plugin.note) {
      card.appendChild(el('div', 'plug-warn', '⚠ ' + t(plugin.note)));
    }

    const probe = this.tests[plugin.id];
    if (this.testing.has(plugin.id)) {
      card.appendChild(el('div', 'plug-test', t('Testing…')));
    } else if (probe) {
      const row = el('div', 'plug-test s-' + probe.state);
      // Заметка проверки приходит английским шаблоном: переводим её здесь.
      const note = (probe.note_key ? tf(probe.note_key, probe.note_args) : tParts(probe.note)) +
        (probe.off_note ? ' ' + t(probe.off_note) : '');
      row.setAttribute('data-no-i18n', '');
      row.textContent = `${this.stateLabel(probe.state)} · ${note}` +
        (probe.ms ? ` · ${probe.ms} ${t('ms')}` : '');
      card.appendChild(row);
    }

    if (plugin.installed && plugin.settings.length) {
      const form = el('div', 'plug-form');
      plugin.settings.forEach(field => {
        const guide = settingGuide(field);
        if (guide) form.appendChild(guide);
        form.appendChild(settingRow(field, values => this.save(plugin.id, values)));
      });
      card.appendChild(form);
    }
    return card;
  },

  catName(id) {
    const hit = this.categories.find(c => c.id === id);
    return hit ? hit.name : id;
  },

  stateLabel(state) {
    return t({ ok: 'Works', warn: 'Answers, but empty', fail: 'Does not work',
               off: 'Not set up', skip: 'Local plugin' }[state] || state);
  },

  /* --------------------------------------------------- живая проверка */
  /* Проверять ли выключенные плагины: запрос уходит напрямую в сервис. */
  force() {
    const node = $('plugTestForce');
    return !!(node && node.classList.contains('on'));
  },

  async test(id) {
    this.testing.add(id);
    this.render();
    try {
      this.tests[id] = await api(`/api/plugins/${id}/selftest`,
        { method: 'POST', body: { force: this.force() } });
    } catch (err) {
      this.tests[id] = { state: 'fail', note: err.message || t('Error'), ms: 0 };
    } finally {
      this.testing.delete(id);
      this.render();
    }
  },

  async testAll() {
    const force = this.force();
    const ids = this.data
      .filter(p => p.installed && (force || p.enabled)).map(p => p.id);
    if (!ids.length) { toast(t('No plugins here yet')); return; }
    ids.forEach(id => this.testing.add(id));
    this.render();
    try {
      const data = await api('/api/plugins/selftest',
        { method: 'POST', body: { ids, force } });
      (data.items || []).forEach(row => { this.tests[row.id] = row; });
      const okay = (data.summary || {}).ok || 0;
      toast(`${t('Works')}: ${okay} / ${data.checked || ids.length}`);
    } catch (err) {
      toast(err.message || t('Error'));
    } finally {
      ids.forEach(id => this.testing.delete(id));
      this.render();
    }
  },

  render() {
    const box = $('plugList');
    if (!box) return;
    document.querySelectorAll('#plugTabs .chip').forEach(chip =>
      chip.classList.toggle('on', chip.dataset.ptab === this.tab));
    const items = this.visible();
    box.innerHTML = '';
    if (!items.length) {
      box.appendChild(el('div', 'plug-empty',
        this.tab === 'installed' ? t('No plugins here yet') : t('Nothing found')));
      return;
    }
    items.forEach(plugin => box.appendChild(this.card(plugin)));
    const counter = $('plugCount');
    if (counter) {
      const total = this.data.length;
      const on = this.data.filter(p => p.installed).length;
      counter.textContent = `${on} / ${total}`;
    }
  },

  /* -------------------------------------------------------------- команды */
  async call(id, path, opts) {
    this.busy.add(id);
    this.render();
    try {
      const data = await api(path, opts);
      this.data = data.plugins || this.data;
      dropCache();
      App.checkHealth && App.checkHealth();
    } catch (err) {
      toast(err.message || t('Error'));
    } finally {
      this.busy.delete(id);
      this.render();
    }
  },

  async install(id) {
    await this.call(id, `/api/plugins/${id}/install`, { method: 'POST' });
    const plugin = this.get(id);
    toast(`${plugin ? plugin.name : id} — ${t('installed')}`);
    if (plugin && plugin.source) {
      // Новая библиотека сразу участвует в поиске.
      if (!(S.sources || []).includes(plugin.source)) {
        S.sources = [...(S.sources || []), plugin.source];
      }
      this.syncSources();
    }
  },

  async uninstall(id) {
    await this.call(id, `/api/plugins/${id}/uninstall`, { method: 'POST' });
    toast(t('Plugin removed'));
    this.syncSources();
  },

  async toggle(id, value) {
    await this.call(id, `/api/plugins/${id}/toggle`,
      { method: 'POST', body: { enabled: value } });
    this.syncSources();
  },

  async save(id, values) {
    await this.call(id, `/api/plugins/${id}/config`, { method: 'PUT', body: values });
    toast(t('Saved'));
  },

  /* Список активных источников поиска держим в настройках в согласии с каталогом. */
  syncSources() {
    const sources = this.data
      .filter(p => p.source && p.installed && p.enabled)
      .map(p => p.source);
    if (!sources.length) return;
    S.sources = (S.sources || []).filter(s => sources.includes(s));
    if (!S.sources.length) S.sources = sources.slice();
    saveSettings();
    dropCache('/api/search');
    App.buildLibraries && App.buildLibraries();
  },

  bind() {
    const tabs = $('plugTabs');
    if (tabs) {
      tabs.onclick = event => {
        const chip = event.target.closest('[data-ptab]');
        if (!chip) return;
        this.tab = chip.dataset.ptab;
        this.render();
      };
    }
    const search = $('plugSearch');
    if (search) {
      search.addEventListener('input', debounce(() => {
        this.query = search.value;
        this.render();
      }, 140));
    }
    const reset = $('plugReset');
    if (reset) {
      reset.onclick = async () => {
        await this.call('*', '/api/plugins/reset', { method: 'POST' });
        toast(t('Plugin catalogue reset'));
        this.syncSources();
      };
    }
    const testAll = $('plugTestAll');
    if (testAll) testAll.onclick = () => this.testAll();
    const force = $('plugTestForce');
    if (force) force.onclick = () => force.classList.toggle('on');
  },
};
