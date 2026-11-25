/* hints.js — история поиска и подсказки под строкой поиска.

   Как это работает по шагам:
     * щелчок или фокус по строке — показываем историю запросов;
     * печать — к истории добавляются подсказки сервиса и найденные авторы;
     * выбор строки — запрос уходит в поиск, а список сразу закрывается и
       больше сам не всплывает: он ждёт следующего щелчка или новой печати;
     * Esc, щелчок мимо и уход фокуса тоже закрывают список.

   Крестик рядом с запросом истории убирает его насовсем — чужие опечатки
   в своей истории никому не нужны. */
'use strict';

const Hints = {
  items: [],        // то, что сейчас показано: {kind, text, author}
  at: -1,           // выделенная строка для стрелок клавиатуры
  open: false,
  armed: true,      // можно ли всплывать: после выбора подсказки — нельзя
  token: 0,

  box() { return $('qPop'); },
  input() { return $('q'); },

  /* ------------------------------------------------------------- данные */
  async fetch(query) {
    const token = ++this.token;
    query = (query || '').trim();
    let data = {};
    try {
      data = query.length >= 2
        ? await api('/api/suggest?q=' + encodeURIComponent(query) + '&authors=1',
                    { timeout: 8000 })
        : await api('/api/searches', { timeout: 8000 });
    } catch {
      data = {};
    }
    if (token !== this.token) return null;

    const items = [];
    const seen = new Set();
    const push = (kind, text, author) => {
      const key = kind + ':' + String(text || '').toLowerCase();
      if (!text || seen.has(key)) return;
      seen.add(key);
      items.push({ kind, text, author });
    };
    // Без запроса ручка /api/searches отдаёт историю в items, а /api/suggest —
    // историю и подсказки вперемешку в queries, причём история идёт первой.
    const history = data.items || (data.recent ? data.queries : []) || [];
    history.forEach(text => push('history', text));
    if (query.length >= 2) {
      (data.queries || []).forEach(text => push('hint', text));
      (data.authors || []).forEach(author => push('author', author.name, author));
    }
    return items.slice(0, 12);
  },

  /* ------------------------------------------------------------- показ */
  async show(query) {
    if (!this.armed || !this.box()) return;
    const items = await this.fetch(query);
    if (items === null) return;
    if (!items.length) { this.hide(); return; }
    this.items = items;
    this.at = -1;
    this.render();
    this.box().hidden = false;
    this.box().classList.add('on');
    this.open = true;
  },

  hide() {
    const box = this.box();
    if (!box) return;
    box.classList.remove('on');
    box.hidden = true;
    this.open = false;
    this.at = -1;
    this.token++;
  },

  render() {
    const box = this.box();
    box.innerHTML = '';
    const head = this.items.some(item => item.kind === 'history')
      && !this.items.some(item => item.kind !== 'history');
    if (head) {
      const title = el('div', 'q-pop-h');
      title.innerHTML = `<span>${esc(t('Recent searches'))}</span>`;
      const clear = el('button', 'q-pop-clear', esc(t('Clear')));
      clear.onmousedown = event => event.preventDefault();
      clear.onclick = async () => {
        try { await api('/api/searches', { method: 'DELETE' }); } catch {}
        this.hide();
      };
      title.appendChild(clear);
      box.appendChild(title);
    }
    this.items.forEach((item, index) => box.appendChild(this.row(item, index)));
  },

  row(item, index) {
    const row = el('div', 'q-row' + (index === this.at ? ' on' : ''));
    const mark = item.kind === 'history' ? 'clock'
      : item.kind === 'author' ? 'user' : 'search';
    row.innerHTML = `${icon(mark, 'ic s')}<span class="q-t clip">${esc(item.text)}</span>` +
      (item.kind === 'author' ? `<span class="q-k">${esc(t('Artist'))}</span>` : '');
    if (item.kind === 'history') {
      const drop = el('button', 'q-drop', icon('close', 'ic xs'));
      drop.title = t('Remove from history');
      drop.onmousedown = event => event.preventDefault();
      drop.onclick = async event => {
        event.stopPropagation();
        try {
          await api('/api/searches?q=' + encodeURIComponent(item.text),
                    { method: 'DELETE' });
        } catch {}
        row.remove();
        this.items = this.items.filter(other => other !== item);
        if (!this.items.length) this.hide();
      };
      row.appendChild(drop);
    }
    // mousedown вместо click: щелчок по строке не должен сначала забирать
    // фокус у поля и закрывать список через blur.
    row.onmousedown = event => {
      if (event.target.closest('.q-drop')) return;
      event.preventDefault();
      this.pick(item);
    };
    return row;
  },

  /* ------------------------------------------------------------- выбор */
  pick(item) {
    // Выбрали — список исчезает и сам больше не появляется: следующий показ
    // только по новому щелчку по строке или по новой печати.
    this.armed = false;
    this.hide();
    if (item.kind === 'author' && item.author) {
      App.openAuthor(item.author.name, item.author.url, item.author.source);
      return;
    }
    const input = this.input();
    if (input) {
      input.value = item.text;
      $('qClear').style.display = '';
      input.blur();
    }
    App.search(item.text);
  },

  move(step) {
    if (!this.open || !this.items.length) return;
    this.at = (this.at + step + this.items.length + 1) % (this.items.length + 1) - 1;
    const rows = [...this.box().querySelectorAll('.q-row')];
    rows.forEach((row, index) => row.classList.toggle('on', index === this.at));
    if (this.at >= 0 && rows[this.at]) rows[this.at].scrollIntoView({ block: 'nearest' });
  },

  current() {
    return this.at >= 0 ? this.items[this.at] : null;
  },

  /* --------------------------------------------------------------- связь */
  bind() {
    const input = this.input();
    if (!input || !this.box()) return;

    let composing = false;
    input.addEventListener('compositionstart', () => {composing = true;});
    input.addEventListener('compositionend', () => {composing = false;});
    const ask = debounce(() => {if(!composing)this.show(input.value);}, 180);
    input.addEventListener('input', () => {
      // Новая печать снова разрешает подсказки, даже если их только что
      // закрыли выбором: человек начал новый запрос.
      this.armed = true;
      ask();
    });
    input.addEventListener('focus', () => { this.armed = true; this.show(input.value); });
    input.addEventListener('click', () => { this.armed = true; this.show(input.value); });
    input.addEventListener('blur', () => setTimeout(() => this.hide(), 120));
    input.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown') { event.preventDefault(); this.move(1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); this.move(-1); }
      else if (event.key === 'Escape' && this.open) { event.stopPropagation(); this.hide(); }
      else if (event.key === 'Enter') {
        const chosen = this.current();
        if (chosen) { event.preventDefault(); event.stopImmediatePropagation(); this.pick(chosen); }
        else { this.armed = false; this.hide(); }
      }
    }, true);

    document.addEventListener('click', event => {
      if (!event.target.closest('#searchWrap')) this.hide();
    });
  },
};
