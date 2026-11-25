/* custom.js — свои плагины и свои библиотеки.

   Раздел живёт внизу экрана «Плагины». Он показывает папки, что загрузилось,
   что не загрузилось и почему, и даёт четыре действия: перечитать, добавить
   файл (или перетащить его в окно), поставить библиотеку через pip, удалить.
   Перезапуск приложению не нужен: сервер импортирует плагины на месте. */
'use strict';

const CustomPlugins = {
  data: null,
  busy: false,

  async load(force = false) {
    if (this.data && !force) { this.render(); return; }
    try {
      this.data = await api('/api/plugins/custom');
    } catch {
      this.data = { items: [], errors: [], libs: [], plugins_dirs: [], lib_dirs: [] };
    }
    this.render();
  },

  /* Любой ответ этих ручек содержит и свежий каталог плагинов: обновляем оба
     списка сразу, чтобы карточка нового плагина появилась без перезагрузки. */
  async act(path, opts, done) {
    if (this.busy) return;
    this.busy = true;
    this.render();
    try {
      const answer = await api(path, opts);
      this.data = answer;
      if (answer.catalog) {
        Plugins.data = answer.catalog.plugins || Plugins.data;
        Plugins.categories = answer.catalog.categories || Plugins.categories;
        Plugins.render();
      }
      dropCache();
      if (done) toast(done);
    } catch (err) {
      toast(err.message || t('Error'));
    } finally {
      this.busy = false;
      this.render();
      App.buildLibraries && App.buildLibraries();
    }
  },

  async upload(file) {
    if (!file) return;
    const form = new FormData();
    form.append('file', file, file.name);
    this.busy = true;
    this.render();
    try {
      const res = await fetch('/api/plugins/custom/upload', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || t('Error'));
      this.data = data;
      if (data.catalog) { Plugins.data = data.catalog.plugins || Plugins.data; Plugins.render(); }
      dropCache();
      toast(`${file.name} — ${t('installed')}`);
    } catch (err) {
      toast(err.message || t('Error'));
    } finally {
      this.busy = false;
      this.render();
    }
  },

  pathRow(label, value) {
    const row = el('div', 'cust-path');
    row.appendChild(el('span', '', t(label)));
    const code = el('code', '', esc(value));
    code.title = t('Click to copy');
    code.onclick = () => {
      navigator.clipboard && navigator.clipboard.writeText(value);
      toast(t('Path copied'));
    };
    row.appendChild(code);
    return row;
  },

  item(entry) {
    const card = el('div', 'cust-item' + (entry.enabled ? '' : ' is-off'));
    const head = el('div', 'cust-item-head');
    head.innerHTML =
      `<b>${esc(entry.name)}</b><span class="ver">v${esc(entry.version)}</span>` +
      (entry.author ? `<span class="by">${t('by')} ${esc(entry.author)}</span>` : '') +
      (entry.hooks || []).map(h => `<span class="tag">${h}()</span>`).join('');
    const acts = el('div', 'cust-acts');
    const test = el('button', 'btn g sm', t('Test'));
    test.onclick = () => Plugins.test(entry.id);
    acts.appendChild(test);
    const drop = el('button', 'btn g sm', t('Delete file'));
    drop.disabled = this.busy;
    drop.onclick = () => this.act(`/api/plugins/custom/${entry.id}`,
      { method: 'DELETE' }, t('Plugin removed'));
    acts.appendChild(drop);
    head.appendChild(acts);
    card.appendChild(head);
    card.appendChild(el('div', 'cust-desc', entry.description || ''));
    card.appendChild(el('code', 'cust-file', esc(entry.path)));
    if (entry.source) {
      card.appendChild(el('small', '', `${t('Search source')}: ${entry.source}`));
    }
    return card;
  },

  error(entry) {
    const card = el('div', 'cust-item is-bad');
    card.appendChild(el('div', 'cust-item-head', `<b>${entry.path.split(/[\\/]/).pop()}</b>` +
      `<span class="tag t-bad">${t('did not load')}</span>`));
    card.appendChild(el('div', 'cust-desc', esc(entry.error)));
    if ((entry.trace || []).length) {
      const pre = el('pre', 'cust-trace', entry.trace.join('\n'));
      card.appendChild(pre);
    }
    return card;
  },

  lib(entry) {
    const row = el('div', 'cust-lib');
    row.appendChild(el('span', '', esc(entry.name)));
    row.appendChild(el('small', '', entry.kind === 'package'
      ? `${Math.max(1, Math.round(entry.size / 1024))} KB` : t('file')));
    if (entry.protected) {
      /* Зависимость самого плеера: её удаление сломало бы следующий запуск. */
      row.appendChild(el('small', 'cust-core', t('needed by the player')));
      return row;
    }
    const drop = el('button', 'btn g sm', t('Remove'));
    drop.disabled = this.busy;
    drop.onclick = () => this.act(`/api/plugins/libs/${encodeURIComponent(entry.name)}`,
      { method: 'DELETE' }, t('Library removed'));
    row.appendChild(drop);
    return row;
  },

  render() {
    const box = $('custBox');
    if (!box || !this.data) return;
    const data = this.data;
    box.innerHTML = '';

    (data.plugins_dirs || []).forEach((dir, i) =>
      box.appendChild(this.pathRow(i ? 'Plugins folder (portable)' : 'Plugins folder', dir)));
    (data.lib_dirs || []).slice(0, 1).forEach(dir =>
      box.appendChild(this.pathRow('Libraries folder', dir)));

    const acts = el('div', 'cust-top');
    const reload = el('button', 'btn sm', t('Reload'));
    reload.disabled = this.busy;
    reload.onclick = () => this.act('/api/plugins/custom/reload', { method: 'POST' },
      t('Plugins reloaded'));
    acts.appendChild(reload);

    const pick = el('button', 'btn g sm', t('Add file…'));
    pick.disabled = this.busy;
    pick.onclick = () => $('custFile').click();
    acts.appendChild(pick);

    const example = el('button', 'btn g sm', t('Create an example'));
    example.disabled = this.busy;
    example.onclick = () => this.act('/api/plugins/custom/example', { method: 'POST' },
      t('The example is in your plugins folder'));
    acts.appendChild(example);
    box.appendChild(acts);

    const zone = el('div', 'cust-drop', t('Drop a .py file or a .zip archive here'));
    zone.ondragover = event => { event.preventDefault(); zone.classList.add('on'); };
    zone.ondragleave = () => zone.classList.remove('on');
    zone.ondrop = event => {
      event.preventDefault();
      zone.classList.remove('on');
      const file = (event.dataTransfer.files || [])[0];
      if (file) this.upload(file);
    };
    box.appendChild(zone);

    const items = data.items || [];
    const errors = data.errors || [];
    if (!items.length && !errors.length) {
      box.appendChild(el('div', 'plug-empty',
        t('No custom plugins yet — put a .py file into the folder above')));
    }
    items.forEach(entry => box.appendChild(this.item(entry)));
    errors.forEach(entry => box.appendChild(this.error(entry)));

    /* ---------------------------------------------------- свои библиотеки */
    box.appendChild(el('h4', '', t('Your Python libraries')));
    box.appendChild(el('div', 'hint',
      // Две фразы переводятся по отдельности: склеенной строки в словаре нет,
      // и подсказка целиком оставалась английской.
      t('They are added to the import path, so plugins can use them.') + ' ' +
      t('Installing goes into your own folder: no administrator rights needed.')));
    const form = el('div', 'cust-top');
    const input = el('input');
    input.placeholder = 'requests beautifulsoup4';
    input.spellcheck = false;
    const install = el('button', 'btn sm', t('Install'));
    install.disabled = this.busy;
    const run = () => {
      const value = input.value.trim();
      if (!value) return;
      input.value = '';
      this.act('/api/plugins/libs', { method: 'POST', body: { packages: value.split(/\s+/) } },
        t('Library installed'));
    };
    install.onclick = run;
    input.onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); run(); } };
    form.appendChild(input);
    form.appendChild(install);
    box.appendChild(form);
    const libs = data.libs || [];
    if (!libs.length) box.appendChild(el('div', 'plug-empty', t('The folder is empty')));
    libs.forEach(entry => box.appendChild(this.lib(entry)));
  },

  bind() {
    const file = $('custFile');
    if (file) {
      file.onchange = () => {
        const chosen = (file.files || [])[0];
        file.value = '';
        this.upload(chosen);
      };
    }
  },
};

