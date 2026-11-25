/* views.js — отрисовка экранов: главная, поиск, автор, медиатека, списки. */
'use strict';

/* Кнопка исполнителя. Раньше имя было просто текстом с невидимым
   обработчиком: угадать, что по нему можно нажать, было нельзя. Теперь это
   настоящая кнопка — с иконкой, рамкой по наведению и фокусом с клавиатуры.
   Внутри строки трека лежит <button>, поэтому вложить ещё одну нельзя:
   используем span с ролью кнопки — браузер и программы чтения с экрана
   считают его кнопкой. */
function artistBtn(track) {
  const name = esc(track.artist || '');
  if (!name) return '';
  const multi = typeof MusicMeta9 !== 'undefined' && MusicMeta9.artists(track).length > 1;
  const label = multi ? t('Choose artist') : t('Open artist');
  return `<span class="ar-btn" data-act="artist" role="button" tabindex="0"` +
    ` data-i18n-artist="${multi ? 'Choose artist' : 'Open artist'}" title="${esc(label)}" aria-label="${esc(label + ': ' + (track.artist || ''))}">${icon('user', 'ic xs')}` +
    `<span class="ar-n">${name}</span>${multi ? icon('down', 'ic xs') : ''}</span>`;
}

/* Enter и пробел на кнопке исполнителя работают как щелчок. */
function bindArtistKeys(root, track) {
  const node = root.querySelector('.ar-btn');
  if (!node) return;
  node.addEventListener('keydown', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    event.stopPropagation();
    App.openTrackArtists(track);
  });
}

