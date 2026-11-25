'use strict';
const vm = require('vm');
const fs = require('fs');
const assert = require('assert/strict');

const loadRequests = [];
const cancelRequests = [];
let failNext = false;

const env = {
  S: { prefetch: true, repeat: 'off' },
  URLSearchParams,
  AbortController,
  Views: { renderQueue() {}, markPlaying() {} },
  toast() {},
  t: s => s,
  fetch: (url, options) => {
    const query = new URLSearchParams(url.split('?')[1] || '');
    if (query.get('cancel') === '1') {
      cancelRequests.push({ url, options });
      return Promise.resolve({ ok: true, json: async () => ({ cancelled: 1 }) });
    }
    loadRequests.push({ url, options });
    if (failNext) {
      failNext = false;
      return Promise.reject(new Error('network failure'));
    }
    return Promise.resolve({ ok: true, json: async () => ({ ready: true, cached: true }) });
  },
};

vm.createContext(env);
vm.runInContext(fs.readFileSync(__dirname + '/../kryonyx/web/js/player.js', 'utf8') + '\nglobalThis.p = Player;', env);
const p = env.p;
p.saveState = () => {};

let n = 0;
const check = (s, v) => {
  assert(v, s);
  n++;
  console.log('PASS', s);
};

(async () => {
  p.audio = { readyState: 0 };
  p.queue = ['a', 'b', 'c', 'd', 'e'].map(id => ({ id, title: id }));
  p.current = p.queue[0];
  p.index = 0;
  p.loadToken = 1;
  p.queueRevision = 1;

  p.prefetchNext();
  check('no speculative audio before current media is ready', loadRequests.length === 0 && p.prefetchState.state === 'queued');

  p.audio.readyState = 3;
  p.prefetchNext();
  check('one successor, not four', loadRequests.length === 1 && new URLSearchParams(loadRequests[0].url.split('?')[1]).get('id') === 'b');

  p.prefetchNext();
  check('repeated canplay is deduplicated', loadRequests.length === 1);

  const firstSignal = loadRequests[0].options.signal;
  p.queue = [p.current, { id: 'e' }, { id: 'b' }];
  p.prefetchNext();
  check('effective shuffle queue order determines next track', loadRequests.length === 2 && loadRequests[1].url.includes('id=e'));
  check('obsolete request is aborted', firstSignal.aborted);

  env.S.repeat = 'one';
  p.prefetchNext();
  check('repeat-one cancels active prefetch and does not fetch a different song', loadRequests.length === 2 && cancelRequests.length === 1 && p.prefetchState.state === 'cancelled');

  env.S.repeat = 'off';
  p.index = p.queue.length - 1;
  p.current = p.queue[p.index];
  p.prefetchNext();
  check('no speculative radio or wrap at queue end', loadRequests.length === 2);

  env.S.repeat = 'all';
  p.prefetchNext();
  check('repeat-all warms first song at the end', loadRequests.length === 3 && loadRequests[2].url.includes('id=a'));

  env.S.prefetch = false;
  p.loadToken++;
  p.prefetchNext();
  check('prefetch preference is respected and cancels active warm-up', loadRequests.length === 3 && cancelRequests.length === 2);

  env.S.prefetch = true;
  p.index = 0;
  p.current = p.queue[0];
  p.addNext({ id: 'z', title: 'z' });
  check('addNext updates queueRevision and prefetches inserted track', loadRequests.length === 4 && loadRequests[3].url.includes('id=z'));

  failNext = true;
  p.move(1, 2);
  await new Promise(r => setTimeout(r, 20));
  check('network failure during prefetch sets failed state without throwing', p.prefetchState.state === 'failed');

  console.log('PREFETCH_V30_PASS', n);
})().catch(err => {
  console.error(err);
  process.exit(1);
});
