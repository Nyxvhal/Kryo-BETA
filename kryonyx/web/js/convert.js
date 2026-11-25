/* convert.js — перенос плейлистов из Spotify, YouTube и SoundCloud.
   Сервер читает ссылку, ищет каждый трек в подключённых библиотеках и
   отдаёт прогресс; здесь показываем совпадения и сохраняем плейлист. */
'use strict';

const Convert = {
  job: null,
  items: [],
  skip: new Set(),
  picked: {},          // номер строки → трек, выбранный руками
  stage: '',
  timer: null,
  running: false,
  revision: 0,
  pollEpoch: 0,
  saving: false,
  page49: 0,
  destination: "",
  context49: null,

  LINK: /(open\.spotify\.com|spotify:)|((music\.)?youtube\.com|youtu\.be)|(soundcloud\.com)|(deezer\.com)/i,

  looksLikeLink(text) {
    const value = (text || '').trim();
    return /^(https?:\/\/|spotify:)/i.test(value) && this.LINK.test(value);
  },

  open(url) {
    openModal('mConvert');
    const input = $('cvUrl');
    if (input) {
      if (url) input.value = url.trim();
      setTimeout(() => input.focus(), 60);
    }
    if (url) this.start();
  },

  reset() {
    this.revision++;
    this.context49 = null;
    this.destination = "";
    this.stopPolling();
    this.job = null;
    this.items = [];
    this.page49 = 0;
    this.skip.clear();
    this.picked = {};
    this.stage = '';
    this.running = false;
    $('cvHead').innerHTML = '';
    $('cvName').value = '';
    $('cvStrict').classList.remove('on');
    $('cvList').innerHTML = '';
    $('cvFoot').style.display = 'none';
    this.buttons();
    this.progress(0, 0);
  },

  /* Кнопки снизу зависят от стадии: «Сохранить» появляется только на готовой
     задаче, «Отмена» — только пока задача идёт. */
  buttons() {
    const save = $('cvSave');
    const cancel = $('cvCancel');
    const ready = this.stage === 'ready' || this.stage === 'cancelled';
    if (save) {
      save.style.display = ready ? '' : 'none';
      save.disabled = !ready || this.saving;
    }
    if (cancel) {
      cancel.style.display = this.running ? '' : 'none';
      cancel.disabled = !this.running;
    }
  },

  progress(done, total) {
    const bar = $('cvBarFill');
    const text = $('cvProgress');
    const share = total ? Math.round((done / total) * 100) : 0;
    if (bar) bar.style.width = share + '%';
    if (text) text.textContent = total ? `${done} / ${total}` : '';
  },

  /* ---------------------------------------------------------------- запуск */
  async start() {
    if(this.running || this.saving || (typeof Transfer48!=="undefined"&&Transfer48.busy))return;
    const input = $('cvUrl');
    const url = (input ? input.value : '').trim();
    if (!url) { toast(t('Paste a playlist link')); return; }
    if (!this.looksLikeLink(url)) {
      toast(t('Link is not recognised: Spotify, YouTube, SoundCloud or Deezer needed'));
      return;
    }
    this.reset();
    if(typeof Connections49!=="undefined")Connections49.attach();
    const revision=this.revision;
    this.running = true;
    $('cvStart').disabled = true;
    this.stage = 'fetching';
    this.buttons();
    $('cvList').innerHTML = `<div class="plug-empty">${t('Reading the playlist…')}</div>`;
    try {
      const data = await api('/api/convert', { method: 'POST', body: { url } });
      if(revision!==this.revision)return;
      this.job = data.id;
      this.apply(data);
      this.poll();
    } catch (err) {
      if(revision!==this.revision)return;
      this.running = false;
      $('cvStart').disabled = false;
      this.stage = 'error';
      this.buttons();
      $('cvList').innerHTML = `<div class="plug-empty">${esc(t(err.message) || t('Error'))}</div>`;
    }
  },

  poll() {
    this.stopPolling();
    const job=this.job, revision=this.revision, epoch=this.pollEpoch;
    if(!job)return;
    const tick=async()=>{
      if(job!==this.job||revision!==this.revision||epoch!==this.pollEpoch)return;
      try {
        const data=await api(`/api/convert/${job}`);
        if(job!==this.job||revision!==this.revision||epoch!==this.pollEpoch)return;
        this.apply(data);
        if(['ready','error','cancelled'].includes(data.stage)) {
          this.running=false;$('cvStart').disabled=false;this.buttons();return;
        }
        this.timer=setTimeout(tick,1200);
      } catch(err) {
        if(job!==this.job||revision!==this.revision||epoch!==this.pollEpoch)return;
        // Keep the server job: losing one response must not start another import.
        const box=$('cvHead'), note=el('div','cv-warn');
        note.textContent=typeof Design48!=='undefined'?Design48.tr('Progress is unavailable. The transfer may still be running.','Нет связи с задачей. Перенос может продолжаться на сервере.'):err.message;
        const retry=el('button','btn g');retry.type='button';retry.textContent=typeof Design48!=='undefined'?Design48.tr('Reconnect','Проверить снова'):'Retry';retry.onclick=()=>this.poll();box.replaceChildren(note,retry);
      }
    };
    this.timer=setTimeout(tick,150);
  },

  /* --------------------------------------------------------------- отмена */
  async cancel() {
    if (!this.job || !this.running) return;
    $('cvCancel').disabled = true;
    try {
      const data = await api(`/api/convert/${this.job}/cancel`, { method: 'POST' });
      this.stopPolling();
      this.running = false;
      $('cvStart').disabled = false;
      this.apply(data);
      toast(t('Transfer stopped'));
    } catch (err) {
      toast(err.message || t('Error'));
    } finally {
      this.buttons();
    }
  },

  stopPolling() {
    this.pollEpoch++;
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
  },

  /* --------------------------------------------------------------- отрисовка */
  apply(data) {
    this.items = data.items || [];
    this.stage = data.stage || '';
    this.error = data.error || '';
    this.progress(data.done || 0, data.total || 0);

    const stage = {
      fetching: t('Reading the playlist…'),
      matching: t('Matching tracks…'),
      ready: t('Done'),
      cancelled: t('Stopped'),
      error: t('Error'),
    }[data.stage] || '';
    const service = { spotify: 'Spotify', youtube: 'YouTube', soundcloud: 'SoundCloud', deezer:'Deezer', vk:'VK Music', 'apple-music':'Apple Music', 'youtube-music':'YouTube Music', generic:'File' }[data.service]
      || data.service || '';
    const head = $('cvHead');
    head.innerHTML =
      `<div class="cv-head">
         <div class="cv-title" data-entity-name>${esc(data.name || service)}</div>
         <div class="cv-sub">${esc(service)}${data.author ? ' · ' + esc(data.author) : ''}
           ${data.total ? ' · ' + data.total + ' ' + t('tracks') : ''}</div>
         <div class="cv-stage">${esc(stage)}${data.error ? ': ' + esc(t(data.error)) : ''}</div>
         ${data.truncated ? `<div class="cv-warn">${t('The source returned only part of this playlist. Some tracks may be unavailable.')}</div>` : ''}
       </div>`;

    this.renderList();

    const foot = $('cvFoot');
    if (data.stage === 'ready' || data.stage === 'cancelled') {
      foot.style.display = '';
      const name = $('cvName');
      if (name && !name.value) name.value = data.name || '';
      $('cvStats').textContent =
        `${t('Found')}: ${data.matched || 0} · ${t('check these')}: ${data.weak || 0} · ` +
        `${t('not found')}: ${data.missing || 0}`;
    } else {
      foot.style.display = 'none';
    }
    this.buttons();
  },

  renderList() {
    const box = $('cvList');
    if (!this.items.length) {
      // Ссылка не открылась: вместо «Читаю плейлист…» показываем причину.
      if (this.stage === 'error') {
        box.innerHTML = `<div class="plug-empty">${esc(t(this.error || '') ||
          t('Spotify returned no track data for this link'))}</div>`;
      }
      return;
    }
    const pageSize=100,pages=Math.ceil(this.items.length/pageSize);
    this.page49=Math.max(0,Math.min(this.page49,pages-1));
    const offset=this.page49*pageSize;
    const frag = document.createDocumentFragment();
    if(pages>1){
      const nav=el('div','convert49-pages');
      const label=el('span');label.textContent=`${offset+1}–${Math.min(offset+pageSize,this.items.length)} / ${this.items.length}`;
      const button=(text,delta)=>{const b=el('button','btn g');b.type='button';b.textContent=text;b.disabled=this.page49+delta<0||this.page49+delta>=pages;b.onclick=()=>{this.page49+=delta;this.renderList();$('cvList').scrollTop=0;};return b;};
      nav.append(button('←',-1),label,button('→',1));frag.append(nav);
    }
    this.items.slice(offset,offset+pageSize).forEach((row, localIndex) => {
      const index=offset+localIndex;
      const manual = this.picked[index] || null;
      const match = manual || row.match;
      const state = manual ? 'manual' : row.state;
      const node = el('div', 'cv-row s-' + state + (this.skip.has(index) ? ' skipped' : ''));
      const label = { good: t('found'), weak: t('check'), missing: t('not found'),
                      error: t('error'), manual: t('chosen') }[state] || state;
      // Слабые и ненайденные строки можно починить руками через окно «Источники».
      const fixable = state !== 'good';
      node.innerHTML =
        `<span class="cv-n">${index + 1}</span>
         <span class="cv-src">
           <b class="clip">${esc(row.title)}</b>
           <small class="clip">${esc(row.artist || '')}</small>
         </span>
         <span class="cv-arrow">→</span>
         <span class="cv-dst">
           ${match ? `<b class="clip">${esc(match.title)}</b>
                      <small class="clip">${esc(match.artist || '')} · ${esc(sourceName(match.source))}</small>`
                   : `<b class="clip muted">${t('no match')}</b><small>${esc(row.error || '')}</small>`}
         </span>
         <span class="cv-state">${label}${(!manual && row.score) ? ` ${Math.round(row.score * 100)}%` : ''}
           ${fixable ? `<button class="cv-fix" type="button">${t('Choose')}</button>` : ''}</span>`;
      if (match) {
        node.onclick = () => {
          if (this.skip.has(index)) this.skip.delete(index); else this.skip.add(index);
          this.renderList();
        };
        node.title = t('Click to skip this track');
      }
      const fix = node.querySelector('.cv-fix');
      if (fix) {
        fix.onclick = event => { event.stopPropagation(); this.choose(index); };
      }
      frag.appendChild(node);
    });
    box.innerHTML = '';
    box.appendChild(frag);
  },

  /* Ручной выбор источника: показываем то же окно «Sources for this track»,
     а выбранный вариант подставляем в строку переноса. */
  choose(index) {
    const row = this.items[index];
    if (!row) return;
    Streams.open({ title: row.title, artist: row.artist, duration: row.duration }, {
      onPick: track => {
        this.picked[index] = track;
        this.skip.delete(index);
        openModal('mConvert');
        this.renderList();
        toast(t('Source chosen'));
      },
    });
  },

  /* --------------------------------------------------------------- сохранение */
  async save() {
    if (!this.job || this.saving) return;
    this.saving=true;
    const button = $('cvSave');
    button.disabled = true;
    try {
      const data = await api(`/api/convert/${this.job}/save`, {
        method: 'POST',
        body: {
          name: ($('cvName').value || '').trim(),
          include_weak: !$('cvStrict').classList.contains('on'),
          skip: [...this.skip],
          overrides: this.picked,
          playlist_id: this.destination ? Number(this.destination) : null,
        },
      });
      if(typeof Connections49!=="undefined")Connections49.saved(data);
      await refreshPlaylists();
      toast(`${data.playlist.name} · +${data.added} ${t('tracks')}`);
      closeModals();
      App.openPlaylist(data.playlist.id, data.playlist.name);
    } catch (err) {
      toast(err.message || t('Error'));
    } finally {
      this.saving=false;
      this.buttons();
    }
  },

  bind() {
    const start = $('cvStart');
    if (start) start.onclick = () => this.start();
    const input = $('cvUrl');
    if (input) {
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); this.start(); }
      });
    }
    const save = $('cvSave');
    if (save) save.onclick = () => this.save();
    const cancel = $('cvCancel');
    if (cancel) cancel.onclick = () => this.cancel();
    const strict = $('cvStrict');
    if (strict) strict.onclick = () => strict.classList.toggle('on');
    document.querySelectorAll('[data-convert-open]').forEach(node => {
      node.onclick = () => this.open('');
    });
    this.buttons();
  },
};
