/* ytcookies.js — cookies YouTube в настройках.

   Зачем. YouTube периодически отвечает «Sign in to confirm you're not a
   bot», и тогда ни один трек не стартует: проверка срабатывает на адрес, а
   не на приложение. Cookies залогиненной сессии снимают её — yt-dlp
   спрашивает YouTube от лица обычного слушателя.

   Здесь два пути, оба ведут в kryonyx/ytcookies.py:
     * выбрать браузер — приложение само читает cookies из его профиля;
     * вставить cookies текстом: файл Netscape, экспорт Cookie-Editor (JSON)
       или просто строка заголовка «Cookie: …». Формат разбирает сервер. */
'use strict';

const YTCookies = {
  state: null,
  busy: false,

  async load(quiet) {
    try {
      this.state = await api('/api/youtube/cookies', { timeout: 8000 });
    } catch {
      this.state = null;
      if (!quiet) toast(t('Server is not responding'));
    }
    this.paint();
  },

  /* Короткая строка в настройках и подробности в окне. */
  paint() {
    const st = this.state || {};
    // Never auto-start video after a cookie change. Explicit user retry/return only.
    if(typeof Clips!=='undefined')Clips.onCookiesChanged57?.();
    const line = $('ytcLine');
    if (line) {
      if (st.present) {
        line.textContent = `${t('Cookies are set')} · ${st.count} · ` +
          (st.signed_in ? t('signed in') : t('no sign-in cookie'));
      } else if (st.browser) {
        line.textContent = t('Cookies are taken from the browser') + ': ' + st.browser;
      } else {
        line.textContent = t('Helps when YouTube asks to confirm you are not a bot');
      }
    }
    const box = $('ytcState');
    if (box) {
      const parts = [];
      if (st.present) {
        parts.push(t('Cookies are set'));
        parts.push(`${st.count} ${t('cookies')}`);
        parts.push(st.signed_in ? t('a signed-in session')
                                : t('no sign-in cookie — the wall may stay'));
        if (st.updated_at) {
          parts.push(t('Updated') + ': ' + new Date(st.updated_at * 1000).toLocaleString());
        }
      } else {
        parts.push(t('No cookies yet'));
      }
      if (st.browser) parts.push(t('Browser') + ': ' + st.browser);
      box.textContent = parts.join(' · ');
    }
    const select = $('ytcBrowser');
    if (select && !select.dataset.filled) {
      select.dataset.filled = '1';
      const none = el('option', '', t('Do not use a browser'));
      none.value = '';
      select.appendChild(none);
      (st.browsers || []).forEach(name => {
        const opt = el('option', '', name);
        opt.value = name;
        select.appendChild(opt);
      });
    }
    if (select) select.value = st.browser || '';
    const forget = $('ytcForget');
    if (forget) forget.style.display = st.present ? '' : 'none';
  },

  open() {
    openModal('mYtCookies');
    this.paintExt();
    this.load(true);
  },

  async save(button) {
    const raw = ($('ytcBox') || {}).value || '';
    if (!raw.trim()) { toast(t('Paste the cookies first')); return; }
    const verdict = await this.checkText();
    if (verdict && !verdict.ok) { toast(t('These cookies will not help — see the check below'), 6000); return; }
    await this.run(button, async () => {
      this.state = await api('/api/youtube/cookies',
        { method: 'PUT', body: { cookies: raw } });
      $('ytcBox').value = '';
      this.paint();
      dropCache('/api/search');
      toast(this.state.signed_in
        ? t('Cookies saved — YouTube now sees a signed-in session')
        : t('Cookies saved, but there is no sign-in cookie in them'));
      $('ytcCheck').innerHTML = '';
    });
    if (this.state && this.state.signed_in) this.test($('ytcTest'));
  },

  async forget(button) {
    await this.run(button, async () => {
      this.state = await api('/api/youtube/cookies', { method: 'DELETE' });
      this.paint();
      toast(t('Cookies removed'));
    });
  },

  async pickBrowser(name) {
    try {
      this.state = await api('/api/youtube/cookies/browser',
        { method: 'POST', body: { browser: name } });
      this.paint();
      toast(name ? t('Cookies will be taken from') + ' ' + name : t('Browser cookies are off'));
    } catch (err) {
      toast(err.message || t('Error'));
    }
  },

  /* Проверка боем: сервер просит у YouTube настоящую ссылку на аудио. */
  async test(button) {
    await this.run(button, async () => {
      toast(t('Asking YouTube for a track…'), 5000);
      await api('/api/youtube/cookies/test', { method: 'POST', timeout: 90000 });
      toast(t('YouTube answered — playback should work'), 5000);
    });
  },

  async run(button, job) {
    if (this.busy) return;
    this.busy = true;
    const label = button ? button.textContent : '';
    if (button) { button.disabled = true; button.textContent = '…'; }
    try {
      await job();
    } catch (err) {
      toast(err.message || t('Error'), 7000);
    } finally {
      this.busy = false;
      if (button) { button.disabled = false; button.textContent = label; }
    }
  },

  /* Расширения для выгрузки cookies: ссылки по браузерам. */
  EXT: {
    chrome: [['Get cookies.txt LOCALLY', 'https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc'],
             ['Cookie-Editor', 'https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm']],
    firefox: [['cookies.txt', 'https://addons.mozilla.org/firefox/addon/cookies-txt/'],
              ['Cookie-Editor', 'https://addons.mozilla.org/firefox/addon/cookie-editor/']],
  },
  NOTES: {
    chrome: '',
    edge: 'Edge installs extensions from the Chrome Web Store too — allow it when Edge asks.',
    brave: 'Brave installs extensions from the Chrome Web Store.',
    opera: 'Opera installs Chrome Web Store extensions after you add “Install Chrome Extensions” from the Opera add-ons page.',
    vivaldi: 'Vivaldi installs extensions from the Chrome Web Store.',
    firefox: '',
    safari: 'Safari has no suitable extension: export from Chrome or Firefox, or copy the Cookie header from F12 → Network.',
  },
  family(name) { return name === 'firefox' ? 'firefox' : name === 'safari' ? '' : 'chrome'; },

  guessBrowser() {
    const ua = navigator.userAgent || '';
    return /Firefox\//.test(ua) ? 'firefox' : /Edg\//.test(ua) ? 'edge'
      : /OPR\//.test(ua) ? 'opera' : 'chrome';
  },

  paintExt() {
    const names = [['chrome', 'Chrome'], ['edge', 'Edge'], ['firefox', 'Firefox'], ['brave', 'Brave'],
                   ['opera', 'Opera'], ['vivaldi', 'Vivaldi'], ['safari', 'Safari']];
    const pick = this.extBrowser || (this.extBrowser = this.guessBrowser());
    const tabs = $('ytcBrowsers');
    if (tabs) {
      tabs.innerHTML = '';
      names.forEach(([id, label]) => {
        const chip = el('button', 'chip' + (pick === id ? ' on' : ''), label);
        chip.onclick = () => { this.extBrowser = id; this.paintExt(); };
        tabs.appendChild(chip);
      });
    }
    const box = $('ytcExt');
    if (box) {
      box.innerHTML = '';
      (this.EXT[this.family(pick)] || []).forEach(([label, url]) => {
        const b = el('button', 'btn', '↗ ' + label);
        b.onclick = () => this.openUrl(url);
        box.appendChild(b);
      });
      const yt = el('button', 'btn g', t('Open YouTube'));
      yt.onclick = () => this.openUrl('https://www.youtube.com/');
      box.appendChild(yt);
    }
    const note = $('ytcExtNote');
    if (note) { note.textContent = this.NOTES[pick] ? t(this.NOTES[pick]) : ''; note.style.display = this.NOTES[pick] ? '' : 'none'; }
  },

  async openUrl(url) {
    try { await api('/api/open-url', { method: 'POST', body: { url } }); }
    catch { window.open(url, '_blank', 'noopener'); }
  },

  /* Проверка вставленного текста до сохранения: те ли это куки. */
  async checkText() {
    const raw = (($('ytcBox') || {}).value || '').trim();
    const box = $('ytcCheck');
    if (!box) return null;
    if (!raw) { box.innerHTML = ''; this.verdict = null; return null; }
    let res;
    try { res = await api('/api/youtube/cookies/check', { method: 'POST', body: { cookies: raw } }); }
    catch { return null; }
    this.verdict = res;
    const rows = [];
    const add = (cls, text) => rows.push(`<div class="${cls}">${cls === 'ok' ? '✓' : cls === 'bad' ? '✗' : '!'} ${esc(text)}</div>`);
    const p = new Set(res.problems);
    if (p.has('empty')) add('bad', t('No cookies found in this text'));
    else if (p.has('wrong_site')) {
      add('bad', t('These are not YouTube cookies') + (res.foreign.length ? ': ' + res.foreign.join(', ') : '') +
        '. ' + t('Export them while a youtube.com tab is open'));
    } else {
      add('ok', `${t('Cookies of youtube.com found')}: ${res.youtube}`);
      if (p.has('expired')) add('bad', t('The sign-in cookies have expired — sign in to YouTube again and export anew'));
      else if (p.has('not_signed_in')) add('bad', t('No sign-in cookies — you are probably signed out of YouTube, or this is the wrong site'));
      else add('ok', t('Sign-in cookies found') + ': ' + res.auth.join(', '));
      if (p.has('no_login_info')) add('warn', t('There is no LOGIN_INFO cookie — export again with a youtube.com tab open'));
      if (p.has('few')) add('warn', t('Very few cookies — this looks like a partial export'));
      if (p.has('foreign')) add('warn', t('Cookies of other sites are ignored and will not be saved') + ': ' + res.foreign.join(', '));
    }
    box.innerHTML = rows.join('');
    return res;
  },

  bind() {
    const open = $('bYtCookies');
    if (open) open.onclick = () => this.open();
    const box = $('ytcBox');
    if (box) box.oninput = debounce(() => this.checkText(), 350);
    const save = $('ytcSave');
    if (save) save.onclick = () => this.save(save);
    const forget = $('ytcForget');
    if (forget) forget.onclick = () => this.forget(forget);
    const test = $('ytcTest');
    if (test) test.onclick = () => this.test(test);
    const select = $('ytcBrowser');
    if (select) select.onchange = () => this.pickBrowser(select.value);
    this.load(true);
  },
};
