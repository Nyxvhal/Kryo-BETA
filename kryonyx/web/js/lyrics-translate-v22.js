/* Opt-in lyric translation state (kept separate from the karaoke document). */
'use strict';

const LyricsTranslate = {
  token: 0,
  controller: null,
  requestId: null,
  cancelWait: Promise.resolve(),
  result: null,
  pending: false,
  timeoutMs: 90000,
  initialized: false,
  cache: new Map(),

  tr(en, ru) {
    const translated = t(en);
    return LANG === 'ru' && translated === en ? ru : translated;
  },

  signature() {
    return JSON.stringify([Karaoke.trackId, Karaoke.fetchToken, Karaoke.lyricSignature, Karaoke.document, Karaoke.lines]);
  },

  cacheKey(signature, source, target) {
    return [Karaoke.trackId || '', signature || '', source || 'auto', target || 'en'].join('|');
  },

  syncButton() {
    const btn = $('sceneTranslate87');
    if (!btn) return;
    const panelOpen = $('translationPanel33') && !$('translationPanel33').hidden;
    const active = !!panelOpen || (S.lyricTranslationVisible !== false && !!this.result && this.result.state !== 'error' && this.result.signature === this.renderSignature);
    btn.classList.toggle('on', active);
    btn.setAttribute('aria-pressed', String(active));
  },

  value(line, index) {
    if (S.lyricTranslationVisible === false) return '';
    const r = this.result;
    if (
      r &&
      r.signature === this.renderSignature &&
      r.target === S.lyricTranslationTarget &&
      r.rows[index]?.original === String(line.text || '') &&
      r.rows[index].status === 'ok'
    ) {
      return r.rows[index].translation;
    }
    return line.translation ? String(line.translation) : '';
  },

  repaint() {
    const current = this.signature();
    if (this.snapshotSignature && current !== this.snapshotSignature && this.pending) {
      this.token++;
      this.cancelPending();
      this.busy(false);
      if ($('lt22Status')) {
        $('lt22Status').textContent = this.tr('Lyrics changed. Translate again.', 'Текст изменился. Повторите перевод.');
      }
    }
    this.renderSignature = current;

    // Restore cached translation automatically when returning to a previously translated track/mode.
    if (!this.result && Karaoke.lines?.length) {
      const target = S.lyricTranslationTarget || 'en';
      const source = $('lt22Source')?.value || S.lyricTranslationSource || 'auto';
      const cached = this.cache.get(this.cacheKey(current, source, target));
      if (cached) this.result = cached;
    }

    let changed = false;
    document.querySelectorAll('#lyrics .lyr-l').forEach(node => {
      const i = Number(node.dataset.i);
      const line = Karaoke.lines[i];
      let text = node.querySelector('.lyric-translated22');
      const value = line ? this.value(line, i) : '';
      if (!value) {
        if (text) {
          text.remove();
          changed = true;
        }
        return;
      }
      if (!text) {
        text = el('div', 'karaoke-translation lyric-translated22');
        text.dataset.noI18n = '';
        node.append(text);
        changed = true;
      }
      if (text.textContent !== value) {
        text.textContent = value;
        changed = true;
      }
    });

    this.scene();
    this.syncButton();
    if (changed && Karaoke.synced && Karaoke.follow && Karaoke.active >= 0) {
      Karaoke.center(true);
    }
  },

  scene() {
    const stage = Disc.on ? $('discStage') : null;
    let node = $('discTranslation22');
    if (stage && !node) {
      node = el('div', 'disc-translation22');
      node.id = 'discTranslation22';
      node.dataset.noI18n = '';
      stage.querySelector('.disc-text')?.append(node);
    }
    if (node) {
      if (Disc.on && !Karaoke.synced) {
        const entries = Karaoke.lines.map((line, i) => ({ line, value: this.value(line, i) })).filter(x => x.value);
        const key = JSON.stringify(entries.map(x => [x.line.text, x.value]));
        if (node.dataset.contentKey !== key) {
          const fragment = document.createDocumentFragment();
          for (const item of entries) {
            const row = el('div', 'viz-lyric-row22');
            const original = el('div', 'viz-original22');
            const translation = el('div', 'viz-translated22');
            original.textContent = String(item.line.text || '');
            translation.textContent = item.value;
            row.append(original, translation);
            fragment.append(row);
          }
          node.replaceChildren(fragment);
          node.dataset.contentKey = key;
        }
        node.hidden = !entries.length;
        node.classList.add('unsynced22');
        node.tabIndex = 0;
      } else {
        const i = Disc.line;
        const line = Karaoke.lines[i];
        const value = Disc.on && line && !Disc.words?.classList.contains('gone') ? this.value(line, i) : '';
        if (node.textContent !== value) node.textContent = value;
        node.hidden = !value;
        node.classList.remove('unsynced22');
        node.removeAttribute('tabindex');
        delete node.dataset.contentKey;
      }
    }
  },

  cancelPending() {
    const id = this.requestId;
    this.requestId = null;
    if (id) {
      this.cancelWait = fetch('/api/lyrics/translate/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: id }),
        keepalive: true,
      }).catch(() => {});
    }
    this.controller?.abort();
  },

  changed() {
    this.token++;
    this.cancelPending();
    this.pending = false;
    this.result = null;
    this.snapshotSignature = null;
    this.busy(false);
    if ($('lt22Retry')) $('lt22Retry').hidden = true;
    if ($('lt22Status')) $('lt22Status').textContent = '';
    this.repaint();
  },

  busy(on) {
    this.pending = on;
    if (!$('lt22Run')) return;
    $('lt22Run').disabled = on;
    $('lt22Retry').disabled = on;
    $('lt22Cancel').hidden = !on;
    $('lyricsTranslate22').setAttribute('aria-busy', String(on));
  },

  mount() {
    if ($('lyricsTranslate22')) return;
    const tr = this.tr.bind(this);
    const details = el('details', 'lyrics-translate22');
    details.id = 'lyricsTranslate22';
    details.open = true;

    const summary = el('summary', '', tr('Lyrics translation', 'Перевод текста'));
    summary.id = 'lt22Summary';

    const body = el('div', 'lt22-body');
    const label = el('label', 'lt22-target');
    label.append(el('span', '', tr('Translate into', 'Язык перевода')));

    const select = el('select');
    select.id = 'lt22Target';
    select.setAttribute('aria-label', tr('Translation language', 'Язык перевода'));
    const langs = [
      ['en', 'English'],
      ['ru', 'Русский'],
      ['uk', 'Українська'],
      ['de', 'Deutsch'],
      ['fr', 'Français'],
      ['es', 'Español'],
      ['it', 'Italiano'],
      ['pt', 'Português'],
      ['tr', 'Türkçe'],
      ['pl', 'Polski'],
      ['ja', '日本語'],
      ['ko', '한국어'],
      ['zh-CN', '中文'],
    ];
    for (const [code, name] of langs) {
      const o = el('option', '', name);
      o.value = code;
      o.dataset.noI18n = '';
      select.append(o);
    }
    select.value = S.lyricTranslationTarget || (LANG === 'zh' ? 'zh-CN' : LANG);
    if (!select.value) select.value = 'en';
    S.lyricTranslationTarget = select.value;
    select.onchange = () => {
      S.lyricTranslationTarget = select.value;
      this.changed();
      saveSettings(true);
    };
    label.append(select);

    const sourceLabel = el('label', 'lt22-target');
    sourceLabel.append(el('span', '', tr('Original language', 'Язык оригинала')));
    const source = select.cloneNode(true);
    source.id = 'lt22Source';
    source.setAttribute('aria-label', tr('Original language', 'Язык оригинала'));
    const auto = el('option', '', tr('Detect automatically', 'Определить автоматически'));
    auto.value = 'auto';
    source.prepend(auto);
    source.value = S.lyricTranslationSource || 'auto';
    source.onchange = () => {
      S.lyricTranslationSource = source.value;
      this.changed();
      saveSettings(true);
    };
    sourceLabel.append(source);

    const hint = el(
      'p',
      'lt22-status',
      tr(
        'Translates karaoke lyrics while keeping original lines and timing intact.',
        'Переводит текст караоке с сохранением оригинальных строк и таймингов.'
      )
    );

    const actions = el('div', 'lt22-actions');
    const run = el('button', 'btn', tr('Translate lyrics', 'Перевести текст'));
    run.id = 'lt22Run';
    run.type = 'button';
    run.onclick = () => this.run(false);

    const retry = el('button', 'btn g', tr('Retry failed lines', 'Повторить ошибки'));
    retry.id = 'lt22Retry';
    retry.type = 'button';
    retry.hidden = true;
    retry.onclick = () => this.run(true);

    const cancel = el('button', 'btn g', tr('Cancel', 'Отмена'));
    cancel.id = 'lt22Cancel';
    cancel.type = 'button';
    cancel.hidden = true;
    cancel.onclick = () => {
      this.token++;
      this.cancelPending();
      this.busy(false);
      $('lt22Status').textContent = tr('Translation cancelled.', 'Перевод отменён.');
    };

    const visible = el('label', 'lt22-visible');
    const toggle = el('input');
    toggle.type = 'checkbox';
    toggle.id = 'lt22Visible';
    toggle.checked = S.lyricTranslationVisible !== false;
    toggle.onchange = () => {
      S.lyricTranslationVisible = toggle.checked;
      saveSettings(true);
      this.repaint();
    };
    visible.append(toggle, el('span', '', tr('Show translation', 'Показывать перевод')));

    const status = el('p', 'lt22-status');
    status.id = 'lt22Status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');

    actions.append(run, retry, cancel, visible);
    body.append(sourceLabel, label, hint, actions, status);
    details.append(summary, body);
    $('nowTop').after(details);
  },

  async run(retry = false) {
    const tr = this.tr.bind(this);
    const status = $('lt22Status');
    const texts = Karaoke.lines.map(l => String(l.text || ''));
    const signature = this.signature();
    const target = S.lyricTranslationTarget;

    if (!texts.some(s => s.trim())) {
      status.textContent = tr('Load lyrics before translating.', 'Сначала загрузи текст песни.');
      return;
    }
    const source = $('lt22Source').value;
    if (source === target) {
      status.textContent = tr('Choose different languages.', 'Выберите разные языки.');
      return;
    }
    const normalized = texts.map(s => s.replace(/[\r\n]+/g, ' '));
    if (
      texts.length > 240 ||
      normalized.some(s => s.length > 2000) ||
      normalized.reduce((n, s) => n + s.length, 0) > 24000
    ) {
      status.textContent = tr('Lyrics exceed the translation limits.', 'Текст превышает ограничения перевода.');
      return;
    }

    this.cancelPending();
    const controller = new AbortController();
    this.controller = controller;
    const token = ++this.token;
    this.snapshotSignature = signature;
    this.busy(true);

    const prior = this.result;
    const old =
      prior &&
      prior.trackId === Karaoke.trackId &&
      prior.target === target &&
      prior.source === source &&
      (source !== 'auto' || prior.signature === signature) &&
      ((retry && prior.signature === signature) || prior.signature !== signature)
        ? prior
        : null;

    const rows = texts.map((original, index) =>
      old?.rows[index]?.status === 'ok' && old.rows[index].original === original
        ? { ...old.rows[index] }
        : { index, original, translation: '', status: original.trim() ? 'pending' : 'empty' }
    );

    let timedOut = false;
    let fingerprint = null;
    let detectedSource = null;
    const timer = setTimeout(() => {
      timedOut = true;
      this.cancelPending();
    }, this.timeoutMs);

    const valid = () =>
      token === this.token &&
      signature === this.signature() &&
      target === S.lyricTranslationTarget &&
      source === $('lt22Source').value;

    try {
      await this.cancelWait;
      if (!valid()) return;

      const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(texts)));
      fingerprint = Array.from(new Uint8Array(bytes), n => n.toString(16).padStart(2, '0')).join('');

      const indices = rows.filter(r => r.status === 'pending').map(r => r.index);
      if (indices.length) {
        status.textContent = tr('Translating…', 'Переводим…');
        const requestId = Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('');
        this.requestId = requestId;
        const response = await fetch('/api/lyrics/translate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            lines: indices.map(i => normalized[i]),
            target,
            source,
            context: normalized,
            request_id: requestId,
          }),
          signal: controller.signal,
        });
        if (this.requestId === requestId) this.requestId = null;

        if (!response.ok) {
          let detail = {};
          try { detail = await response.json(); } catch {}
          throw Object.assign(Error(detail.error || 'Translation request failed'), {
            code: detail.error_code || 'provider',
          });
        }

        let data;
        try {
          data = await response.json();
        } catch {
          throw Object.assign(Error('Invalid server response'), { code: 'malformed' });
        }
        if (!valid()) return;
        if (data.error) throw Object.assign(Error(data.error || 'Translation request failed'), { code: 'provider' });

        detectedSource = data.source;
        if (
          data.schema_version !== 1 ||
          data.target !== target ||
          !detectedSource ||
          !['kryo-translate-v2', 'argos-offline-v1'].includes(data.provider) ||
          !Array.isArray(data.results) ||
          data.results.length !== indices.length
        ) {
          throw Error('Invalid translation response');
        }

        for (let j = 0; j < indices.length; j++) {
          const x = data.results[j];
          const i = indices[j];
          if (
            !x ||
            x.index !== j ||
            x.original !== normalized[i] ||
            !['ok', 'error'].includes(x.status) ||
            typeof x.translation !== 'string' ||
            (x.status === 'ok' && !x.translation.trim()) ||
            (x.status === 'error' && x.translation !== '')
          ) {
            throw Error('Translation lost line alignment');
          }
          rows[i] = {
            index: i,
            original: texts[i],
            translation: x.translation,
            status: x.status,
            error_code: x.status === 'error' ? (x.error_code || 'provider') : undefined,
          };
        }
      }

      if (!valid()) return;
      const payload = {
        schema_version: 1,
        fingerprint,
        revision: signature,
        signature,
        target,
        trackId: Karaoke.trackId,
        provider: 'kryo-translate-v2',
        source,
        detectedSource,
        created_at: new Date().toISOString(),
        state: rows.some(r => r.status === 'error')
          ? (rows.some(r => r.status === 'ok') ? 'partial' : 'error')
          : 'complete',
        rows,
        lines: rows.map(r => r.translation),
        texts,
      };
      this.result = payload;
      if (payload.state === 'complete') {
        this.cache.set(this.cacheKey(signature, source, target), payload);
      }

      S.lyricTranslationVisible = true;
      $('lt22Visible').checked = true;
      saveSettings(true);
      this.repaint();
      $('lt22Retry').hidden = payload.state === 'complete';

      const failure = rows.find(r => r.status === 'error')?.error_code;
      const reasons = {
        rate_limit: tr('Service rate limit.', 'Превышен лимит сервиса.'),
        timeout: tr('Service timed out.', 'Сервис не ответил вовремя.'),
        network: tr('Network error.', 'Ошибка сети.'),
        malformed: tr('Invalid service response.', 'Некорректный ответ сервиса.'),
        http: tr('Service unavailable.', 'Сервис недоступен.'),
        provider: tr('Translation failed.', 'Перевести не удалось.'),
      };
      status.textContent =
        payload.state === 'error'
          ? (reasons[failure] || reasons.provider) + ' ' + tr('Retry failed lines.', 'Повторите попытку.')
          : payload.state === 'partial'
            ? tr('Some lines failed. Retry failed lines.', 'Некоторые строки не переведены. Повторите ошибки.')
            : tr('Translated · original text and timing preserved.', 'Перевод готов · оригинал и тайминги сохранены.') +
              (source === 'auto' && detectedSource ? ' ' + tr('Detected: ', 'Определён язык: ') + detectedSource : '');
    } catch (e) {
      if (token !== this.token) return;
      if (valid() && fingerprint && (timedOut || e.name !== 'AbortError')) {
        const code = timedOut ? 'timeout' : e.code || (/invalid|alignment/i.test(e.message || '') ? 'malformed' : 'network');
        for (const row of rows) {
          if (row.status === 'pending') {
            row.status = 'error';
            row.error_code = code;
          }
        }
        this.result = {
          schema_version: 1,
          fingerprint,
          revision: signature,
          signature,
          target,
          trackId: Karaoke.trackId,
          provider: 'kryo-translate-v2',
          source,
          detectedSource,
          created_at: new Date().toISOString(),
          state: rows.some(r => r.status === 'ok') ? 'partial' : 'error',
          rows,
          lines: rows.map(r => r.translation),
          texts,
        };
        this.repaint();
        $('lt22Retry').hidden = false;
      }
      if (timedOut || e.name !== 'AbortError') {
        const code = timedOut ? 'timeout' : e.code || (/invalid|alignment/i.test(e.message || '') ? 'malformed' : 'network');
        const reasons = {
          rate_limit: tr('Service rate limit.', 'Превышен лимит сервиса.'),
          timeout: tr('Service timed out.', 'Сервис не ответил вовремя.'),
          network: tr('Network error.', 'Ошибка сети.'),
          malformed: tr('Invalid service response.', 'Некорректный ответ сервиса.'),
          http: tr('Service unavailable.', 'Сервис недоступен.'),
          provider: tr('Translation failed.', 'Перевести не удалось.'),
        };
        status.textContent =
          code === 'language'
            ? tr('Could not detect the source language. Choose languages manually.', 'Не удалось определить язык. Выберите языки вручную.')
            : code === 'busy'
              ? tr('Translation is still finishing. Retry in a moment.', 'Предыдущий перевод ещё завершается. Повторите через пару секунд.')
              : (reasons[code] || reasons.provider) + ' ' + tr('Retry failed lines.', 'Повторите ошибки.');
      }
    } finally {
      clearTimeout(timer);
      if (token === this.token) {
        if (signature !== this.signature() || target !== S.lyricTranslationTarget) {
          status.textContent = tr('Lyrics changed. Translate again.', 'Текст изменился. Повторите перевод.');
        }
        this.busy(false);
        this.syncButton();
      }
    }
  },

  error(message) {
    const tr = this.tr.bind(this);
    return tr('Could not translate lyrics. Check the connection and retry.', 'Не удалось перевести текст. Проверь подключение и повтори попытку.') + (LANG === 'en' ? ' ' + message : '');
  },

  init() {
    if (this.initialized) return;
    this.initialized = true;
    this.mount();
    const render = Karaoke.render.bind(Karaoke);
    Karaoke.render = () => {
      render();
      this.repaint();
      if (typeof Interface45 !== 'undefined' && Interface45.labels) Interface45.labels();
    };
    const track = Karaoke.onTrack.bind(Karaoke);
    Karaoke.onTrack = async (...args) => {
      this.changed();
      const node = $('discTranslation22');
      if (node) {
        node.textContent = '';
        node.hidden = true;
      }
      await track(...args);
      this.repaint();
      if (typeof Interface45 !== 'undefined' && Interface45.labels) Interface45.labels();
    };
    const time = Karaoke.onTime.bind(Karaoke);
    Karaoke.onTime = (...args) => {
      time(...args);
      if (Disc.on) this.scene();
    };
    const apply = App.applyKaraoke.bind(App);
    App.applyKaraoke = (...args) => {
      const result = apply(...args);
      this.scene();
      return result;
    };
  },
};
