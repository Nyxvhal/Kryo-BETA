/* app.js — навигация, поиск с подсказками, настройки, горячие клавиши. */
'use strict';

const App = {
  searchToken: 0,
  addTrack: null,

  /* Шаг загрузки, который не может уронить остальные.

     Раньше boot() был одной длинной цепочкой: исключение в любом модуле
     обрывало её молча, и окно оставалось пустым — снаружи это выглядит как
     «приложение не отвечает». Теперь каждый шаг отделён: сломанный модуль
     попадает в журнал, а плеер продолжает собираться. */
  step(name, fn) {
    try { fn(); } catch (err) {
      (this.bootErrors || (this.bootErrors = [])).push(name);
      console.error('[boot] ' + name, err);
    }
  },

  async boot() {
    this.step('settings', loadLocal);
    // Настройки и тема приезжают из базы на устройстве, а не из хранилища
    // WebView: их нельзя потерять при обновлении или чистке кэша.
    try { await pullSettings(); } catch (err) { console.error('[boot] pullSettings', err); }
    this.step('lang', () => setLang(detectLang(), false));
    this.step('safe-mode', applySafeMode);
    this.step('theme', applyTheme);
    this.step('player', () => Player.init());
    this.step('clips', () => Clips.init());
    this.step('karaoke', () => Karaoke.init());
    // Restore per-track preferences before a restored/selected track asks for lyrics.
    const karaokeState = Promise.all([Karaoke.loadOffsets(), Karaoke.loadPicks()]);
    this.step('karaoke-tools', () => KaraokeTools.init());
    this.step('atmo', () => Atmo.init());
    this.step('karaoke-settings', () => this.applyKaraoke());
    this.step('bind', () => this.bind());
    this.step('settings-ui', () => this.buildSettings());
    this.step('libraries', () => this.buildLibraries());
    this.step('plugins', () => Plugins.bind());
    this.step('custom', () => { CustomPlugins.bind(); LocalCheck.bind(); });
    this.step('streams', () => Streams.bind());
    this.step('convert', () => Convert.bind());
    this.step('themes', () => Themes.bind());
    this.step('tune', () => { Tune.bind(); Tune.build(); });
    this.step('settings-search', () => this.bindSettingsSearch());
    // Рисованная тема и внешний вид: свои панели настроек.
    this.step('sketch', () => { Sketch.bind(); Sketch.build(); });
    this.step('frame', () => Frame.applySettings());
    this.step('wall', () => { Wall.bind(); Wall.build(); });
    this.step('look', () => { Look.bind(); Look.build(); });
    this.step('kcustom', () => { KCustom.bind(); KCustom.build(); KCustom.apply(); });
    this.step('vmedia', () => { VMedia.bind(); VMedia.build(); VMedia.applyBg(); });
    this.step('finder', () => Finder.bind());
    this.step('avatars', () => Avatars.bind());
    this.step('ytcookies', () => YTCookies.bind());
    this.step('mini', () => MiniPlayer.init());
    this.step('netproxy', () => NetProxy.bind());
    this.step('integrations', () => Integrations.bind());
    this.step('logs', () => Logs.bind());
    this.step('sync', () => this.syncSettingsUI());

    this.step('volume', () => Player.setVolume(S.volume));
    document.body.classList.add('has-mobnav');

    // Главный экран рисуем сразу, всё остальное подтягиваем параллельно —
    // окно перестаёт «висеть» на старте.
    this.step('studio', () => Studio.init());
    this.step('workspace', () => Workspace.init());
    this.step('home-v5', () => Home.init());
    this.step('ui-v6', () => InterfaceV6.init());
    this.step('ui-v7', () => InterfaceV7.init());
    this.step('experience-v8', () => ExperienceV8.init());
    this.step('custom-avatars', () => CustomAvatars.init());
    this.step('experience-v9', () => ExperienceV9.init());
    // Public/local track counters were removed in v38; no stats observers or requests.
    this.step('song-finder', () => SongFinder.init());
    this.step('home-picks', () => HomePicks20.init());
    this.step('home', () => Views.renderHome(false));

    refreshLikes();
    refreshPlaylists();
    // Очередь с прошлого запуска: треки на месте, играть начнёт по кнопке.
    await karaokeState;
    this.step('restore', () => Player.restoreState());
    this.step('lyricFind', () => Karaoke.bindFind());
    setTimeout(() => this.checkHealth(), 400);
    // Доклад о том, что интерфейс собрался: пока его нет, следующий запуск
    // считает прошлый неудачным и поднимается облегчённым (main.py).
    api('/api/boot/ok', { method: 'POST' }).catch(() => {});
    if (SAFE) this.safeBanner();
    if (this.bootErrors && this.bootErrors.length) {
      setTimeout(() => toast(t('Some parts did not load') + ': ' +
                             this.bootErrors.join(', '), 6000), 900);
    }
  },

  /* Полоса сверху в облегчённом режиме: человек должен понимать, почему
     оформление пропало и как вернуть обычный запуск. */
  safeBanner() {
    const bar = el('div', 'safe-bar');
    bar.innerHTML =
      `<span>${esc(t('Safe mode: the previous start did not finish, so the heavy visuals are off and settings are not saved.'))}</span>`;
    const btn = el('button', 'btn g', t('Start normally'));
    btn.onclick = () => { location.href = location.pathname; };
    bar.appendChild(btn);
    document.body.appendChild(bar);
  },

  /* Раздел настроек: подсветка пункта и ленивая загрузка его данных. */
  openPane(name) {
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.settingsPane(name);
    document.querySelectorAll('#setTabs [data-pane]').forEach(node =>
      node.classList.toggle('on', node.dataset.pane === name));
    document.querySelectorAll('.pane').forEach(pane =>
      pane.classList.toggle('on', pane.dataset.pane === name));
    const body = document.querySelector('.set-body');
    if (body) body.scrollTop = 0;
    if (name === 'sketch') Sketch.build();
    if (name === 'look2') { Wall.build(); Look.build(); }
    if (name === 'themes') Tune.build();
    if (name === 'sound') {
      // Виджет создаём один раз и только когда на него действительно смотрят.
      const host = $('setEq');
      if (host && !host.children.length) Equalizer.mount(host);
      Equalizer.paintAll();
    }
    if (name === 'plugins') { Plugins.load(); CustomPlugins.load(); }
    if (name === 'themes') Themes.build();
    if (name === 'avatar') Avatars.build();
    if (name === 'integrations') Integrations.load();
    if (name === 'keys') Hotkeys.build();
    if (name === 'news') News.build();
    if (name === 'logs') Logs.start(); else Logs.stop();
  },

  /* ------------------------------------------------------------ навигация */
  go(view, push = true) {
    if (view === 'liked') { this.openLiked(); return; }
    if (view === 'history') { this.openHistory(); return; }
    this.navigationToken = (this.navigationToken || 0) + 1;
    if (push && K.view !== view) K.stack.push(K.view);
    K.view = view;
    const id = 'v' + view[0].toUpperCase() + view.slice(1);
    document.querySelectorAll('.view').forEach(node => node.classList.toggle('on', node.id === id));
    document.querySelectorAll('[data-nav]').forEach(btn =>
      btn.classList.toggle('on', btn.dataset.nav === view));
    $('scroll').scrollTop = 0;
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.onNavigate(view);

    if (view === 'home') Views.renderHome(false);
    if (view === 'lib') Views.renderLibrary();
    if (view === 'search') { $('q').focus(); if (!K.search.query) Studio.searchLanding(); }
  },

  /* Подсветка пункта меню для виртуальных разделов (Любимое, История). */
  markNav(name) {
    document.querySelectorAll('[data-nav]').forEach(btn =>
      btn.classList.toggle('on', btn.dataset.nav === name));
  },

  back() {
    if (typeof Workspace !== 'undefined' && Workspace.ready) { Workspace.travel(-1); return; }
    const prev = K.stack.pop() || 'home';
    this.go(prev, false);
  },

  /* --------------------------------------------------------------- поиск */
  /* Источники опрашиваются параллельно, и выдача дополняется по мере ответов:
     первые треки видно через доли секунды, а не после самого медленного сервиса.
     Альбомы, плейлисты и исполнители идут отдельным запросом (/api/search/extra)
     и появляются сразу, как только каталог ответил, — не ждут треков. */
  async search(query, force) {
    query = (query || '').trim();
    if (!query) return;
    // Ссылку на плейлист Spotify, YouTube или SoundCloud не ищем, а переносим.
    if (Convert.looksLikeLink(query)) { this.cancelSearch(); Convert.open(query); return; }
    this.searchController?.abort();
    this.moreController?.abort();
    this.moreController = null;
    const controller = this.searchController = new AbortController();
    const token = ++this.searchToken;
    K.search = { query, page: 0, tracks: [], authors: [], official: [], albums: [], playlists: [],
                 loading: true, more: false, extraDone: false, token };
    this.searchTab = 'all';
    Studio.startSearch();
    this.go('search');
    $('q').blur();
    // Шапку и вкладки обновляем сразу: раньше заголовок «Результаты: …» и
    // кнопка «Показать ещё» оставались от прошлого запроса, пока не ответит
    // первый источник.
    $('sTitle').textContent = t('Results: ') + query;
    $('sMore').style.display = 'none';
    $('sTracksH').style.display = '';
    Views.skeletons($('sTracks'), 8, 'row');
    ['sAuthors', 'sAlbums', 'sPlaylists'].forEach(id => { $(id).style.display = 'none'; });
    Views.searchTabs(this.searchTab, null);
    this.loading(true);
    if (force) dropCache('/api/search');

    // Полки каталога — параллельно с треками.
    const extra = cachedApi('/api/search/extra?' + new URLSearchParams({ q: query, limit: 20 }),
                            300000, { timeout: 30000, signal: controller.signal, cacheIf: d => !d.degraded })
      .then(data => {
        if (token !== this.searchToken) return;
        K.search.official = data.authors || [];
        ['albums', 'playlists'].forEach(key => {
          (data[key] || []).forEach(item => {
            if (!K.search[key].some(other => other.id === item.id)) K.search[key].push(item);
          });
        });
      })
      .catch(err => { if (token === this.searchToken) console.warn('[search] extra', err.message); })
      .finally(() => {
        if (token !== this.searchToken) return;
        K.search.extraDone = true;
        this.renderSearchState(!K.search.loading);
      });

    let first = true;
    const jobs = activeSources().map(async source => {
      try {
        const data = await this.fetchSearch(query, 0, source, controller.signal);
        if (token !== this.searchToken) return;
        // v73: skeletons stay until some source actually has tracks — an empty
        // first answer used to leave a blank list while the others loaded.
        if (first && (data.tracks || []).length) { $('sTracks').innerHTML = ''; first = false; }
        Studio.sourceStatus(source, 'ok');
        this.mergeSearch(data, false);
      } catch (err) {
        if (token === this.searchToken) { Studio.sourceStatus(source, 'error'); console.warn('[search]', source, err.message); }
      }
    });

    await Promise.allSettled(jobs);
    if (token !== this.searchToken) return;
    K.search.loading = false;
    this.loading(false);
    this.renderSearchState(true);
    await extra;
    if (token !== this.searchToken) return;
    if (this.searchController === controller) this.searchController = null;
    if (!K.search.tracks.length && !K.search.albums.length && !K.search.playlists.length
        && !this.searchAuthors().length) {
      toast(t('Nothing found'));
    }
  },

  /* v73: one recording found by several sources is one row. The server marks
     every track with m73 = [core title, artist names, version tags]; rows with
     the same title and tags and a shared artist fold together, the more
     trusted source stays (YouTube > Spotify > SoundCloud > others) and keeps
     the better score. Page 0 is ordered by score; "Show more" appends its rows
     below what is already on screen instead of reshuffling the list. */
  mergeSearch(data, done, append) {
    const trust = source => ({ youtube: 3, spotify: 2, soundcloud: 1 })[source] || 0;
    const same = (a, b) => {
      const x = a.m73, y = b.m73;
      return !!(x && y && x[0] && x[0] === y[0] && String(x[2] || '') === String(y[2] || '')
        && (x[1] || []).some(name => (y[1] || []).includes(name)));
    };
    const list = K.search.tracks.slice();
    const ids = new Set(list.map(x => x.id));
    const added = [];
    (data.tracks || []).forEach(track => {
      if (!track || ids.has(track.id)) return;
      const at = list.findIndex(other => other.source !== track.source && same(other, track));
      if (at < 0) { ids.add(track.id); (append ? added : list).push(track); return; }
      const old = list[at];
      // On "Show more" rows already on screen never change under the pointer.
      const keep = !append && trust(track.source) > trust(old.source) ? track : old;
      const drop = keep === track ? old : track;
      list[at] = { ...keep, search_score: Math.max(+old.search_score || 0, +track.search_score || 0),
                   also73: [...new Set([...(old.also73 || []), ...(track.also73 || []), drop.source])].filter(s => s !== keep.source) };
      ids.add(track.id);
    });
    const byScore = (a, b) => (+b.search_score || 0) - (+a.search_score || 0);
    K.search.tracks = append ? list.concat(added.sort(byScore)) : list.sort(byScore);
    (data.authors || []).forEach(author => {
      if (!K.search.authors.some(x => x.name.toLowerCase() === author.name.toLowerCase())) {
        K.search.authors.push(author);
      }
    });
    ['albums', 'playlists'].forEach(key => {
      (data[key] || []).forEach(item => {
        if (!K.search[key].some(other => other.id === item.id)) K.search[key].push(item);
      });
    });
    K.search.more = K.search.more || !!data.has_more;
    this.renderSearchState(done);
  },

  /* Официальные карточки каталога первыми, затем авторы из найденных треков. */
  searchAuthors() {
    const out = [];
    const seen = new Set();
    [...(K.search.official || []), ...(K.search.authors || [])].forEach(author => {
      const key = String(author.name || '').trim().toLowerCase();
      if (!key || seen.has(key)) return;
      seen.add(key);
      out.push(author);
    });
    return out;
  },

  setSearchTab(tab) {
    this.searchTab = tab || 'all';
    this.renderSearchState(!K.search.loading);
    $('scroll').scrollTop = 0;
  },

  renderSearchState(done) {
    // Одиночные релизы сервер уже отсеял; здесь — страховка для карточек,
    // у которых число треков известно.
    const big = list => (list || []).filter(x => !x.count || x.count >= 2);
    const filtered = Studio.filterTracks(K.search.tracks);
    Studio.searchSummary(filtered, done);
    Views.renderSearch({
      query: K.search.query,
      tab: this.searchTab || 'all',
      tracks: filtered,
      authors: this.searchAuthors(),
      albums: big(K.search.albums),
      playlists: big(K.search.playlists),
      hasMore: K.search.more,
      done,
      extraDone: !!K.search.extraDone,
    });
  },

  fetchSearch(query, page, source, signal) {
    const params = new URLSearchParams({
      q: query, sources: source || activeSources().join(','), limit: S.limit, page,
      // полки приходят отдельным запросом — треки их не ждут
      collections: 0, ranking: 34,
    });
    // Поиск не имеет права висеть вечно: лучше честная ошибка и повтор.
    // v73: a degraded answer (the catalogue query failed) is not cached.
    return cachedApi('/api/search?' + params, 300000, { timeout: 30000, signal, cacheIf: d => !d.degraded });
  },

  async more() {
    if (K.search.loading || !K.search.query || !K.search.more) return;
    const state = K.search;
    const token = this.searchToken;
    const controller = this.moreController = new AbortController();
    state.loading = true;
    this.loading(true);
    $('bMore').textContent = t('Loading…');
    const page = state.page + 1;
    try {
      const results = await Promise.allSettled(activeSources().map(source =>
        this.fetchSearch(state.query, page, source, controller.signal)));
      const chunks = results.filter(result => result.status === 'fulfilled').map(result => result.value);
      const failed = results.some(result => result.status !== 'fulfilled' || result.value.degraded);
      // Пока грузилось, пользователь мог начать новый поиск.
      if (token !== this.searchToken) return;
      // Keep the page retryable if even one source failed; merging is deduplicated.
      if (!failed) state.page = page;
      state.more = false;
      this.mergeSearch({ tracks: chunks.flatMap(chunk => chunk.tracks || []),
                         has_more: failed || chunks.some(chunk => chunk.has_more) }, true, true);
      if (failed) toast(t('Could not load more: ') + (LANG === 'ru' ? 'повторите попытку' : 'please retry'));
    } catch (err) {
      if (token === this.searchToken) toast(t('Could not load more: ') + err.message);
    } finally {
      if (this.moreController === controller) this.moreController = null;
      if (token === this.searchToken) {
        $('bMore').textContent = t('Show more');
        state.loading = false;
        this.loading(false);
        this.renderSearchState(true);
      }
    }
  },

  cancelSearch() {
    if (!this.searchController && !this.moreController) return;
    this.searchToken++;
    this.searchController?.abort(); this.searchController = null;
    this.moreController?.abort(); this.moreController = null;
    K.search.loading = false; K.search.extraDone = true; K.search.cancelled = true;
    for (const [source, status] of Object.entries(Studio.statuses || {}))
      if (status === 'loading') Studio.sourceStatus(source, 'cancelled');
    this.loading(false); this.renderSearchState(true);
    if (!K.search.tracks.length && !K.search.albums.length && !K.search.playlists.length && !this.searchAuthors().length)
      $('sTracks').textContent = LANG === 'ru' ? 'Поиск отменён. Введите новый запрос.' : 'Search cancelled. Enter a new query.';
  },

  loading(on) { $('loadBar').classList.toggle('on', !!on); },

  /* История поиска и подсказки живут в hints.js: список всплывает по
     щелчку по строке и во время печати, после выбора закрывается. */

  /* --------------------------------------------------------------- автор */
  async openAuthor(name, url, source) {
    this.go('author');
    $('aName').textContent = name || t('Artist');
    $('aKind').textContent = source ? sourceName(source) : t('Artist');
    setImg($('aPic'), null);
    this.authorPicture = '';
    this.authorName = name || '';
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.record({ view: 'author', name, url, source });
    this.authorTracks = [];
    Views.skeletons($('aTracks'), 8, 'row');
    // пока грузится один автор, можно кликнуть по другому — рисуем только последний
    const token = (this.authorToken = (this.authorToken || 0) + 1);
    try {
      const params = new URLSearchParams({ name: name || '' });
      if (url) params.set('url', url);
      if (source) params.set('source', source);
      params.set('catalog', 'v15'); // Invalidate cached pre-filter artist pages.
      const path = '/api/author?' + params;
      // Неполный или пустой ответ в кэш не кладём — иначе страница автора
      // остаётся пустой при каждом следующем заходе.
      const full = d => !d.partial;
      const data = await cachedApi(path, 600000, { timeout: 30000, cacheIf: d => full(d) && (d.tracks || []).length > 0 });
      if (token !== this.authorToken || K.view !== 'author') return;
      setImg($('aPic'), data.picture);
      this.authorPicture = data.picture || '';
      this.authorName = data.name || name || '';
      $('aName').textContent = data.name;
      this.authorTracks = data.tracks || [];
      // Пока треков нет, оставляем скелетоны: пустой экран вместо загрузки
      // выглядел как «ничего не работает».
      if (this.authorTracks.length) Views.renderTracks($('aTracks'), this.authorTracks);
      else if (full(data)) this.renderAuthorEmpty();
      if (!full(data)) this.refreshAuthor(path, token);
    } catch (err) {
      if (token !== this.authorToken || K.view !== 'author') return;
      $('aTracks').innerHTML = `<div class="empty">${icon('user')}<div>${esc(err.message)}</div></div>`;
    }
  },

  /* Догрузка страницы автора: без скелетонов и мигания. Если пользователь
     ушёл на другого автора, результат просто выбрасывается. */
  renderAuthorEmpty() {
    $('aTracks').innerHTML = `<div class="empty">${icon('user')}<div>${t('Nothing was found for this artist')}</div></div>`;
  },

  async refreshAuthor(path, token, tries = 6) {
    const full = d => !d.partial;
    for (let i = 0; i < tries; i++) {
      await new Promise(done => setTimeout(done, 2500));
      if (token !== this.authorToken || K.view !== 'author') return;
      dropCache(path);
      let data;
      try {
        data = await cachedApi(path, 0, { timeout: 30000, cacheIf: d => full(d) && (d.tracks || []).length > 0 });
      } catch { continue; }
      if (token !== this.authorToken || K.view !== 'author') return;
      if (JSON.stringify(data.tracks || []) !== JSON.stringify(this.authorTracks || [])) {
        setImg($('aPic'), data.picture);
        if (data.picture) this.authorPicture = data.picture;
        this.authorTracks = data.tracks || [];
        if (this.authorTracks.length) Views.renderTracks($('aTracks'), this.authorTracks);
        else if (full(data)) this.renderAuthorEmpty();
      }
      if (full(data)) { if (!(this.authorTracks || []).length) this.renderAuthorEmpty(); return; }
    }
    // Ничего так и не пришло — честно говорим об этом вместо вечных скелетонов.
    if (token === this.authorToken && !(this.authorTracks || []).length) {
      $('aTracks').innerHTML =
        `<div class="empty">${icon('user')}<div>${t('Nothing was found for this artist')}</div></div>`;
    }
  },

  /* ------------------------------------------------- обмен плейлистами */
  /* Плеер работает без сервера аккаунтов, поэтому «поделиться» — это короткий
     код: сжатый список треков, который друг вставляет у себя. Всё офлайн,
     ничего никуда не выгружается. */
  async sharePlaylist(id, name) {
    try {
      const data = await api(`/api/playlists/${id}/share`);
      this.showShare(data.name || name, data.count, data.code);
    } catch (err) {
      toast(err.message || t('Could not build the code'));
    }
  },

  /* Тот же код, но для списка, которого нет в базе (лайки, микс, история). */
  async shareTracks(name, tracks) {
    if (!tracks || !tracks.length) { toast(t('This list is empty')); return; }
    try {
      const data = await api('/api/playlists/share-list', {
        method: 'POST', body: { name, tracks },
      });
      this.showShare(data.name || name, data.count, data.code);
    } catch (err) {
      toast(err.message || t('Could not build the code'));
    }
  },

  showShare(name, count, code) {
    this.shareName = name;
    $('shareSub').textContent = `${name} · ${count} ` + t('tracks');
    $('shareCode').value = code;
    openModal('mShare');
    setTimeout(() => $('shareCode').select(), 60);
  },

  async saveShareFile() {
    return FileSave27.save({kind:'playlist',name:FileSave27.name(this.shareName||'playlist','.kryx'),text:$('shareCode').value});
  },

  /* Импорт в два шага: сначала показываем, что лежит в коде, и даём выбрать
     и треки (галочки), и место — новый плейлист или любой существующий.
     Раньше код молча создавал ещё один плейлист, и добавить песни в уже
     собранный список было нельзя. */
  async importPlaylist(code) {
    const text = (code || '').trim();
    if (!text) { toast(t('Paste the code first')); return; }
    let data;
    try {
      data = await api('/api/playlists/decode', { method: 'POST', body: { code: text } });
    } catch (err) {
      toast(err.message || t('This share code is not valid'));
      return;
    }
    closeModals();
    this.showImportPick(data.name, data.tracks || []);
  },

  showImportPick(name, tracks) {
    this.ipTracks = tracks;
    this.ipTarget = 0;                        // 0 — новый плейлист
    // Базово отмечены все треки: чаще всего нужен весь список.
    this.ipPicked = new Set(tracks.map((_, i) => i));
    $('ipSub').textContent = `${name} · ${tracks.length} ` + t('tracks');
    $('ipName').value = name;
    this.renderImportTargets();
    this.renderImportTracks();
    openModal('mImportPick');
  },

  renderImportTargets() {
    const box = $('ipTargets');
    if (!box) return;
    box.innerHTML = '';
    const row = (label, sub, id, iconName) => {
      const node = el('button', 'tr' + (this.ipTarget === id ? ' on' : ''));
      node.innerHTML = `<span class="n">${icon(iconName, 'ic s')}</span>
        <span class="meta"><span class="t clip">${esc(label)}</span>
        <span class="a">${esc(sub)}</span></span>`;
      node.onclick = () => {
        this.ipTarget = id;
        $('ipNameRow').style.display = id ? 'none' : '';
        this.renderImportTargets();
      };
      box.appendChild(node);
    };
    row(t('Create a new playlist'), t('The tracks go to a brand new list'), 0, 'plus');
    (K.playlists || []).forEach(playlist => row(
      playlist.name,
      `${playlist.count} ${plural(playlist.count, t('track'), t('tracks'), t('tracks'))}`,
      playlist.id, 'queue'));
    $('ipNameRow').style.display = this.ipTarget ? 'none' : '';
  },

  renderImportTracks() {
    const box = $('ipTracks');
    if (!box) return;
    box.innerHTML = '';
    this.ipTracks.forEach((track, index) => {
      const row = el('label', 'tr pick');
      row.innerHTML = `<input type="checkbox" ${this.ipPicked.has(index) ? 'checked' : ''}>
        <span class="meta"><span class="t clip">${esc(track.title || track.id)}</span>
        <span class="a clip">${esc(track.artist || '')}</span></span>`;
      row.querySelector('input').onchange = event => {
        if (event.target.checked) this.ipPicked.add(index);
        else this.ipPicked.delete(index);
        this.paintImportCount();
      };
      box.appendChild(row);
    });
    this.paintImportCount();
  },

  paintImportCount() {
    const node = $('ipCount');
    if (node) node.textContent = `${this.ipPicked.size} / ${this.ipTracks.length}`;
    const ok = $('ipOk');
    if (ok) ok.disabled = !this.ipPicked.size;
  },

  async runImportPick() {
    const tracks = this.ipTracks.filter((_, i) => this.ipPicked.has(i));
    if (!tracks.length) { toast(t('Pick at least one track')); return; }
    try {
      const body = { tracks };
      if (this.ipTarget) body.playlist_id = this.ipTarget;
      else body.name = ($('ipName').value || '').trim() || t('Playlist');
      const data = await api('/api/playlists/import', { method: 'POST', body });
      closeModals();
      await refreshPlaylists();
      Views.renderLibrary();
      Views.renderSidePlaylists();
      toast(`${data.name} · ${data.added} ` + t('tracks added'));
      this.openPlaylist(data.id, data.name);
    } catch (err) {
      toast(err.message || t('This share code is not valid'));
    }
  },

  /* Заголовок открытого списка. Имя плейлиста, импорта или микса — данные
     пользователя, их переводить нельзя; у своих списков («Понравившиеся»,
     «История») имя наше и переводится вместе с остальным интерфейсом. */
  setListName(name, state) {
    const head = $('lName');
    if (!head) return;
    const own = !!(state &&
      ['playlist', 'mix', 'spotify', 'import', 'collection'].includes(state.type));
    if (own) head.setAttribute('data-no-i18n', '');
    else head.removeAttribute('data-no-i18n');
    head.textContent = state && state.type === 'playlist' ? plName(name) : name;
  },

  /* ---------------------------------------------------- списки треков */
  showList(name, tracks, state) {
    Views.listState = state;
    this.go('list');
    this.setListName(name, state);
    const save = $('lSave');
    if (save) {
      // импортированный список можно сохранить как обычный плейлист приложения
      // Альбом и плейлист каталога тоже можно забрать себе целиком.
      const importable = state && ['spotify', 'mix', 'collection'].includes(state.type);
      save.style.display = importable && tracks.length ? '' : 'none';
      save.onclick = () => this.saveListAsPlaylist(name, tracks);
    }
    // «Добавить треки» есть только у собственных плейлистов: в «Понравившихся»
    // и в истории добавлять нечего.
    const add = $('lAdd');
    if (add) {
      const own = !!(state && state.type === 'playlist');
      add.style.display = own ? '' : 'none';
      add.onclick = own ? () => Finder.open({
        id: state.id,
        name: state.name || name,
        ids: (this.listTracks || []).map(item => item.id),
      }) : null;
    }
    $('lCount').textContent = `${tracks.length} ${plural(tracks.length, t('track'), t('tracks'), t('tracks'))}`;
    if (!tracks.length) {
      $('lTracks').innerHTML = `<div class="empty">${icon('note')}<div>${t('Nothing here yet')}</div></div>`;
    } else {
      Views.renderTracks($('lTracks'), tracks);
    }
    this.listTracks = tracks;
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.listLoaded(name, tracks, state);
  },

  /* Сохранение импортированного списка (например из Spotify) в свой плейлист. */
  async saveListAsPlaylist(name, tracks) {
    if (!tracks || !tracks.length) return;
    const button = $('lSave');
    if (button) { button.disabled = true; button.textContent = t('Loading…'); }
    try {
      // сервер умеет принять сразу весь список — один запрос вместо сотни
      const created = await api('/api/playlists', { method: 'POST', body: { name, tracks } });
      const id = created.id || (created.item && created.item.id);
      await refreshPlaylists();
      toast(t('Playlist created') + ': ' + name);
      this.openPlaylist(id, name);
    } catch (err) {
      toast(t('Error'));
    } finally {
      if (button) { button.disabled = false; button.textContent = t('Save as playlist'); }
    }
  },

  async openPlaylist(id, name) {
    Views.listState = { type: 'playlist', id, name };
    this.go('list');
    this.setListName(name, Views.listState);
    Views.skeletons($('lTracks'), 6, 'row');
    const token = this.navigationToken;
    Workspace.listLoading(name, Views.listState);
    let data;
    try { data = await api(`/api/playlists/${id}/tracks`, { timeout: 15000 }); }
    catch (err) { if (token === this.navigationToken) Workspace.listError(err, () => this.openPlaylist(id, name)); return; }
    if (token !== this.navigationToken || K.view !== 'list') return;
    this.showList(name, data.items || [], { type: 'playlist', id, name });
  },

  /* Перерисовать открытый плейлист, не трогая прокрутку остальных экранов.
     Нужен, когда треки добавляются из окна поиска. */
  async refreshOpenPlaylist() {
    const state = Views.listState;
    if (!state || state.type !== 'playlist') return;
    try {
      const data = await api(`/api/playlists/${state.id}/tracks`);
      if (Views.listState !== state || K.view !== 'list') return;
      this.showList(state.name, data.items || [], state);
    } catch { /* сервер ответит в следующий раз */ }
  },

  async openLiked() {
    this.go('list');
    this.markNav('liked');
    Views.skeletons($('lTracks'), 6, 'row');
    const token = this.navigationToken;
    Workspace.listLoading(t('Liked tracks'), { type: 'liked' });
    await refreshLikes();
    if (token !== this.navigationToken || K.view !== 'list') return;
    this.showList(t('Liked tracks'), K.likedTracks || [], { type: 'liked' });
    this.markNav('liked');
  },

  /* --------------------------------------------- альбомы и плейлисты каталога */
  /* Содержимое альбома или плейлиста открывается как обычный список треков:
     его можно слушать, перемешать, добавить в очередь и сохранить себе. */
  async openCollection(item) {
    if (!item || !item.id) return;
    const state = { type: 'collection', id: item.id, name: item.title || '',
                    kind: item.kind, cover: item.thumbnail || '',
                    artist: item.artist || '' };
    Views.listState = state;
    this.go('list');
    this.setListName(item.title || t('Album'), state);
    Views.skeletons($('lTracks'), 8, 'row');
    try {
      const data = await cachedApi('/api/collection?id=' + encodeURIComponent(item.id) + '&all=1&v=34',
                                   900000, { timeout: 120000 });
      if (Views.listState !== state) return;
      if (!state.cover && data.thumbnail) state.cover = data.thumbnail;
      this.showList(data.title || item.title || '', data.tracks || [], state);
    } catch (err) {
      if (Views.listState !== state) return;
      this.showList(item.title || '', [], state);
      toast(err.message || t('Could not open this album'));
    }
  },

  /* Кнопка на карточке: релиз уходит играть или в очередь без открытия. */
  async playCollection(item, opts = {}) {
    if (!item || !item.id) return;
    toast(t('Loading…'));
    try {
      const data = await cachedApi('/api/collection?id=' + encodeURIComponent(item.id) + '&all=1&v=34',
                                   900000, { timeout: 120000 });
      const tracks = data.tracks || [];
      if (!tracks.length) { toast(t('Nothing here yet')); return; }
      if (opts.queue) {
        tracks.forEach(track => Player.queue.push(track));
        Views.renderQueue();
        toast(t('Added to the queue'));
        return;
      }
      Player.playList(tracks, false);
    } catch (err) {
      toast(err.message || t('Could not open this album'));
    }
  },

  async openHistory() {
    this.go('list');
    this.markNav('history');
    Views.skeletons($('lTracks'), 8, 'row');
    const token = this.navigationToken;
    Workspace.listLoading(t('History'), { type: 'history' });
    let data;
    try { data = await api('/api/history?limit=200', { timeout: 15000 }); }
    catch (err) { if (token === this.navigationToken) Workspace.listError(err, () => this.openHistory()); return; }
    if (token !== this.navigationToken || K.view !== 'list') return;
    this.showList(t('History'), data.items || [], { type: 'history' });
    this.markNav('history');
  },

  async deletePlaylist(id) {
    await api('/api/playlists/' + id, { method: 'DELETE' });
    await refreshPlaylists();
    Views.renderLibrary();
    toast(t('Playlist deleted'));
    if (K.view === 'list') this.go('lib');
  },

  openAddTo(track) {
    this.addTrack = track;
    const box = $('addToList');
    box.innerHTML = '';
    K.playlists.forEach(playlist => {
      const row = el('button', 'tr');
      row.innerHTML = `<span class="n">${icon('plus', 'ic s')}</span><img alt="">
        <span class="meta"><span class="t clip">${esc(plName(playlist.name))}</span>
        <span class="a">${playlist.count} ${plural(playlist.count, t('track'), t('tracks'), t('tracks'))}</span></span>`;
      setImg(row.querySelector('img'), playlist.cover);
      row.onclick = async () => {
        await api(`/api/playlists/${playlist.id}/tracks`, { method: 'POST', body: { track } });
        closeModals();
        refreshPlaylists();
        toast(t('Added to') + ' «' + playlist.name + '»');
      };
      box.appendChild(row);
    });
    const create = el('button', 'btn g', t('Create a new playlist'));
    create.style.width = '100%';
    create.style.marginTop = '12px';
    create.onclick = () => { closeModals(); openModal('mNewPl'); };
    box.appendChild(create);
    openModal('mAddTo');
  },

  async startRadio(track) {
    toast(t('Building radio…'));
    try {
      const data = await api('/api/radio', { method: 'POST', body: { track: track || Player.current } });
      const items = data.items || [];
      if (!items.length) { toast(t('Could not build radio')); return; }
      Player.playList([track || Player.current, ...items].filter(Boolean), false);
    } catch (err) { toast(t('Radio unavailable: ') + err.message); }
  },

  async playMix() {
    toast(t('Building your mix…'));
    try {
      const data = await api('/api/mix?limit=50');
      if (!data.items || !data.items.length) { toast(t('Not enough data for a mix yet')); return; }
      Player.playList(data.items, true);
      this.showList(t(data.title), data.items, { type: 'mix' });
    } catch (err) { toast(t('Failed: ') + err.message); }
  },

  /* ------------------------------------------------------------ настройки */
  buildSettings() {
    Themes.build();
    this.buildKaraokePane();

    const langs = $('langChips');
    if (langs) {
      langs.innerHTML = '';
      LANGS.forEach(([code, name]) => {
        const chip = el('button', 'chip' + (S.lang === code ? ' on' : ''), name);
        chip.dataset.noI18n = '';
        chip.onclick = () => {
          S.lang = code;
          saveSettings();
          setLang(code);
        };
        langs.appendChild(chip);
      });
    }
  },

  /* Караоке: сцены и режимы выбираются карточками и чипами, без выпадающих
     списков — их системный вид не читался на тёмной теме. */
  buildKaraokePane() {
    if (typeof KCustom !== 'undefined') KCustom.build();
    if (typeof VMedia !== 'undefined') VMedia.build();
    const scenes = [
      ['aurora',    'Aurora',   'Soft colour clouds from the artwork'],
      ['albumflow', 'Album flow', 'Slow flowing colours sampled from the current artwork'],
      ['stage',     'Stage',    'Almost black hall and huge soft lights, like Apple Music'],
      ['waves',     'Waves',    'Calm layered waves'],
      ['bars',      'Spectrum', 'Classic bars driven by the frequencies'],
      ['mirror',    'Mirror',   'Spectrum mirrored around the centre'],
      ['particles', 'Particles','Light dust floating upwards'],
      ['stars',     'Starfield','Flying through stars, faster on loud parts'],
      ['rings',     'Rings',    'A ring flies out on every beat'],
      ['grid',      'Grid',     'Synthwave perspective grid'],
      ['glow',      'Glow',     'One calm light that breathes with the bass'],
      ['none',      'Off',      'Only the blurred artwork'],
    ];
    const grid = $('kScenes');
    if (grid) {
      grid.innerHTML = '';
      scenes.forEach(([id, name, note]) => {
        const card = el('button', 'scene' + (S.karaokeStyle === id ? ' on' : ''));
        card.appendChild(el('span', 'scene-p sc-' + id));
        card.appendChild(el('span', 'scene-n', t(name)));
        card.appendChild(el('span', 'scene-h', t(note)));
        card.onclick = () => {
          Karaoke.stop(); S.karaokeStyle = id;
          saveSettings();
          if (S.karaokeBg && !S.noAnim) Karaoke.start();
          this.applyKaraoke();
          this.buildKaraokePane();
        };
        grid.appendChild(card);
      });
    }

    const pick = (id, key, options, after) => {
      const box = $(id);
      if (!box) return;
      box.innerHTML = '';
      options.forEach(([value, label]) => {
        const chip = el('button', 'chip' + (S[key] === value ? ' on' : ''), t(label));
        chip.onclick = () => {
          S[key] = value;
          saveSettings();
          this.buildKaraokePane();
          if (after) after();
        };
        box.appendChild(chip);
      });
    };
    pick('kMode', 'karaokeMode',
         [['split', 'Artwork and lyrics'], ['focus', 'Lyrics only'], ['cinema', 'Cinema'], ['disc', 'Disc']],
         () => { this.applyKaraoke(); Karaoke.center(true); });
    pick('kAlign', 'karaokeAlign', [['left', 'Left'], ['center', 'Centre']],
         () => this.applyKaraoke());
    pick('kSize', 'karaokeSize', [['s', 'Small'], ['m', 'Medium'], ['l', 'Large']],
         () => this.applyKaraoke());
    pick('kLit', 'karaokeLit', [['text', 'White'], ['accent', 'Accent']],
         () => this.applyKaraoke());
    pick('kLook', 'karaokeLook', [['glow', 'Glow'], ['apple', 'Apple']],
         () => this.applyKaraoke());

    // Качество обложек. Смена перерисовывает текущий экран: новые ссылки
    // уходят в браузер сразу, кэш картинок прежних размеров не мешает.
    pick('kCover', 'coverQuality',
         [['normal', 'Normal'], ['high', 'High'], ['max', 'Maximum']],
         () => {
           if (Player.current) Player.paintTrack();
           Disc.setArt(Player.current ? KCustom.cover(Player.current.thumbnail) : null);
           if (typeof Viz !== 'undefined') Viz.paint();
           if (K.view === 'home') Views.renderHome(false);
           if (K.view === 'search') this.renderSearchState(true);
         });

    // Режим «Диск»: вид сцены применяется на месте, текст не перестраивается.
    const disc = () => { Disc.apply(); };
    pick('dSync', 'discSync',
         [['line', 'Whole line']], disc);
    pick('dLayout', 'discLayout',
         [['side', 'Beside the disc'], ['under', 'Under the disc'],
          ['over', 'Over the disc']], disc);
    pick('dSkin', 'discCaseSkin',
         [['jewel', 'Jewel case'], ['bare', 'Bare disc'], ['vinyl', 'Vinyl']], disc);
    pick('dGlow', 'discGlowStyle',
         [['cover', 'From the cover'], ['white', 'White bloom'], ['off', 'Off']],
         // Старый переключатель свечения мог остаться выключенным: выбор
         // стиля должен включать свет, иначе чипы выглядят сломанными.
         () => { S.discGlow = true; saveSettings(); Disc.apply(); });
  },

  buildLibraries() {
    const box = $('libList');
    if (!box) return;
    const known = (K.health && K.health.sources) || [];
    // Показываем только библиотеки, чьи плагины установлены и включены.
    const allowed = (K.health && K.health.plugin_sources) || ALL_SOURCES;
    const metas = ALL_SOURCES.filter(id => allowed.includes(id)).map(id => {
      const found = known.find(s => s.id === id);
      return { id, name: sourceName(id), note: found ? found.note : '',
               available: found ? found.available !== false : true };
    });
    box.innerHTML = '';
    metas.forEach(meta => {
      const row = el('div', 'set');
      const info = el('div', '',
        `<div class="l">${meta.name}${meta.available ? '' : ' <span class="h">— ' + t('unavailable') + '</span>'}</div>` +
        (meta.note ? `<div class="h">${t(meta.note)}</div>` : ''));
      const ctl = el('div', 'c');
      const on = activeSources().includes(meta.id);
      const sw = el('div', 'sw' + (on ? ' on' : ''));
      sw.onclick = () => {
        const list = new Set(activeSources());
        if (list.has(meta.id)) list.delete(meta.id); else list.add(meta.id);
        if (!list.size) { toast(t('At least one library must stay enabled')); return; }
        S.sources = ALL_SOURCES.filter(id => list.has(id));
        saveSettings();
        dropCache('/api/search');
        this.buildLibraries();
      };
      ctl.appendChild(sw);
      row.appendChild(info); row.appendChild(ctl);
      box.appendChild(row);
    });
    if (!metas.length) {
      box.appendChild(el('div', 'hint',
        t('No streaming plugins are enabled — open the Plugins tab and install one')));
    }
  },

  /* После смены языка перерисовываем всё, что собрано в JS. */
  afterLangChange() {
    this.paintAudioCache();
    this.buildSettings();
    this.buildLibraries();
    if (Plugins.loaded) { Plugins.renderCategories(); Plugins.render(); }
    Themes.build();
    Sketch.build(); Wall.build(); Look.build();
    Hotkeys.build && Hotkeys.build();
    News.build && News.build();
    if (Integrations.items && Integrations.items.length) Integrations.render();
    this.syncSettingsUI();
    Views.renderSidePlaylists();
    if (Views.listState && Views.listState.type === 'playlist') this.setListName(Views.listState.name, Views.listState);
    if (K.view === 'home') Views.renderHome(false);
    if (K.view === 'search') this.renderSearchState(true);
    Player.paintTrack && Player.current && Player.paintTrack();
    Player.paintIdle && Player.paintIdle();
    if (typeof Logs !== 'undefined' && Logs.items && Logs.items.length) Logs.render();
    // Строки состояния собираются из перевода и данных («… · версия»), поэтому
    // словарём их не перевести — просто запрашиваем и рисуем их заново.
    this.checkHealth();
    if ($('ui13PortraitCount')) $('ui13PortraitCount').textContent = tf('{count} VTuber portraits', {count:Avatars.items.filter(x=>x.collection==='portraits').length||76});
    if (typeof CustomAvatars !== 'undefined' && CustomAvatars.dialog) CustomAvatars.refreshLabels();
    if (typeof ExperienceV8 !== 'undefined') { ExperienceV8.renderStore(); if (ExperienceV8.lastRecommendationData) ExperienceV8.recommendStatus(ExperienceV8.lastRecommendationData); }
    if (typeof Workspace !== 'undefined' && Workspace.ready) { Workspace.networkState(); Workspace.queueRendered(); if (K.view==='lib') Workspace.renderLibrary(); if (K.view==='list' && Workspace.listState) Workspace.listHeader(Workspace.listName,Workspace.listData,Workspace.listState); }
    if (typeof Studio!=='undefined') {
      document.querySelectorAll('.studio-local').forEach(n=>{const suffix=n.textContent.replace(/^.*?:\s*/, '');n.textContent=t('You')+': '+suffix;});
      document.querySelectorAll('.ui9-all-tracks').forEach(n=>{const count=n.textContent.match(/\d+$/)?.[0]||'';n.textContent=t('All tracks · ')+count;});
    }
    if(typeof Workspace!=='undefined'&&Workspace.ready)Workspace.apply();
    translateDom();
    document.querySelectorAll('.home-feature,.studio-featured').forEach(node=>{
      const title=node.querySelector('strong');
      node.setAttribute('aria-label',t('Play')+(title?': '+title.textContent:''));
    });
    if (typeof MiniPlayer !== 'undefined') MiniPlayer.push(true);
    if (typeof LocalCheck !== 'undefined' && LocalCheck.data && LocalCheck.render) LocalCheck.render();
    if (typeof CustomPlugins !== 'undefined' && CustomPlugins.data && CustomPlugins.render) CustomPlugins.render();
  },

  syncSettingsUI() {
    document.querySelectorAll('[data-sw]').forEach(node =>
      node.classList.toggle('on', !!S[node.dataset.sw]));
    const set = (id, value) => { const n = $(id); if (n) n.value = value; };
    set('sRadius', S.radius);
    set('sReactSense', S.reactSense);
    set('sLyricsOffset', S.lyricsOffset); set('sFade', S.fade); set('sVolume', S.volume); set('sLimit', String(S.limit));
    set('sStreamExpiry', String(S.streamExpiryMs));
    set('sDiscSize', S.discSize); set('sDiscTextSize', S.discTextSize);
    set('sDiscSpinSpeed', S.discSpinSpeed); set('sDiscLines', S.discLines);
    set('sDiscLead', S.discLead); set('sDiscHold', S.discHold);
    set('sDiscLinger', S.discLinger);
    set('sVizArt', S.vizArt); set('sVizText', S.vizText); set('sVizGlow', S.vizGlow);
    set('sVizBgLevel', S.vizBgLevel); set('sVizMotion', S.vizMotion);
    set('sVizSparkRate', S.vizSparkRate);
    set('sStreamRetries', String(S.streamResolutionRetries));
    set('vizSrcText', S.vizSrcText || '');
    set('cAccent', S.accent); set('cAccent2', S.accent2); set('cBg', S.bg);
    set('vol', S.volume);
    const text = (id, value) => { const n = $(id); if (n) n.textContent = value; };
    text('vRadius', S.radius); text('vFade', S.fade);
    text('vLyricsOffset', Number(S.lyricsOffset || 0).toFixed(2));
    text('vDiscSize', S.discSize); text('vDiscTextSize', S.discTextSize);
    text('vDiscSpinSpeed', S.discSpinSpeed); text('vDiscLines', S.discLines);
    text('vDiscLead', Number(S.discLead || 0).toFixed(2));
    text('vDiscHold', Number(S.discHold || 0).toFixed(2));
    text('vDiscLinger', Number(S.discLinger || 0).toFixed(1));
    text('vVizArt', S.vizArt); text('vVizText', S.vizText); text('vVizGlow', S.vizGlow);
    text('vVizBgLevel', S.vizBgLevel); text('vVizMotion', S.vizMotion);
    text('vVizSparkRate', S.vizSparkRate);
    set('sBal', Math.round((+S.balance || 0) * 100));
    this.paintBalance();
    if (typeof Equalizer !== 'undefined') Equalizer.paintAll();
    if (typeof Mixer !== 'undefined' && Mixer.built) Mixer.sync();
  },

  /* Подпись под регулятором баланса. */
  paintBalance() {
    const node = $('sBalV');
    if (!node) return;
    const value = Math.round((+S.balance || 0) * 100);
    node.textContent = value === 0 ? t('Centre')
      : value < 0 ? `${t('Left')} ${-value} %` : `${t('Right')} ${value} %`;
  },

  async refreshAudioCache() {
    const node = $('audioCacheState');
    if (!node) return;
    try {
      const data = await api('/api/cache/audio');
      this.audioCacheInfo = data;
      this.paintAudioCache();
    } catch { this.audioCacheInfo = {unavailable:true}; this.paintAudioCache(); }
  },

  paintAudioCache() {
    const node = $('audioCacheState'), data = this.audioCacheInfo;
    if (!node || !data) return;
    node.textContent = data.unavailable ? t('Unavailable') : data.tracks
      ? `${data.tracks} ${t('tracks')} · ${data.mb} ${t('MB on disk')}`
      : t('No cached audio');
  },

  /* Подпись движка YouTube: бинарник ставится и обновляется сам, поэтому
     здесь важнее показать, что делает фоновая задача, а не звать нажимать. */
  ytdlpLine(bin) {
    const tag = bin.tag ? ' · ' + bin.tag : '';
    if (bin.busy || (bin.stage === 'downloading' && !bin.ready)) {
      return t('Downloading yt-dlp in the background…');
    }
    if (bin.stage === 'offline') {
      return bin.ready
        ? t('No connection: yt-dlp will update itself later') + tag
        : t('No connection: yt-dlp will be downloaded automatically');
    }
    if (!bin.ready) return bin.error || t('yt-dlp is not installed yet');
    if (bin.rolled_back) return t('The update was rolled back, the previous yt-dlp is in use') + tag;
    return t('yt-dlp installs and updates itself') + tag;
  },

  /* Настройки караоке применяются на месте: без перезагрузки текста. */
  applyKaraoke() {
    S.karaokeTiming = 'line'; S.discSync = 'line';
    if (S.karaokeMode === 'viz') { S.karaokeMode = 'split'; saveSettings(); }
    const mode = S.karaokeMode || 'split';
    const now = $('now');
    if (now) {
      now.classList.toggle('album-flow23',['aurora','albumflow'].includes(S.karaokeStyle)&&!!S.karaokeBg&&mode!=='disc'&&!S.vbgOn);
      now.classList.toggle('flow-still23',!!S.noAnim||!Karaoke.playing);
      now.classList.toggle('focus', mode !== 'split');
      now.classList.toggle('cinema', mode === 'cinema');
      now.classList.toggle('disc', mode === 'disc');
      now.classList.remove('viz', 'bare', 'awake', 'idle30', 'chrome-hidden38');
      // Тёмная сцена: обложка-подложка уходит, иначе свет пятен не читается.
      now.classList.toggle('stage',
        (S.karaokeStyle || 'aurora') === 'stage' && !!S.karaokeBg && !S.noAnim);
      // Спокойная сцена: обложка, текст и транспорт остаются.
      now.classList.add('noctl');
      this.mountSceneReturn(now);
      if (!S.karaokeBare) now.classList.remove('awake');
      this.bindBareWake(now);
    }
    Disc.setMode(mode === 'disc');
    if (typeof Viz !== 'undefined') Viz.setMode(false);
    if (mode === 'disc') Karaoke.stop(); else if (Karaoke.playing) Karaoke.start();
    const focus = $('nFocus');
    if (focus) { focus.classList.toggle('on', mode === 'focus'); focus.setAttribute('aria-pressed', String(mode === 'focus')); }
    Karaoke.applyStyle();
    if (Karaoke.lines.length) Karaoke.render();
    if (Karaoke.synced && Player.audio) Karaoke.resync();
    if (!Karaoke.lines.length && typeof Workspace!=='undefined' && Workspace.ready) Workspace.nowOpen();
  },

  mountSceneReturn() { $('sceneReturn')?.remove(); },

  setPlayerControls(visible) {
    // Eye hide/restore chrome toggle removed; keep controls always visible.
    S.playerControls = true;
    $('now')?.classList.remove('chrome-hidden38');
    Repair33.mode();
    saveSettings();
    document.querySelectorAll('[data-sw="playerControls"]').forEach(n => n.classList.toggle('on', true));
  },

  /* Пробуждение кнопок в режиме «только караоке». Таймер один на окно:
     обработчик ставим единожды, иначе каждый вызов applyKaraoke() добавлял
     бы ещё один и кнопки начинали мигать. */
  bindBareWake(now) {
    if (this._bareBound) return;
    this._bareBound = true;
    let idle = null;
    const wake = () => {
      if (!now.classList.contains('bare') || now.classList.contains('noctl')) return;
      now.classList.add('awake');
      clearTimeout(idle);
      idle = setTimeout(() => now.classList.remove('awake'), 2500);
    };
    now.addEventListener('pointermove', wake, { passive: true });
    now.addEventListener('pointerdown', wake, { passive: true });
    now.addEventListener('dblclick', e=>{
      if (!now.classList.contains('noctl')) return;
      e.preventDefault();e.stopPropagation();this.setPlayerControls(true);
    },true);
  },

  async checkHealth() {
    try {
      const data = await api('/api/health');
      K.health = data;
      this.buildLibraries();
      this.refreshAudioCache();
      $('srcState').textContent = data.ytdlp
        ? t('Ready')
        : t('Libraries unavailable');
      const ytState = $('ytdlpState');
      if (ytState) ytState.textContent = this.ytdlpLine(data.ytdlp_binary || {});
      // Состояние cookies приезжает тем же ответом — второй запрос не нужен.
      if (typeof YTCookies !== 'undefined' && data.youtube_cookies) {
        YTCookies.state = data.youtube_cookies;
        YTCookies.paint();
      }
      $('aboutBox').textContent = `Kryo ${data.version || ""}`
        + ` · ${data.stats?.db ?? "—"}`;
      const grid = $('statGrid');
      const stats = data.stats || {};
      grid.innerHTML = '';
      [[t('Plays'), stats.plays], [t('Unique tracks'), stats.tracks],
       [t('Liked'), stats.likes], [t('Playlists'), stats.playlists],
       [t('Artists in taste'), stats.artists], [t('Hours of music'), stats.hours]]
        .forEach(([label, value]) => {
          grid.appendChild(el('div', 'stat', `<b>${value ?? "—"}</b><span>${label}</span>`));
        });
    } catch {
      $('srcState').textContent = t('Server is not responding');
      this.buildLibraries();
    }
  },

  /* ---------------------------------------------------------------- связки */
  /* Поиск по настройкам.

     Панелей шестнадцать, и найти нужный переключатель можно было, только
     помня, в какой он вкладке. Поиск складывает все панели в один список и
     оставляет те строки, где встретилось слово, — вместе с заголовком их
     раздела, чтобы было понятно, откуда строка. Пустой запрос возвращает
     обычный вид вкладок. */
  bindSettingsSearch() {
    InterfaceV6.bindSettingsSearch();
  },

  bind() {
    document.querySelectorAll('[data-nav]').forEach(btn =>
      btn.onclick = () => this.go(btn.dataset.nav));
    document.querySelectorAll('[data-back]').forEach(btn => btn.onclick = () => this.back());
    document.querySelectorAll('[data-close]').forEach(btn => btn.onclick = () => closeModals());

    // поиск
    const input = $('q');
    input.addEventListener('input', () => {
      $('qClear').style.display = input.value.trim() ? '' : 'none';
      if ((this.searchController || this.moreController) && input.value.trim() !== K.search.query) this.cancelSearch();
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') this.search(input.value);
      else if (event.key === 'Escape') input.blur();
    });
    $('qClear').onclick = () => {
      input.value = ''; $('qClear').style.display = 'none'; this.cancelSearch(); input.focus();
    };
    // История поиска и подсказки живут отдельным модулем (hints.js).
    if (typeof Hints !== 'undefined') Hints.bind();
    document.addEventListener('click', event => {
      if (menuJustOpened()) return;
      if (!event.target.closest('.menu') && !event.target.closest('.pop')) hideMenu();
    });

    $('bMore').onclick = () => this.more();
    $('scroll').addEventListener('scroll', () => {
      const box = $('scroll');
      if (K.view !== 'search' || !K.search.more || K.search.loading) return;
      // Полки альбомов и исполнителей теперь над треками, поэтому треки
      // догружаются сами при прокрутке (на вкладках «Все» и «Треки»).
      if (!['all', 'tracks'].includes(this.searchTab || 'all')) return;
      if (box.scrollTop + box.clientHeight > box.scrollHeight - 600) this.more();
    }, { passive: true });

    // главная
    $('bMix').onclick = () => this.playMix();
    $('bRadio').onclick = () => this.startRadio(Player.current);
    $('bRefresh').onclick = () => {
      dropCache('/api/recommend');
      if (typeof Home31 !== 'undefined' && Home31.ready) Home31.load(true);
      else Views.renderHome(true);
      toast(t('Refreshing picks'));
    };

    // автор
    $('aPlay').onclick = () => Player.playList(this.authorTracks, false);
    $('aShuffle').onclick = () => Player.playList(this.authorTracks, true);
    $('aRadio').onclick = () => this.startRadio((this.authorTracks || [])[0]);
    // Аватарка автора: кнопка в ряду действий и правый щелчок по фото.
    const saveAvatar = () => saveCover(this.authorPicture, this.authorName, 'Avatar');
    if ($('aSavePic')) $('aSavePic').onclick = saveAvatar;
    $('aPic').oncontextmenu = event => {
      if (!this.authorPicture) return;
      event.preventDefault();
      showMenu(event.clientX, event.clientY, [
        { label: t('Download avatar'), icon: 'image', action: saveAvatar }]);
    };

    // списки
    $('lPlay').onclick = () => Player.playList(this.listTracks, false);
    $('lShuffle').onclick = () => Player.playList(this.listTracks, true);
    $('lMenu').onclick = event => {
      const state = Views.listState || {};
      const items = [
        { label: t('Shuffle play'), icon: 'shuffle',
          action: () => Player.playList(this.listTracks, true) },
        { label: t('Add to queue'), icon: 'queue',
          action: () => { (this.listTracks || []).forEach(t => Player.queue.push(t));
                          Views.renderQueue(); toast(t('Added to the queue')); } },
      ];
      if (state.type === 'playlist') {
        items.push({ label: t('Share the playlist'), icon: 'link',
          action: () => this.sharePlaylist(state.id, state.name) });
        items.push('-', { label: t('Delete playlist'), icon: 'trash', danger: true,
          action: () => this.deletePlaylist(state.id) });
      }
      // Обложка альбома или плейлиста — одной кнопкой на диск.
      let cover = state.cover || '';
      if (!cover && state.type === 'playlist') {
        const own = (K.playlists || []).find(p => String(p.id) === String(state.id));
        cover = own && own.cover || '';
      }
      if (cover) {
        const title = $('lName').textContent || state.name || '';
        items.push('-', { label: t('Save cover artwork as…'), icon: 'image',
          action: () => saveCover(cover, [state.artist, title].filter(Boolean).join(' — ')) });
      }
      if (state.type === 'liked' || state.type === 'mix' || state.type === 'history') {
        // Любой открытый список тоже можно отдать другу — как разовый код.
        items.push({ label: t('Share the playlist'), icon: 'link',
          action: () => this.shareTracks($('lName').textContent, this.listTracks) });
      }
      if (state.type === 'history') {
        items.push('-', { label: t('Clear history'), icon: 'trash', danger: true,
          action: async () => { await api('/api/history', { method: 'DELETE' });
                                Studio.counts.clear(); Studio.refreshVisible(); this.openHistory(); toast(t('History cleared')); } });
      }
      showMenu(event.clientX, event.clientY, items);
    };

    // медиатека
    $('bNewPl').onclick = () => { $('newPlName').value = ''; openModal('mNewPl'); };
    const importBtn = $('bImportPl');
    if (importBtn) {
      importBtn.onclick = () => { $('importCode').value = ''; openModal('mImportPl'); };
    }
    const pick = $('importPick');
    if (pick) pick.onclick = () => $('importFile').click();
    const file = $('importFile');
    if (file) {
      file.onchange = async () => {
        const chosen = file.files && file.files[0];
        if (!chosen) return;
        $('importCode').value = (await chosen.text()).trim();
        file.value = '';
      };
    }
    const importOk = $('importOk');
    if (importOk) importOk.onclick = () => this.importPlaylist($('importCode').value);
    const ipOk = $('ipOk');
    if (ipOk) ipOk.onclick = () => this.runImportPick();
    const ipAll = $('ipAll');
    if (ipAll) ipAll.onclick = () => {
      this.ipPicked = new Set(this.ipTracks.map((_, i) => i));
      this.renderImportTracks();
    };
    const ipNone = $('ipNone');
    if (ipNone) ipNone.onclick = () => { this.ipPicked = new Set(); this.renderImportTracks(); };
    const copy = $('shareCopy');
    if (copy) {
      copy.onclick = async () => {
        const code = $('shareCode').value;
        try { await navigator.clipboard.writeText(code); }
        catch { $('shareCode').select(); document.execCommand('copy'); }
        toast(t('Code copied — send it to a friend'));
      };
    }
    const saveFile = $('shareFile');
    if (saveFile) saveFile.onclick = () => this.saveShareFile();
    $('newPlOk').onclick = async () => {
      const name = $('newPlName').value.trim();
      if (!name) { toast(t('Enter a name')); return; }
      const playlist = await api('/api/playlists', { method: 'POST', body: { name } });
      closeModals();
      await refreshPlaylists();
      Views.renderLibrary();
      if (this.addTrack) {
        await api(`/api/playlists/${playlist.id}/tracks`, { method: 'POST', body: { track: this.addTrack } });
        this.addTrack = null;
        refreshPlaylists();
      }
      toast(t('Playlist created') + ': ' + name);
    };

    // плеер
    const bindAll = (ids, handler) => ids.forEach(id => { const n = $(id); if (n) n.onclick = handler; });
    bindAll(['pPlay', 'nPlay', 'pMobPlay'], () => Player.toggle());
    bindAll(['pNext', 'nNext', 'pNextM'], () => Player.next(false));
    bindAll(['pPrev', 'nPrev', 'pPrevM'], () => Player.prev());
    bindAll(['pShuffle', 'nShuffle', 'pShuffleM'], () => {
      S.shuffle = !S.shuffle;
      saveSettings();
      // Включили — мешаем то, что играет; выключили — возвращаем исходный
      // порядок. Дальше режим живёт сам: каждая новая очередь собирается
      // с учётом перемешки (Player.queueFrom).
      if (Player.queue.length > 1) {
        if (S.shuffle) Player.reshuffle();
        else Player.unshuffle();
        Player.saveState();
        Views.renderQueue();
      }
      Player.paintState();
      Player.prefetchNext();
      toast(S.shuffle ? t('Shuffled') : t('Normal order'));
    });
    bindAll(['pRepeat', 'nRepeat'], () => {
      S.repeat = S.repeat === 'off' ? 'all' : S.repeat === 'all' ? 'one' : 'off';
      saveSettings();
      Player.paintState();
      Player.prefetchNext();
      toast({ off: t('Repeat off'), all: t('Repeat queue'), one: t('Repeat track') }[S.repeat]);
    });
    bindAll(['pLike', 'nLike', 'pLikeM'], () => Player.current && toggleLike(Player.current));
    bindAll(['pAdd', 'nAdd'], () => Player.current && this.openAddTo(Player.current));
    bindAll(['pQueue', 'nQueue'], () => {
      const on = $('queue').classList.toggle('on');
      $('veil').classList.toggle('on', on);
      Views.renderQueue(on);
    });
    $('queueClose').onclick = () => closeModals();
    const queueClear = $('queueClear');
    if (queueClear) {
      queueClear.onclick = () => {
        if (!Player.queue.length) { toast(t('The queue is empty')); return; }
        Player.clearQueue();
        toast(t('Queue cleared'));
      };
    }
    $('veil').onclick = () => closeModals();

    const openMixer = $('sOpenMixer');
    if (openMixer) openMixer.onclick = () => Mixer.open();
    const bal = $('sBal');
    if (bal) {
      bal.oninput = () => { Player.setBalance(bal.value / 100); this.paintBalance(); };
      bal.ondblclick = () => { Player.setBalance(0); this.syncSettingsUI(); };
    }
    const balCenter = $('sBalCenter');
    if (balCenter) balCenter.onclick = () => { Player.setBalance(0); this.syncSettingsUI(); };

    $('vol').oninput = event => Player.setVolume(+event.target.value);
    $('pMute').onclick = () => {
      const next = Player.audio.volume > 0 ? 0 : (S.lastVolume || 100);
      if (Player.audio.volume > 0) S.lastVolume = S.volume;
      $('vol').value = next;
      Player.setVolume(next);
    };
    // полноэкранный плеер
    $('pInfo').onclick = event => {
      if (event.target.closest('#pArtist') && Player.current) {
        event.stopPropagation();
        this.openAuthor(Player.current.artist, Player.current.author_url,
                        Player.current.source);
        return;
      }
      this.openNow();
    };
    // Имя исполнителя на большом экране плеера — тоже ссылка.
    const nArtist = $('nArtist');
    if (nArtist) {
      nArtist.classList.add('ar-btn', 'ar-wide');
      nArtist.setAttribute('role', 'button');
      nArtist.setAttribute('tabindex', '0');
      nArtist.title = t('Open artist');
      const open = () => {
        const track = Player.current;
        if (track) this.openAuthor(track.artist, track.author_url, track.source);
      };
      nArtist.onclick = open;
      nArtist.onkeydown = event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
      };
    }
    // Имя исполнителя в нижней полосе — тоже видимая кнопка. Класс ставит
    // Player.paintTrack: пока ничего не играет, там подсказка «выберите
    // трек», и кнопкой она быть не должна.
    const pArtist = $('pArtist');
    if (pArtist) {
      pArtist.setAttribute('role', 'button');
      pArtist.title = t('Open artist');
    }
    // бейдж источника открывает выбор источника, не полноэкранный плеер
    const badge = $('pSource');
    if (badge) {
      badge.onclick = event => {
        event.stopPropagation();
        if (Player.current) Streams.open(Player.current);
      };
    }
    const dur = $('pDur');
    if (dur) {
      dur.onclick = () => {
        Player.showLeft = !Player.showLeft;
        Player.paintTime();
      };
    }
    $('nClose').onclick = () => {
      $('now').classList.remove('on');
      if (!Player.audio.paused) return;
      Karaoke.stop();
    };
    // «Только текст»: обложка уходит, строки занимают весь экран.
    const focus = $('nFocus');
    if (focus) {
      focus.onclick = () => {
        S.karaokeMode = (S.karaokeMode || 'split') === 'split' ? 'focus' : 'split';
        saveSettings();
        this.applyKaraoke();
        Karaoke.center(true);
      };
    }
    // Чистая сцена для записи: текст остаётся, весь служебный интерфейс скрыт.
    const ctl = $('nCtl');
    if (ctl) {
      ctl.onclick = () => {
        this.setPlayerControls(S.playerControls === false);
      };
    }
    const sync = (id, fn) => { const node = $(id); if (node) node.onclick = fn; };
    sync('nSyncBack', event => Karaoke.nudge(event && event.shiftKey ? -0.5 : -0.1));
    sync('nSyncFwd', event => Karaoke.nudge(event && event.shiftKey ? 0.5 : 0.1));
    sync('nSyncVal', () => Karaoke.resetOffset());
    sync('nSyncTap', () => Karaoke.tap());
    $('nLyrics').onclick = () => {
      dropCache('/api/lyrics');
      Karaoke.fetchLyrics(Player.current);
      toast(t('Looking for lyrics again'));
    };

    // настройки
    const openSettings = () => { this.checkHealth(); Plugins.load(); openModal('mSettings'); };
    // Панели настроек закрываются вместе с окном — фоновые опросы не тикают зря.
    $('setClose').addEventListener('click', () => Logs.stop());
    $('bSettings').onclick = openSettings;
    $('navSettings').onclick = openSettings;
    $('mobSettings').onclick = openSettings;
    $('setClose').onclick = () => closeModals();
    $('setTabs').onclick = event => {
      const chip = event.target.closest('[data-pane]');
      if (!chip) return;
      this.openPane(chip.dataset.pane);
    };

    document.querySelectorAll('[data-sw]').forEach(node => {
      node.onclick = event => {
        event.stopPropagation();
        const key = node.dataset.sw;
        S[key] = !S[key];
        if(key==='rail'&&typeof Workspace!=='undefined')Workspace.update({sidebarCollapsed:S.rail});
        document.querySelectorAll(`[data-sw="${key}"]`)
          .forEach(other => other.classList.toggle('on', S[key]));
        saveSettings();
        applyTheme();
        if(['karaokeBg','noAnim','vbgOn'].includes(key))this.applyKaraoke();
        if (key === 'normalize') { Player.ensureCtx(); Player.rebuild(); }
        if (key === 'miniPlayer') MiniPlayer.apply();
        if (key === 'kCoverOn') KCustom.repaint();
        if (key === 'autoLyrics' && Player.current) Karaoke.onTrack(Player.current);
        if (key === 'lyricsFit' && Karaoke.synced) Karaoke.resync();
        if (key === 'lyricsAutoSync' && !S.lyricsAutoSync) {
          if (typeof KFit42 !== 'undefined') KFit42.cancel();
          Karaoke.auto = null;
        }
        if (key === 'kbScene') KCustom.apply();
        if (key === 'vbgOn') {
          if (S.vbgOn && !VMedia.cfgBg()) {
            S.vbgOn = false; saveSettings();
            document.querySelectorAll('[data-sw="vbgOn"]').forEach(n => n.classList.remove('on'));
            toast(t('Choose a video first'));
          } else VMedia.applyBg();
        }
        if (key === 'karaokeBg') { S.karaokeBg ? Karaoke.start() : Karaoke.stop(); }
        if (key === 'noAnim') { S.noAnim ? Karaoke.stop() : Karaoke.start(); Atmo.kick(); }
        if (key === 'atmo') Atmo.apply();
        if (key === 'playerControls') this.setPlayerControls(S.playerControls);
        else if (key === 'karaokeDim' || key === 'karaokeDots' || key === 'karaokeBare') this.applyKaraoke();
        if (key.startsWith('disc')) Disc.apply();
        if (key.startsWith('viz')) Viz.recolor();
        if (key.startsWith('sketch')) Sketch.build();
        if (key.startsWith('win')) Frame.applySettings();
      };
    });

    // Привязка окна к половинам экрана прямо из настроек.
    document.querySelectorAll('[data-snap]').forEach(node => {
      node.onclick = () => (node.dataset.snap === 'full'
        ? Frame.toggleMax() : Frame.snap(node.dataset.snap));
    });

    const onRange = (id, key, after) => {
      const node = $(id);
      if (!node) return;
      node.oninput = event => {
        const float = FLOAT_SETTINGS.includes(key);
        S[key] = float ? +event.target.value : Math.round(+event.target.value);
        saveSettings();
        applyTheme();
        this.syncSettingsUI();
        if (after) after();
      };
    };
    onRange('sRadius', 'radius');
    // Чувствительность к музыке общая для всех сцен: обновляем ту, что открыта.
    onRange('sReactSense', 'reactSense', () => {
      Karaoke.beat = 0; Karaoke.bassAvg = null; Karaoke._lv = null;
      if (typeof Disc !== 'undefined') { Disc._energy = Disc._beat = null; Disc.apply(); }
      if (typeof Viz !== 'undefined' && Viz.apply) Viz.apply();
    });
    onRange('sFade', 'fade');
    onRange('sLyricsOffset', 'lyricsOffset', () => Karaoke.resync());
    onRange('sVolume', 'volume', () => Player.setVolume(S.volume));
    // Сцена «Диска»: размеры, скорость вращения и тайминг слов.
    [['sDiscSize', 'discSize'], ['sDiscTextSize', 'discTextSize'],
     ['sDiscSpinSpeed', 'discSpinSpeed'], ['sDiscLines', 'discLines'],
     ['sDiscLead', 'discLead'], ['sDiscHold', 'discHold'],
     ['sDiscLinger', 'discLinger']]
      .forEach(([id, key]) => onRange(id, key, () => Disc.apply()));

    $('sLimit').onchange = event => { S.limit = +event.target.value; saveSettings(); dropCache('/api/search'); };
    // Срок жизни готовой ссылки и число попыток добора источника.
    $('sStreamExpiry').onchange = event => {
      S.streamExpiryMs = +event.target.value; saveSettings();
      api('/api/streams', { method: 'DELETE' }).catch(() => {});
    };
    $('sStreamRetries').onchange = event => {
      S.streamResolutionRetries = +event.target.value; saveSettings();
    };
    ['cAccent', 'cAccent2', 'cBg'].forEach(id => {
      $(id).oninput = event => {
        S[{ cAccent: 'accent', cAccent2: 'accent2', cBg: 'bg' }[id]] = event.target.value;
        S.theme = 'custom';
        applyTheme();
        saveSettings();
      };
    });

    $('bCheck').onclick = () => { this.checkHealth(); toast(t('Checking libraries')); };

    // Движок YouTube: официальный бинарник yt-dlp. Кнопка
    // проверяет и подтягивает свежую сборку — именно она чинит источник,
    // когда YouTube в очередной раз меняет плеер.
    const ytdlp = $('bYtdlp');
    if (ytdlp) ytdlp.onclick = async () => {
      ytdlp.disabled = true;
      const state = $('ytdlpState');
      if (state) state.textContent = t('Checking for a newer yt-dlp…');
      try {
        const data = await api('/api/youtube/update', { method: 'POST' });
        if (state) {
          state.textContent = (data.ok ? t('yt-dlp is up to date') : t('yt-dlp could not be updated'))
            + (data.version ? ' · ' + data.version : '');
        }
        // Дальше подпись снова возьмёт на себя фоновая задача.
        setTimeout(() => this.checkHealth(), 4000);
        toast(data.ok ? t('yt-dlp is up to date') : t('yt-dlp could not be updated'));
        dropCache('/api/search');
      } catch (err) {
        if (state) state.textContent = err.message || t('Error');
        toast(err.message || t('Error'));
      } finally {
        ytdlp.disabled = false;
      }
    };
    $('bClearAudio').onclick = async () => {
      await api('/api/cache/audio', { method: 'DELETE' });
      toast(t('Cache cleared'));
      this.refreshAudioCache();
    };
    $('bClearCache').onclick = async () => {
      await api('/api/cache/clear', { method: 'POST' });
      dropCache();
      toast(t('Cache cleared'));
    };
    $('bClearHistory').onclick = async () => {
      await api('/api/history', { method: 'DELETE' });
      dropCache();
      this.checkHealth();
      toast(t('History and taste reset'));
    };
    $('bClearSearch').onclick = async () => {
      await api('/api/searches', { method: 'DELETE' });
      toast(t('Search history cleared'));
    };
    $('bResetSettings').onclick = async () => {
      // Only reset the local UI once the database accepted the deletion.
      await api('/api/settings', { method: 'DELETE' });
      S = structuredClone(DEFAULTS);
      localStorage.removeItem('kryonyx');
      applyTheme();
      this.buildSettings();
      this.buildLibraries();
      this.syncSettingsUI();
      Themes.build(); Sketch.build(); Wall.build(); Look.build(); Tune.build();
      Frame.applySettings();
      Plugins.load(true);
      Workspace.apply(); Studio.apply(); saveSettings(true);
      toast(t('Settings reset'));
    };

    $('bFull').onclick = () => this.fullscreen();

    // горячие клавиши
    addEventListener('keydown', event => {
      const key = event.key.toLowerCase();
      const now=$('now'),editing=event.target.matches('input,textarea,select,[contenteditable=true]');
      if (now.classList.contains('on') && !editing && !event.ctrlKey && !event.metaKey && !event.altKey
          && (key==='h'||key==='р'||(key==='escape'&&S.playerControls===false))) {
        event.preventDefault();event.stopImmediatePropagation();
        this.setPlayerControls(key==='escape'||S.playerControls===false);return;
      }
      // Escape закрывает окно и из поля ввода: в модалке переноса курсор
      // сразу стоит в поле ссылки, и окно иначе не закрыть с клавиатуры.
      if (key === 'escape' && !event.target.closest('#searchWrap')) {
        if (event.target.matches('input, textarea, select')) event.target.blur();
        closeModals();
        $('now').classList.remove('on');
        return;
      }
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.target.matches('input, textarea, select') || event.target.closest('button, [role=button], .modal, #queue')) return;
      // Экран клипов живёт своими клавишами: пробел там ставит на паузу клип,
      // а не музыку за ним.
      if ($('clips') && $('clips').classList.contains('on')) return;
      if (key === ' ') { event.preventDefault(); Player.toggle(); }
      else if (key === 'arrowright' && event.shiftKey) Player.next(false);
      else if (key === 'arrowleft' && event.shiftKey) Player.prev();
      else if (key === 'arrowright') Player.audio.currentTime += 5;
      else if (key === 'arrowleft') Player.audio.currentTime -= 5;
      else if (key === 'arrowup') { $('vol').value = Math.min(100, S.volume + 5); Player.setVolume(+$('vol').value); }
      else if (key === 'arrowdown') { $('vol').value = Math.max(0, S.volume - 5); Player.setVolume(+$('vol').value); }
      else if (key === 'l') Player.current && toggleLike(Player.current);
      else if (key === 'q') $('pQueue').click();
      else if (key === 's') $('pShuffle').click();
      else if (key === 'r') $('pRepeat').click();
      else if (key === 'f') this.openNow();
      else if (key === 'm' || key === 'ь') Mixer.open();
      else if (key === 't' || key === 'е') Karaoke.tap();
      else if (key === '[' || key === 'х') Karaoke.nudge(-0.1);
      else if (key === ']' || key === 'ъ') Karaoke.nudge(0.1);
      else if (key === '/') { event.preventDefault(); if(K.view === 'home' && $('homeQuery')) $('homeQuery').focus(); else { this.go('search'); $('q').focus(); } }
      else if (key === 'escape') { closeModals(); $('now').classList.remove('on'); }
      else if (event.key === 'F11') { event.preventDefault(); this.fullscreen(); }
    });

    // свайп вниз закрывает полноэкранный плеер (телефон)
    let touchY = 0;
    $('now').addEventListener('touchstart', e => { touchY = e.touches[0].clientY; }, { passive: true });
    $('now').addEventListener('touchend', e => {
      if (e.changedTouches[0].clientY - touchY > 110) $('now').classList.remove('on');
    }, { passive: true });
  },

  openNow() {
    if (!Player.current) { toast(t('Pick a track first')); return; }
    $('now').classList.add('on');
    Karaoke.resize();
    Karaoke.start();
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.nowOpen();
  },

  fullscreen() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.toggle_fullscreen) {
      window.pywebview.api.toggle_fullscreen().then((state) => {
        // В полном экране своя полоса заголовка не нужна.
        if (window.Frame) window.Frame.setFullscreen(state);
      }).catch(() => {});
      return;
    }
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  },
};

addEventListener('DOMContentLoaded', () => {
  App.bootReady = App.boot();
  App.bootReady.then(() => {
    requestAnimationFrame(() => { document.documentElement.classList.remove('booting45'); $('boot45')?.remove(); });
  }).catch((err) => {
    console.error('[boot] failed', err);
    if($('bootStatus45'))$('bootStatus45').textContent=t('Some parts did not load');
    if($('bootRetry45')){$('bootRetry45').hidden=false;$('bootRetry45').textContent=t('Retry');}
    try { toast('Kryo: ' + (err && err.message || err)); } catch {}
  });
});
