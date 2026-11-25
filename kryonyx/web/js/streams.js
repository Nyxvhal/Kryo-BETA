/* streams.js — выбор источника звука по двухфазной схеме:
   сначала кандидаты (/api/streams), потом разрешение ссылки (/api/streams/resolve). */
'use strict';

const Streams = {
  track: null,
  candidates: [],
  onPick: null,

  /* options.onPick — если передан, выбранный источник не начинает играть,
     а возвращается вызывающему коду (так окно переиспользует перенос). */
  async open(track, options = {}) {
    this.track = track;
    this.onPick = options.onPick || null;
    this.candidates = [];
    $('streamsSub').textContent = `${track.artist || ''} — ${track.title || ''}`;
    $('streamsList').innerHTML = `<div class="plug-empty">${t('Looking for sources…')}</div>`;
    openModal('mStreams');
    await this.load(false);
  },

  async load(fresh) {
    const track = this.track;
    if (!track) return;
    const params = new URLSearchParams({ title: track.title || '', artist: track.artist || '' });
    if (track.id) params.set('id', track.id);
    if (track.duration) params.set('duration', String(track.duration));
    if (fresh) params.set('fresh', '1');
    try {
      const data = await api('/api/streams?' + params.toString());
      this.candidates = data.candidates || [];
      if (!data.success && !this.candidates.length) {
        $('streamsList').innerHTML =
          `<div class="plug-empty">${t(data.error || 'No sources found')}</div>`;
        return;
      }
    } catch (err) {
      $('streamsList').innerHTML = `<div class="plug-empty">${esc(err.message)}</div>`;
      return;
    }
    this.render();
  },

  render() {
    const box = $('streamsList');
    box.innerHTML = '';
    if (!this.candidates.length) {
      box.innerHTML = `<div class="plug-empty">${t('No sources found')}</div>`;
      return;
    }
    this.candidates.forEach((candidate, index) => {
      const source = candidate.source || {};
      const row = el('div', 'stream-row' + (candidate.failed ? ' bad' : ''));
      const seconds = candidate.durationMs ? Math.round(candidate.durationMs / 1000) : null;
      const stream = candidate.stream || null;
      const state = candidate.failed ? t('failed')
        : stream ? [stream.qualityLabel, stream.codec, stream.protocol]
                     .filter(Boolean).join(' · ')
        : t('not resolved yet');
      row.innerHTML =
        `<span class="sr-n">${index + 1}</span>` +
        `<span class="sr-src">${esc(source.name || source.provider || '')}</span>` +
        `<span class="sr-t">${esc(candidate.title || '')}</span>` +
        `<span class="sr-s">${esc(state)}</span>` +
        `<span class="sr-d">${seconds ? fmt(seconds) : '--:--'}</span>`;
      row.onclick = () => this.pick(candidate);
      box.appendChild(row);
    });
  },

  /* Выбор источника: разрешаем ссылку и играем именно этого кандидата. */
  async pick(candidate) {
    if (candidate.failed) { toast(t('failed')); return; }
    toast(t('Loading…'));
    try {
      const data = await api('/api/streams/resolve',
        { method: 'POST', body: { candidate } });
      const resolved = data.candidate || candidate;
      const index = this.candidates.findIndex(c => c.id === resolved.id);
      if (index >= 0) this.candidates[index] = resolved;
      if (!data.ok) { this.render(); toast(resolved.error || t('Error')); return; }
      closeModals();
      if (this.onPick) {
        const handler = this.onPick;
        this.onPick = null;
        handler({
          id: resolved.id,
          title: resolved.title || this.track.title || '',
          artist: resolved.artist || this.track.artist || '',
          duration: resolved.durationMs ? Math.round(resolved.durationMs / 1000)
                                        : (this.track.duration || null),
          thumbnail: resolved.thumbnail || '',
          source: (resolved.source || {}).provider || this.track.source || '',
        });
        return;
      }
      Player.play({
        ...this.track,
        id: resolved.id,
        source: (resolved.source || {}).provider || this.track.source,
        duration: resolved.durationMs ? Math.round(resolved.durationMs / 1000)
                                      : this.track.duration,
      });
      toast(t('Source changed'));
    } catch (err) {
      toast(err.message || t('Error'));
    }
  },

  bind() {
    const refresh = $('streamsRefresh');
    if (refresh) refresh.onclick = () => this.load(true);
  },
};
