/* netproxy.js — «Прокси / VPN» и кэш клипов в настройках.

   Прокси один на всё приложение: поиск, воспроизведение, клипы и обновление
   движка YouTube. Сервер (kryonyx/netproxy.py) применяет выбор сразу, без
   перезапуска. Пароль из адреса обратно в окно не возвращается. */
'use strict';

const NetProxy = {
  state: null,
  busy: false,

  async load(quiet) {
    try {
      this.state = await api('/api/network/proxy', { timeout: 8000 });
    } catch {
      this.state = null;
      if (!quiet) toast(t('Server is not responding'));
    }
    this.paint();
  },

  describe(st) {
    if (!st) return t('Direct connection');
    if (st.mode === 'custom') return t('Own proxy') + ': ' + (st.url || '—');
    if (st.mode === 'system') {
      return st.effective ? t('System proxy') + ': ' + st.effective
                          : t('System settings (VPN or system proxy)');
    }
    return t('Direct connection');
  },

  paint() {
    const st = this.state || { mode: 'off' };
    const line = $('npLine');
    if (line) line.textContent = this.describe(st);
    const mode = $('npMode');
    if (mode && document.activeElement !== mode) mode.value = st.mode || 'off';
    const url = $('npUrl');
    if (url && document.activeElement !== url) url.value = st.url || '';
    this.toggle();
    const box = $('npState');
    if (box) {
      const parts = [this.describe(st)];
      if (st.mode === 'system' && !st.system_found) {
        parts.push(t('No system proxy found — the system VPN, if any, still works'));
      }
      if (st.mode === 'custom' && /^socks/i.test(st.url || '') && !st.socks_ready) {
        parts.push(t('SOCKS needs the aiohttp-socks package'));
      }
      box.textContent = parts.join(' · ');
    }
  },

  toggle() {
    const mode = $('npMode');
    const custom = $('npCustom');
    if (custom && mode) custom.style.display = mode.value === 'custom' ? '' : 'none';
    const hint = $('npHint');
    if (hint && mode) {
      hint.textContent = ({
        off: t('Connect directly, as usual'),
        system: t('Use the proxy of Windows / macOS / the environment'),
        custom: t('Send everything through the address below'),
      })[mode.value] || '';
    }
  },

  open() {
    openModal('mProxy');
    this.load(true);
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

  async save(button) {
    await this.run(button, async () => {
      this.state = await api('/api/network/proxy', {
        method: 'PUT', timeout: 10000,
        body: { mode: $('npMode').value, url: ($('npUrl') || {}).value || '' },
      });
      this.paint();
      dropCache('/api/search');
      toast(t('Network settings saved'));
    });
  },

  async test(button) {
    await this.run(button, async () => {
      // Сначала сохраняем введённое: проверять нужно то, что выбрано в окне.
      this.state = await api('/api/network/proxy', {
        method: 'PUT', timeout: 10000,
        body: { mode: $('npMode').value, url: ($('npUrl') || {}).value || '' },
      });
      this.paint();
      toast(t('Checking the connection…'), 4000);
      const res = await api('/api/network/proxy/test', { method: 'POST', timeout: 25000 });
      toast(`${t('YouTube answered')} · ${res.ms} ${t('ms')}` + (res.ip ? ` · IP ${res.ip}` : ''), 6000);
    });
  },

  /* Сохранённые клипы: сколько места занимают и очистка. */
  async cache() {
    const line = $('clipCacheState');
    if (!line) return;
    try {
      const st = await api('/api/video/cache', { timeout: 6000 });
      const mb = Math.round((st.bytes || 0) / 1048576);
      line.textContent = st.files ? `${st.files} ${t('clips')} · ${mb} MB` : t('No saved clips yet');
    } catch {
      line.textContent = '—';
    }
  },

  bind() {
    const open = $('bProxy');
    if (open) open.onclick = () => this.open();
    const mode = $('npMode');
    if (mode) mode.onchange = () => this.toggle();
    const save = $('npSave');
    if (save) save.onclick = () => this.save(save);
    const test = $('npTest');
    if (test) test.onclick = () => this.test(test);
    const clear = $('bClipCache');
    if (clear) {
      clear.onclick = async () => {
        await this.run(clear, async () => {
          await api('/api/video/cache', { method: 'DELETE', timeout: 15000 });
          toast(t('Saved clips removed'));
        });
        this.cache();
      };
    }
    this.cache();
    this.load(true);
  },
};
