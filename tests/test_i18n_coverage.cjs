'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert/strict');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'kryonyx/web/index.html'), 'utf8');
const scripts = [...html.matchAll(/<script src="\/js\/(i18n[^"]*\.js)/g)].map(m => m[1].split('?')[0]);

const env = {
  window: {},
  document: { documentElement: { lang: 'en' }, querySelectorAll: () => [], addEventListener: () => {} },
  localStorage: { getItem: () => null, setItem: () => {} },
  navigator: { language: 'en' },
  S: {},
  App: { afterLangChange: () => {}, boot: async () => {} },
  Views: {},
  Player: {},
  console,
};
env.window = env;
vm.createContext(env);
for (const s of scripts) {
  vm.runInContext(fs.readFileSync(path.join(root, 'kryonyx/web/js', s), 'utf8'), env);
}
vm.runInContext('globalThis.PACKS = PACKS; globalThis.LANGS = LANGS;', env);

const expectedLangs = ['en', 'ru', 'es', 'pt', 'de', 'fr', 'it', 'tr', 'pl', 'uk', 'zh', 'ja'];
for (const l of expectedLangs) {
  assert(env.LANGS.some(x => x.code === l) || l in env.PACKS || l === 'en', `Missing language ${l}`);
}

const packLangs = expectedLangs.filter(l => l !== 'en');
const allKeys = new Set();
for (const l of packLangs) {
  for (const k of Object.keys(env.PACKS[l])) allKeys.add(k);
}

for (const l of packLangs) {
  const pack = env.PACKS[l];
  const missing = [...allKeys].filter(k => !(k in pack));
  const empty = Object.keys(pack).filter(k => !String(pack[k] || '').trim());
  const phBad = [];
  for (const k of Object.keys(pack)) {
    const srcPh = (k.match(/\{[a-zA-Z0-9_]+\}/g) || []).sort().join(',');
    const valPh = (String(pack[k]).match(/\{[a-zA-Z0-9_]+\}/g) || []).sort().join(',');
    if (srcPh && srcPh !== valPh) phBad.push([k, srcPh, valPh]);
  }
  assert.equal(missing.length, 0, `${l} missing keys: ${missing.slice(0, 5).join(', ')}`);
  assert.equal(empty.length, 0, `${l} empty keys: ${empty.slice(0, 5).join(', ')}`);
  assert.equal(phBad.length, 0, `${l} placeholder mismatches: ${JSON.stringify(phBad.slice(0, 3))}`);
}

console.log(`I18N_COVERAGE_PASS languages=${expectedLangs.length} keys=${allKeys.size}`);