/* --------------------------------------------------------------------------
   «Запустится ли здесь»: та же проверка, что и в Kryo --doctor.
   Нужна ровно для одного вопроса — почему у одного человека работает, а у
   другого нет. Ответ виден сразу, без чтения журналов.
   ------------------------------------------------------------------------ */
const LocalCheck = {
  data: null,

  async run() {
    const box = $('docBox');
    if (!box) return;
    box.innerHTML = `<div class="plug-empty">${t('Checking…')}</div>`;
    let data;
    try {
      data = await api('/api/doctor');
    } catch (err) {
      box.innerHTML = `<div class="plug-empty">${esc(err.message || t('Error'))}</div>`;
      return;
    }
    this.data = data;
    this.render();
  },

  /* Отдельно от run(): после смены языка отчёт перерисовывается без
     повторной проверки. */
  render() {
    const box = $('docBox');
    const data = this.data;
    if (!box || !data) return;
    box.innerHTML = '';
    box.appendChild(el('div', 'doc-head',
      `<b>${esc(data.app)} ${esc(data.version)}</b> · ${esc(data.platform)} · ` +
      `${t('device')} ${esc(data.device)}`));
    (data.checks || []).forEach(item => {
      const row = el('div', 'doc-row s-' + item.state);
      row.appendChild(el('span', 'doc-name', t(item.name)));
      // Заметка и совет приходят английскими ключами (шаблон + данные):
      // переводим здесь, иначе строка показывалась на языке сервера.
      const note = el('span', 'doc-note',
        esc(item.note_key ? tf(item.note_key, item.note_args) : tParts(item.note)));
      note.setAttribute('data-no-i18n', '');
      row.appendChild(note);
      if (item.fix) {
        const fix = el('small', 'doc-fix',
          esc(item.fix_key ? tf(item.fix_key, item.fix_args) : tParts(item.fix)));
        fix.setAttribute('data-no-i18n', '');
        row.appendChild(fix);
      }
      box.appendChild(row);
    });
    const verdict = { ok: 'Everything is ready on this device',
                      warn: 'It will run, some features stay off',
                      fail: 'Something blocks the start — see the lines above' };
    box.appendChild(el('div', 'doc-sum s-' + data.state, t(verdict[data.state])));
  },

  bind() {
    const button = $('docRun');
    if (button) button.onclick = () => this.run();
  },
};