const Views = {
  context: [],     // текущий список для «играть дальше»
  listState: null,

  /* ------------------------------------------------------- строка трека

     opts позволяет переиспользовать строку в очереди и в других панелях:
       onPlay   — что делать по клику по самой строке;
       onRemove — показать крестик и вызвать это по нажатию.
     Раньше вызывающий код просто перезаписывал row.onclick целиком, и
     вместе с ним терялись кнопки «лайк», «в плейлист» и «⋯» — именно
     поэтому в панели очереди они ничего не делали. */
  trackRow(track, index, list, opts = {}) {
    const row = el('div', 'tr');
    row.setAttribute('role', 'group');
    row.setAttribute('aria-label', track.title || t('Track'));
    row.style.animationDelay = Math.min(index * 14, 320) + 'ms';
    row.dataset.id = track.id;
    row.innerHTML = `
      <span class="n">${index + 1}</span>
      <img alt="">
      <span class="meta">
        <button class="t clip workspace-track-title" data-act="play" title="${esc(t("Play"))}">${esc(track.title)}</button>
        <span class="a clip">${artistBtn(track)} · ${sourceName(track.source)}</span>
      </span>
      ${Studio.stats(track)}
      <span class="d">${fmt(track.duration)}</span>
      <span class="acts">
        <button class="ib" type="button" data-act="like" data-like="${esc(track.id)}"
              title="${esc(t('Like'))}">${icon('heart', 'ic s')}</button>
        <button class="ib" type="button" data-act="add" title="${esc(t('Add to playlist'))}">${icon('plus', 'ic s')}</button>
        ${opts.onRemove ? `<button class="ib" type="button" data-act="drop"
              title="${esc(t('Remove from the queue'))}">${icon('close', 'ic s')}</button>` : ''}
        <button class="ib" type="button" data-act="more" title="${esc(t('More'))}">${icon('dots', 'ic s')}</button>
      </span>`;
    setImg(row.querySelector('img'), track.thumbnail, 56);
    if (K.likes.has(track.id)) {
      const like = row.querySelector('[data-act=like]');
      like.classList.add('on');
      like.querySelector('.ic').classList.add('f');
    }
    row.onclick = event => {
      const act = event.target.closest('[data-act]');
      if (!act) {
        if (opts.onPlay) opts.onPlay();
        else Player.play(track, list);
        return;
      }
      event.stopPropagation();
      const name = act.dataset.act;
      if (name === 'play') { if (opts.onPlay) opts.onPlay(); else Player.play(track, list); }
      else if (name === 'like') toggleLike(track);
      else if (name === 'add') App.openAddTo(track);
      else if (name === 'drop') opts.onRemove();
      else if (name === 'artist')
        App.openTrackArtists(track);
      else this.trackMenu(event, track, list, opts);
    };
    row.oncontextmenu = event => {
      event.preventDefault();
      this.trackMenu(event, track, list, opts);
    };
    bindArtistKeys(row, track);
    Studio.queueStats(track.id);
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.enhanceTrackRow(row, track, index, opts);
    return row;
  },

  trackMenu(event, track, list, opts = {}) {
    const items = [
      { label: t('Play'), icon: 'play', action: () => Player.play(track, list) },
      { label: t('Play next'), icon: 'next', action: () => Player.addNext(track) },
      { label: t('Add to end of queue'), icon: 'queue', action: () => Player.addLast(track) },
      '-',
      { label: K.likes.has(track.id) ? t('Unlike') : t('Like'),
        icon: 'heart', action: () => toggleLike(track) },
      { label: t('Add to playlist'), icon: 'plus', action: () => App.openAddTo(track) },
      { label: t('Share audio file'), icon: 'share64', action: () => Share64.open(track) },
      '-',
      { label: t('Radio from this track'), icon: 'radio', action: () => App.startRadio(track) },
      { label: t('Change source'), icon: 'lib', action: () => Streams.open(track) },
      { label: t('Open artist'), icon: 'user',
        action: () => App.openTrackArtists(track) },
    ];
    if (track.thumbnail) {
      items.push({ label: t('Save cover artwork as…'), icon: 'image',
        action: () => saveCover(track.thumbnail,
          [track.artist, track.title].filter(Boolean).join(' — ')) });
    }
    if (opts.onRemove) {
      items.push('-', { label: t('Remove from the queue'), icon: 'close',
                        danger: true, action: () => opts.onRemove() });
    }
    if (!opts.onRemove && this.listState && this.listState.type === 'playlist' && track.row_id) {
      items.push('-', {
        label: t('Remove from playlist'), icon: 'trash', danger: true,
        action: async () => {
          await api(`/api/playlists/${this.listState.id}/tracks/${track.row_id}`, { method: 'DELETE' });
          App.openPlaylist(this.listState.id, this.listState.name);
          refreshPlaylists();
        },
      });
    }
    showMenu(event.clientX, event.clientY, items);
  },

  /* Длинные списки собираются порциями по кадрам — окно не подвисает
     даже на плейлисте в тысячу треков. */
  renderTracks(box, list, { append = false, chunk = 80 } = {}) {
    if (!append) box.innerHTML = '';
    const offset = append ? box.children.length : 0;
    if (this._chunkTimer) { cancelAnimationFrame(this._chunkTimer); this._chunkTimer = null; }

    const paint = (from) => {
      const frag = document.createDocumentFragment();
      const to = Math.min(from + chunk, list.length);
      for (let i = from; i < to; i++) frag.appendChild(this.trackRow(list[i], offset + i, list));
      box.appendChild(frag);
      if (to < list.length) {
        this._chunkTimer = requestAnimationFrame(() => paint(to));
      } else {
        this._chunkTimer = null;
        this.markPlaying();
      }
    };
    paint(0);
    this.markPlaying();
  },

  /* -------------------------------------------------------------- карточки */
  trackCard(track, list, options = {}) {
    const card = el('button', 'card');
    card.dataset.id = track.id;
    card.innerHTML = `
      <span class="art">
        <img alt="">
        <span class="badge ${sourceTag(track.source)}">${sourceName(track.source)}</span>
        <span class="play-fab">${icon('play', 'ic s f')}</span>
      </span>
      <span class="t clip">${esc(track.title)}</span>
      <span class="a clip">${artistBtn(track)}</span>
      ${options.stats === false ? '' : Studio.stats(track)}`;
    setImg(card.querySelector('img'), track.thumbnail, 240);
    card.onclick = event => {
      // Клик по имени исполнителя уводит на его страницу, а не запускает трек.
      if (event.target.closest('[data-act=artist]')) {
        event.stopPropagation();
        App.openTrackArtists(track);
        return;
      }
      Player.play(track, list);
    };
    card.oncontextmenu = event => { event.preventDefault(); this.trackMenu(event, track, list); };
    bindArtistKeys(card, track);
    if (options.stats !== false) Studio.queueStats(track.id);
    return card;
  },

  authorCard(author) {
    const card = el('button', 'card artist');
    card.innerHTML = `
      <span class="art"><img alt=""></span>
      <span class="t clip">${esc(author.name)}</span>
      <span class="a clip">${author.tracks ? author.tracks + t(' tracks found') : sourceName(author.source)}</span>`;
    setImg(card.querySelector('img'), author.thumbnail);
    card.onclick = () => App.openAuthor(author.name, author.url, author.source);
    card.oncontextmenu = event => {
      event.preventDefault();
      const items = [{ label: t('Open artist'), icon: 'user',
                       action: () => App.openAuthor(author.name, author.url, author.source) }];
      if (author.thumbnail) {
        items.push({ label: t('Download avatar'), icon: 'image',
                     action: () => saveCover(author.thumbnail, author.name, 'Avatar') });
      }
      showMenu(event.clientX, event.clientY, items);
    };
    return card;
  },

  playlistCard(playlist) {
    return this.ownPlaylistCard(playlist);
  },

  /* Карточка альбома или плейлиста из каталога: клик открывает содержимое.
     Кнопка в углу сразу ставит весь релиз в очередь, не открывая список. */
  collectionCard(item) {
    const card = el('button', 'card');
    card.dataset.id = item.id;
    const kind = item.kind === 'album' ? t('Album') : t('Playlist');
    const sub = [item.artist || '', item.year || '',
                 item.count ? item.count + ' ' + t('tracks') : '']
      .filter(Boolean).join(' · ');
    card.innerHTML = `
      <span class="art">
        <img alt="">
        <span class="badge">${esc(kind)}</span>
        <span class="play-fab">${icon('play', 'ic s f')}</span>
      </span>
      <span class="t clip">${esc(item.title || '')}</span>
      <span class="a clip">${esc(sub)}</span>`;
    setImg(card.querySelector('img'), item.thumbnail, 240);
    card.onclick = event => {
      if (event.target.closest('.play-fab')) {
        event.stopPropagation();
        App.playCollection(item);
        return;
      }
      App.openCollection(item);
    };
    card.oncontextmenu = event => {
      event.preventDefault();
      showMenu(event.clientX, event.clientY, [
        { label: t('Open'), icon: 'lib', action: () => App.openCollection(item) },
        { label: t('Play'), icon: 'play', action: () => App.playCollection(item) },
        { label: t('Add to queue'), icon: 'queue',
          action: () => App.playCollection(item, { queue: true }) },
        ...(item.thumbnail ? ['-', { label: t('Save cover artwork as…'), icon: 'image',
          action: () => saveCover(item.thumbnail,
            [item.artist, item.title].filter(Boolean).join(' — ')) }] : []),
      ]);
    };
    return card;
  },

  ownPlaylistCard(playlist) {
    const card = el('button', 'card');
    card.innerHTML = `
      <span class="art"><img alt=""><span class="play-fab">${icon('play', 'ic s f')}</span></span>
      <span class="t clip">${esc(plName(playlist.name))}</span>
      <span class="a clip">${playlist.count} ${plural(playlist.count, t('track'), t('tracks'), t('tracks'))}</span>`;
    setImg(card.querySelector('img'), playlist.cover);
    card.onclick = () => App.openPlaylist(playlist.id, playlist.name);
    card.oncontextmenu = event => {
      event.preventDefault();
      showMenu(event.clientX, event.clientY, [
        { label: t('Open'), icon: 'play', action: () => App.openPlaylist(playlist.id, playlist.name) },
        ...(playlist.cover ? [{ label: t('Save cover artwork as…'), icon: 'image',
          action: () => saveCover(playlist.cover, plName(playlist.name)) }] : []),
        { label: t('Delete'), icon: 'trash', danger: true, action: () => App.deletePlaylist(playlist.id) },
      ]);
    };
    return card;
  },

  skeletons(box, count, kind = 'card') {
    box.innerHTML = '';
    for (let i = 0; i < count; i++) {
      const node = el('div', 'skel');
      node.style.height = kind === 'card' ? '214px' : '58px';
      node.style.opacity = Math.max(0.25, 1 - i * 0.08);
      box.appendChild(node);
    }
  },

  /* ------------------------------------------------------------- главная */
  async renderHome(force) {
    // v31 mounts once after the shell boots; do not build hundreds of legacy shelf cards first.
    if (typeof Home31 !== 'undefined') { if (Home31.ready) return Home31.load(!!force); return; }
    const box = $('rows');
    updateGreet();

    if (force) dropCache('/api/recommend');
    if (!box.children.length) {
      box.innerHTML = '';
      for (let i = 0; i < 3; i++) {
        const shelf = el('div', 'shelf');
        shelf.innerHTML = '<div class="skel" style="height:22px;width:220px;margin:26px 0 14px"></div>';
        const strip = el('div', 'strip');
        this.skeletons(strip, 7);
        shelf.appendChild(strip);
        box.appendChild(shelf);
      }
    }

    try {
      const rows = [8,12,16].includes(S.ui8?.recommendRows) ? S.ui8.recommendRows : 12;
      const data = !force && this.recommendSnapshot30?.rows===rows ? this.recommendSnapshot30.data : await cachedApi('/api/recommend?rows='+rows+(force?'&fresh=1':''), force ? 1 : 300000);
      this.recommendSnapshot30={rows,data};
      if (typeof Home31 !== 'undefined' && Home31.ready) { Home31.receive(data); return; }
      if(typeof ExperienceV8!=='undefined')ExperienceV8.recommendStatus(data);
      box.innerHTML = '';
      Studio.homeData = data.rows || [];
      Studio.paintHero(Studio.homeData);
      if (!data.rows || !data.rows.length) {
        box.innerHTML = `<div class="empty">${icon('note')}<div>${t('Nothing to show yet — find your first track and the picks will build themselves')}</div></div>`;
        return;
      }
      data.rows.forEach(row => box.appendChild(this.shelf(row)));
      Studio.layoutShelves();
      this.renderDiscovery(box, force);
    } catch (err) {
      box.innerHTML = `<div class="empty">${icon('note')}<div>${esc(t('Could not build the selections:'))}
        <span data-no-i18n>${esc(err.message)}</span></div></div>`;
    }
  },

  /* Ряд главной: заголовок, кнопка «Слушать» и лента карточек. */
  shelf(row) {
    const shelf = el('div', 'shelf');
    const head = el('div', 'shelf-h');
    Studio.decorateShelf(shelf, row);
    // Заголовок полки приходит шаблоном (title_key + title_args): имя автора
    // или трека подставляется после перевода и само в словарь не попадает.
    // Подпись без шаблона — это имя исполнителя, её не переводим.
    const title = row.title_key ? tf(row.title_key, row.title_args) : t(row.title);
    const sub = row.subtitle_key ? tf(row.subtitle_key, row.subtitle_args) : (row.subtitle || '');
    head.innerHTML = `<h2 data-no-i18n>${esc(title)}</h2>` +
      `<span class="sub"${row.subtitle_key ? '' : ' data-no-i18n'}>${esc(sub)}</span>`;
    const collections = row.kind === 'albums' || row.kind === 'playlists';
    if (!row.unresolved && !collections) {
      const play = el('button', 'chip', t('Play'));
      play.onclick = () => Player.playList(row.items, false);
      head.appendChild(play);
    }
    shelf.appendChild(head);
    const strip = el('div', 'strip');
    row.items.forEach(track => {
      if (collections) strip.appendChild(this.collectionCard(track));
      else strip.appendChild(row.unresolved || !track.id
        ? this.suggestCard(track)
        : this.trackCard(track, row.items));
    });
    shelf.appendChild(strip);
    this.attachStrip(shelf, strip);
    return shelf;
  },

  /* Карточка без готового потока: клик уводит в поиск по названию. */
  suggestCard(track) {
    const card = el('div', 'card');
    const art = el('div', 'art');
    const img = el('img');
    setImg(img, track.thumbnail);
    art.appendChild(img);
    card.appendChild(art);
    card.appendChild(el('span', 't', esc(track.title || '')));
    card.appendChild(el('span', 'a', esc(track.artist || '')));
    card.onclick = () => App.search(`${track.artist || ''} ${track.title || ''}`.trim());
    return card;
  },

  /* Ряды, которые добавляют плагины категории Discovery. */
  async renderDiscovery(box, force) {
    try {
      const data = await cachedApi('/api/discovery', force ? 1 : 600000);
      (data.rows || []).forEach(row => {
        if (row.items && row.items.length) box.appendChild(this.shelf(row));
      });
      Studio.layoutShelves();
    } catch { /* плагины подборок выключены или недоступны */ }
  },

  /* --------------------------------------------------------------- поиск */
  /* Вкладки поиска: подсветка активной и число найденного у каждой. */
  searchTabs(tab, counts) {
    const box = $('sTabs');
    if (!box) return;
    box.querySelectorAll('[data-stab]').forEach(btn => {
      btn.classList.toggle('on', btn.dataset.stab === tab);
      if (!btn.onclick) btn.onclick = () => App.setSearchTab(btn.dataset.stab);
      let badge = btn.querySelector('.stab-n');
      const n = counts ? counts[btn.dataset.stab] : null;
      if (n == null || btn.dataset.stab === 'all') { if (badge) badge.remove(); return; }
      if (!badge) {
        badge = el('span', 'stab-n');
        badge.setAttribute('data-no-i18n', '');
        btn.appendChild(badge);
      }
      badge.textContent = String(n);
    });
  },

  renderSearch({ query, tab = 'all', tracks, authors, albums, playlists, hasMore, done, extraDone }) {
    // Раньше здесь стояло t(`Results: ${query}`) — такого ключа нет, — и
    // жёстко прописанное «Поиск», которое видели все языки.
    $('sTitle').textContent = query ? t('Results: ') + query : t('Search');
    authors = authors || []; albums = albums || []; playlists = playlists || [];
    this.searchTabs(tab, {
      tracks: tracks.length, authors: authors.length,
      albums: albums.length, playlists: playlists.length,
    });

    // На «Все» — ленты по 12 карточек, на отдельной вкладке — вся сетка.
    const all = tab === 'all';
    const shelves = [
      ['sAuthors', 'sAuthorsG', authors, 'authors', item => this.authorCard(item)],
      ['sAlbums', 'sAlbumsG', albums, 'albums', item => this.collectionCard(item)],
      ['sPlaylists', 'sPlaylistsG', playlists, 'playlists', item => this.collectionCard(item)],
    ];
    shelves.forEach(([section, box, items, key, card]) => {
      const host = $(box);
      const shelf = $(section);
      if (!host || !shelf) return;
      const visible = all || tab === key;
      const list = all ? items.slice(0, 12) : items;
      host.innerHTML = '';
      host.className = all ? 'strip' : 'grid';
      if (!all) {
        if (host._navOff) host._navOff();
        shelf.querySelectorAll('.shelf-nav').forEach(node => node.remove());
        shelf.classList.remove('has-nav', 'scrollable');
      }
      list.forEach(item => host.appendChild(card(item)));
      if (visible && !list.length && !all) {
        host.innerHTML = extraDone || done
          ? `<div class="empty">${icon('search')}<div>${esc(t('Nothing found'))}</div></div>`
          : '';
        if (!extraDone) this.skeletons(host, 8, 'card');
      }
      shelf.style.display = visible && (list.length || !all) ? '' : 'none';
      if (all && list.length) this.attachStrip(shelf, host);
    });

    const showTracks = all || tab === 'tracks';
    if (!showTracks) {
      $('sTracksH').style.display = 'none';
      $('sTracks').style.display = 'none';
      $('sMore').style.display = 'none';
      return;
    }
    $('sTracks').style.display = '';
    if (!tracks.length) {
      // Пока источники отвечают, скелетоны остаются на месте.
      if (!done) return;
      $('sTracksH').style.display = 'none';
      const nothing = !authors.length && !albums.length && !playlists.length;
      const filteredOut = !!K.search.tracks.length;
      $('sTracks').innerHTML = nothing || tab === 'tracks'
        ? `<div class="empty">${icon('search')}<div>${esc(filteredOut ? Studio.tr('No tracks match these filters — reset the filters above','Нет треков по этим фильтрам — сбросьте фильтры выше') : t('Nothing found — try another query'))}</div></div>`
        : '';
      $('sMore').style.display = 'none';
      return;
    }
    $('sTracksH').style.display = '';
    if (Studio.search.layout === 'grid') {
      $('sTracks').className = 'grid studio-results-grid';
      $('sTracks').replaceChildren(...tracks.map(track => this.trackCard(track, tracks)));
    } else {
      $('sTracks').className = 'list';
      this.renderTracks($('sTracks'), tracks);
    }
    $('sMore').style.display = hasMore && done ? '' : 'none';
  },

  /* Горизонтальная карусель: колесо мыши, крупные стрелки и перетаскивание. */
  attachStrip(shelf, strip) {
    // Полка поиска переиспользуется, поэтому старые стрелки убираем — иначе
    // после каждого запроса на ней копился новый комплект кнопок.
    shelf.querySelectorAll('.shelf-nav').forEach(node => node.remove());
    shelf.classList.add('has-nav');
    // И старые обработчики тоже: лента поиска одна на все запросы, и раньше
    // на каждый запрос вешался новый комплект слушателей окна и наблюдателей.
    if (strip._navOff) strip._navOff();
    const ctl = new AbortController();
    const signal = ctl.signal;
    let observer = null;
    strip._navOff = () => { ctl.abort(); if (observer) observer.disconnect(); };

    const step = () => Math.max(260, strip.clientWidth * 0.85);
    const buttons = {};
    ['prev', 'next'].forEach(dir => {
      const btn = el('button', 'shelf-nav ' + dir, icon('down', 'ic'));
      btn.title = t(dir === 'prev' ? 'Back' : 'Forward');
      btn.onclick = event => {
        event.stopPropagation();
        strip.scrollBy({ left: (dir === 'prev' ? -1 : 1) * step(),
                         behavior: S.noAnim ? 'auto' : 'smooth' });
      };
      shelf.appendChild(btn);
      buttons[dir] = btn;
    });

    // Стрелка гаснет, когда ехать в эту сторону уже некуда.
    const edges = () => {
      // Полку главной перерисовали — её лента уже не в документе. Тогда
      // снимаем слушатели окна, иначе каждая перерисовка оставляла их висеть.
      if (!strip.isConnected) {
        if (strip._wasOn) strip._navOff();
        return;
      }
      strip._wasOn = true;
      // Секция выше ленты (заголовок, отступы), поэтому центр считаем по ленте.
      const top = strip.offsetTop + strip.clientHeight / 2;
      buttons.prev.style.top = buttons.next.style.top = top + 'px';
      const max = strip.scrollWidth - strip.clientWidth - 1;
      const scrollable = max > 4;
      shelf.classList.toggle('scrollable', scrollable);
      buttons.prev.classList.toggle('off', !scrollable || strip.scrollLeft <= 2);
      buttons.next.classList.toggle('off', !scrollable || strip.scrollLeft >= max);
    };
    strip.addEventListener('scroll', () => {
      cancelAnimationFrame(strip._edgeRaf);
      strip._edgeRaf = requestAnimationFrame(edges);
    }, { passive: true, signal });
    addEventListener('resize', debounce(edges, 150), { signal });
    // Обложки догружаются и меняют высоту ленты — следим за размером,
    // иначе стрелка остаётся там, где лента была в момент отрисовки.
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => edges());
      observer.observe(strip);
    }
    [60, 400, 1200].forEach(delay => setTimeout(edges, delay));
    edges();

    /* Колесо мыши намеренно не перехватываем: вертикальная прокрутка должна
       листать страницу, а не ряд. Ряд листается стрелками, перетаскиванием
       и горизонтальным жестом тачпада (это делает сам браузер). */

    // Перетаскивание мышью по пустому месту карусели.
    let dragging = false, startX = 0, startLeft = 0;
    strip.addEventListener('pointerdown', event => {
      if (event.target.closest('.card')) return;
      dragging = true; startX = event.clientX; startLeft = strip.scrollLeft;
      strip.classList.add('dragging');
    }, { signal });
    addEventListener('pointermove', event => {
      if (!dragging) return;
      strip.scrollLeft = startLeft - (event.clientX - startX);
    }, { signal });
    addEventListener('pointerup', () => { dragging = false; strip.classList.remove('dragging'); },
                     { signal });
  },

  /* --------------------------------------------------------- медиатека */
  renderLibrary() {
    if (typeof Workspace !== 'undefined' && Workspace.ready) { Workspace.renderLibrary(); return; }
    const grid = $('libG');
    grid.innerHTML = '';
    const liked = {
      id: 'liked', name: t('Liked tracks'),
      count: (K.likedTracks || []).length,
      cover: (K.likedTracks || [])[0] && K.likedTracks[0].thumbnail,
    };
    const likedCard = this.playlistCard(liked);
    likedCard.onclick = () => App.openLiked();
    grid.appendChild(likedCard);
    K.playlists.forEach(playlist => grid.appendChild(this.playlistCard(playlist)));
  },

  renderSidePlaylists() {
    const box = $('sidePl');
    box.innerHTML = '';
    K.playlists.filter(playlist => !(DEFAULT_PLAYLIST_NAMES.includes(playlist.name) && !Number(playlist.count || playlist.track_count || 0))).forEach(playlist => {
      const node = el('button', 'side-pl', `<img alt=""><span class="clip">${esc(plName(playlist.name))}</span>`);
      setImg(node.querySelector('img'), playlist.cover);
      node.onclick = () => App.openPlaylist(playlist.id, playlist.name);
      node.dataset.playlistId = playlist.id;
      box.appendChild(node);
    });
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.paintSidebar();
  },

  /* ------------------------------------------------------------- очередь

     Панель живая: строка запускает свой трек, кнопки лайка, «в плейлист»,
     «⋯» и крестик работают как в обычном списке, а порядок можно менять
     перетаскиванием. */
  renderQueue(force = false) {
    const box = $('queueList');
    if (!box) return;
    const count = $('queueCount');
    if (count) {
      count.textContent = Player.queue.length
        ? `${Player.queue.length} ${plural(Player.queue.length, t('track'), t('tracks'), t('tracks'))}`
        : '';
    }
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.queueRendered();
    const queueEl = $('queue');
    if (!force && queueEl && !queueEl.classList.contains('on')) {
      if (box.childElementCount) box.replaceChildren();
      return;
    }
    box.innerHTML = '';
    if (!Player.queue.length) {
      box.innerHTML = `<div class="empty">${icon('queue')}<div>${t('The queue is empty')}</div></div>`;
      return;
    }
    const total = Player.queue.length;
    const limit = this._showAllQueue || total <= 150 ? total : 150;
    const start = limit === total ? 0 : Math.max(0, Math.min(total - limit, (Player.index >= 0 ? Player.index : 0) - 20));
    const end = Math.min(total, start + limit);
    const frag = document.createDocumentFragment();
    for (let i = start; i < end; i++) {
      const track = Player.queue[i];
      const row = this.trackRow(track, i, Player.queue, {
        onPlay: () => { Player.index = i; Player.load(); },
        onRemove: () => { if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.snapshotQueue(); Player.removeAt(i); },
      });
      row.classList.add('q-row');
      row.dataset.at = i;
      row.draggable = true;
      if (i === Player.index) row.classList.add('playing');
      if (i < Player.index) row.classList.add('q-done');
      frag.appendChild(row);
    }
    if (end < total || start > 0) {
      const more = el('button', 'btn g sm', `${t('More')} (${total})`);
      more.style.margin = '12px auto';
      more.onclick = () => { this._showAllQueue = true; this.renderQueue(true); };
      frag.appendChild(more);
    }
    box.appendChild(frag);
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.filterQueue();
    this.bindQueueDrag(box);
  },

  /* Перетаскивание строк очереди. Индекс играющего трека едет вместе с ним,
     поэтому музыка не прерывается. */
  bindQueueDrag(box) {
    let from = -1;
    box.ondragstart = event => {
      const row = event.target.closest('.q-row');
      if (!row) return;
      from = +row.dataset.at;
      row.classList.add('q-drag');
      try { event.dataTransfer.setData('text/plain', String(from)); } catch {}
      event.dataTransfer.effectAllowed = 'move';
    };
    box.ondragover = event => {
      if (from < 0) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      const row = event.target.closest('.q-row');
      box.querySelectorAll('.q-over').forEach(n => n.classList.remove('q-over'));
      if (row) row.classList.add('q-over');
    };
    box.ondrop = event => {
      event.preventDefault();
      const row = event.target.closest('.q-row');
      box.querySelectorAll('.q-over').forEach(n => n.classList.remove('q-over'));
      if (from < 0 || !row) return;
      Player.move(from, +row.dataset.at);
      from = -1;
    };
    box.ondragend = () => {
      from = -1;
      box.querySelectorAll('.q-drag, .q-over')
        .forEach(n => n.classList.remove('q-drag', 'q-over'));
    };
  },

  markPlaying() {
    const id = Player.current && Player.current.id;
    const playing = Player.audio && !Player.audio.paused;
    document.querySelectorAll('.tr').forEach(row => {
      const on = row.dataset.id === id;
      row.classList.toggle('playing', on);
      row.classList.toggle('track-loading37', on && Player.busy);
      row.setAttribute('aria-busy', String(on && Player.busy));
      const num = row.querySelector('.n');
      if (num) {
        if (on && Player.busy) num.innerHTML = '<span class="loading-ring37" role="status" aria-label="' + esc(t('Loading…')) + '">'+loadingIcon38()+'</span>';
        else if (on && playing) num.innerHTML = '<span class="eq"><i></i><i></i><i></i></span>';
        else if (on) num.innerHTML = icon('play', 'ic s f');
        else num.textContent = [...row.parentNode.children].indexOf(row) + 1;
      }
    });
    const eqHtml = '<span class="eq"><i></i><i></i><i></i></span>';
    document.querySelectorAll('.card').forEach(card => {
      const on = !!id && card.dataset.id === id;
      card.classList.toggle('playing', on);
      const fab = card.querySelector('.play-fab');
      if (!fab) return;
      card.classList.toggle('track-loading37', on && Player.busy);
      card.setAttribute('aria-busy', String(on && Player.busy));
      const want = on && Player.busy ? 'loading' : on ? (playing ? 'eq' : 'pause') : 'play';
      if (fab.dataset.state === want) return;
      fab.dataset.state = want;
      fab.innerHTML = want === 'loading' ? '<span class="loading-ring37" aria-hidden="true">'+loadingIcon38()+'</span>' : want === 'eq' ? eqHtml : icon(want, 'ic s f');
    });
  },
};

function esc(text) {
  return String(text == null ? '' : text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function plural(n, one, few, many) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

/* Приветствие на главной идёт за часами компьютера: меняется само, когда
   наступает утро, день, вечер или ночь, — без перезапуска и без перехода по
   экранам. Пока окно свёрнуто, таймер спит; при возвращении — сверяемся сразу. */
function greetKey(hour) {
  return hour >= 23 || hour < 5 ? 'Good night' : hour < 12 ? 'Good morning'
    : hour < 18 ? 'Good afternoon' : 'Good evening';
}

function updateGreet() {
  const node = $('greet');
  if (!node) return;
  const key = greetKey(new Date().getHours());
  if (node.dataset.greet === key && node.dataset.lang === (S.lang || '')) return;
  node.dataset.greet = key;
  node.dataset.lang = S.lang || '';
  node.textContent = t(key);
}

setInterval(updateGreet, 15000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) updateGreet(); });
window.addEventListener('focus', updateGreet);
