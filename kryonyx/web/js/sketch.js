/* Legacy palette import compatibility; drawn renderer removed in v30. */
'use strict';
function skHex(hex) {
  const v = String(hex || '').replace('#', '').trim();
  const s = v.length === 3 ? v.split('').map(c => c + c).join('') : v;
  const n = parseInt(s, 16);
  if (!/^[0-9a-f]{6}$/i.test(s) || Number.isNaN(n)) return [0, 0, 0];
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function skStr(rgb) {
  return '#' + rgb.map(v => Math.max(0, Math.min(255, Math.round(v)))
                             .toString(16).padStart(2, '0')).join('');
}
/* k = 0 — первый цвет, k = 1 — второй. */
function skMix(a, b, k) {
  const x = skHex(a), y = skHex(b);
  return skStr([0, 1, 2].map(i => x[i] + (y[i] - x[i]) * k));
}
function skLuminance(hex) {
  const c = skHex(hex).map(v => { const n = v / 255; return n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4; });
  return c[0] * .2126 + c[1] * .7152 + c[2] * .0722;
}
function skOnColor(hex) { return skLuminance(hex) > .179 ? '#000000' : '#FFFFFF'; }
function skRgb(hex) { return skHex(hex).join(', '); }
/* Цвет внутри data:URI пишется как %23rrggbb: решётка в URL недопустима. */
function skUrlColor(hex) { return '%23' + String(hex).replace('#', ''); }

/* --------------------------------------------------------------- скины */
/* Скин задаёт только пять цветов и характер бумаги — остальное выводится.
   `dark: true` означает «светлые чернила по тёмной бумаге»: меняется не
   палитра, а то, как вычисляются подложки и прозрачные слои. */
const SKETCH_SKINS = {
  saba: {
    name: 'Original', note: 'The original: deep-sea ink on warm paper',
    ink: '#1D3F72', paper: '#FFFCF4', sky: '#3FB4E8', gold: '#F2C230',
    blush: '#F9C6CC', coral: '#E0575C', doodles: 'fish', tex: 'ruled', mark: 'dot',
  },
  plain: {
    name: 'Plain paper', note: 'Same hand, no doodles in the margins',
    ink: '#1D3F72', paper: '#FFFCF4', sky: '#3FB4E8', gold: '#F2C230',
    blush: '#F9C6CC', coral: '#E0575C', doodles: 'none', tex: 'plain', mark: 'dot',
  },
  graphite: {
    name: 'Graphite', note: 'Pencil on grey paper, almost no colour',
    ink: '#2E2E33', paper: '#ECE9E2', sky: '#7A7A82', gold: '#A2927A',
    blush: '#C9BFB4', coral: '#8C5A52', doodles: 'geo', tex: 'plain', mark: 'dot',
  },
  ballpoint: {
    name: 'Ballpoint', note: 'Blue pen on a squared notebook',
    ink: '#24409A', paper: '#FBFBF6', sky: '#4A6FD6', gold: '#E2A33C',
    blush: '#E8C3D6', coral: '#CC4A52', doodles: 'stars', tex: 'grid', mark: 'star',
  },
  sakura: {
    name: 'Sakura', note: 'Plum ink, petals in the margins',
    ink: '#7A3550', paper: '#FFF6F8', sky: '#F18FB0', gold: '#F6C45E',
    blush: '#FBD3DD', coral: '#E0607E', doodles: 'hearts', tex: 'dots', mark: 'star',
  },
  matcha: {
    name: 'Matcha', note: 'Green ink on cool paper',
    ink: '#164D3C', paper: '#F2FBF6', sky: '#2FBF8F', gold: '#D9AE42',
    blush: '#CBE8D6', coral: '#C9603F', doodles: 'music', tex: 'ruled', mark: 'dot',
  },
  kraft: {
    name: 'Kraft', note: 'Brown pen on packing paper',
    ink: '#44301E', paper: '#E6D3B3', sky: '#2F7A74', gold: '#C8781F',
    blush: '#D8A98C', coral: '#A8452E', doodles: 'geo', tex: 'plain', mark: 'dot',
  },
  sepia: {
    name: 'Sepia', note: 'Old ink, no colour accents',
    ink: '#5A3E2B', paper: '#F6EBD8', sky: '#A9774A', gold: '#C9972B',
    blush: '#E0C7A6', coral: '#9C4B2E', doodles: 'none', tex: 'ruled', mark: 'dot',
  },
  blueprint: {
    name: 'Blueprint', note: 'White lines on drafting blue', dark: true,
    ink: '#E4EFFF', paper: '#123A64', sky: '#7FC8FF', gold: '#FFD98A',
    blush: '#B9D6F2', coral: '#FF8A7A', doodles: 'geo', tex: 'grid', mark: 'dot',
  },
  noir: {
    name: 'Noir', note: 'Chalk-white ink on near-black paper', dark: true,
    ink: '#EFECE4', paper: '#15161A', sky: '#9BB0C4', gold: '#D9BE7E',
    blush: '#C9A8AE', coral: '#E0675F', doodles: 'none', tex: 'plain', mark: 'dot',
  },
  chalk: {
    name: 'Chalkboard', note: 'Chalk on a green board', dark: true,
    ink: '#F4F6EE', paper: '#1E2A24', sky: '#8FD9C0', gold: '#F5D77E',
    blush: '#EBC7CE', coral: '#F08E7E', doodles: 'stars', tex: 'plain', mark: 'star',
  },
  midnightsaba: {
    name: 'Original at night', note: 'The original palette, inverted into the dark', dark: true,
    ink: '#DCE9F8', paper: '#121C2B', sky: '#53C3F2', gold: '#F2C230',
    blush: '#F3A8B2', coral: '#E0575C', doodles: 'fish', tex: 'ruled', mark: 'dot',
  },
  neon: {
    name: 'Neon marker', note: 'Highlighter on black paper', dark: true,
    ink: '#D8CCFF', paper: '#0C0A16', sky: '#FF4FD8', gold: '#4FE8FF',
    blush: '#FF9FE4', coral: '#FF5C7A', doodles: 'stars', tex: 'dots', mark: 'star',
  },
  inkred: {
    name: 'Red pen', note: 'The teacher who marked your homework',
    ink: '#8E1F28', paper: '#FFFDF7', sky: '#C3424C', gold: '#D79B2A',
    blush: '#F2C4C7', coral: '#6E1118', doodles: 'none', tex: 'ruled', mark: 'dot',
  },
  lavendernote: {
    name: 'Lavender note', note: 'Violet ink on a dotted pad',
    ink: '#4A3A7A', paper: '#F8F5FF', sky: '#9B86E8', gold: '#E8C45C',
    blush: '#E2D2F5', coral: '#C9607E', doodles: 'stars', tex: 'dots', mark: 'star',
  },
  ocean: {
    name: 'Ocean log', note: 'Ship journal: teal ink on salted paper',
    ink: '#13424F', paper: '#F0F8F8', sky: '#2E9BAD', gold: '#E0A93C',
    blush: '#BFE3E3', coral: '#C9563F', doodles: 'fish', tex: 'ruled', mark: 'dot',
  },
  mint: {
    name: 'Mint', note: 'Cool green pen on a squared pad',
    ink: '#1F5244', paper: '#F3FCF7', sky: '#3FCFA0', gold: '#CFC24F',
    blush: '#C8EEDC', coral: '#CC6A52', doodles: 'music', tex: 'grid', mark: 'dot',
  },
  honeycomb: {
    name: 'Honeycomb', note: 'Warm brown ink on amber paper',
    ink: '#5C3B14', paper: '#FFF6E0', sky: '#C9922E', gold: '#F2B33D',
    blush: '#F0DCB0', coral: '#B35A2E', doodles: 'geo', tex: 'dots', mark: 'dot',
  },
  comic: {
    name: 'Comic', note: 'Heavy black outline, primary colours',
    ink: '#141414', paper: '#FFFEF2', sky: '#3B7BF2', gold: '#FFD23D',
    blush: '#FFC2CF', coral: '#F2453D', doodles: 'stars', tex: 'dots', mark: 'star',
  },
  grid: {
    name: 'Engineering', note: 'Grey lead on graph paper, strictly geometric',
    ink: '#33414F', paper: '#F4F7FA', sky: '#5B7F99', gold: '#B08C3C',
    blush: '#D2DEE8', coral: '#A35147', doodles: 'geo', tex: 'grid', mark: 'dot',
  },
  storm: {
    name: 'Storm', note: 'Pale ink on slate paper', dark: true,
    ink: '#DCE3EC', paper: '#1C2128', sky: '#7FA8D9', gold: '#D9B86A',
    blush: '#C2CBD6', coral: '#E07A6A', doodles: 'geo', tex: 'grid', mark: 'dot',
  },
  campfire: {
    name: 'Campfire', note: 'Warm chalk on charred paper', dark: true,
    ink: '#F7E6CC', paper: '#1A1210', sky: '#E09A4F', gold: '#F5C65C',
    blush: '#E6BFA0', coral: '#E05B3C', doodles: 'music', tex: 'plain', mark: 'star',
  },
  deepsea: {
    name: 'Deep sea', note: 'Glowing ink far below the surface', dark: true,
    ink: '#CFE9F5', paper: '#0A1A26', sky: '#35C2D9', gold: '#E8D27A',
    blush: '#A9D8E0', coral: '#F07A5F', doodles: 'fish', tex: 'dots', mark: 'dot',
  },
};


const Sketch={skin(){return SKETCH_SKINS[S.sketchSkin]||SKETCH_SKINS.saba;},apply(){S.sketch=false;this.clear();},clear(){document.body.classList.remove('sketch','sk-dark','sk-nowob','sk-nohand','sk-noshadow');},build(){},bind(){}};
function skAccessible(color,paper) {
 const ratio=(a,b)=>{const x=skLuminance(a),y=skLuminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
 let out=color;for(let n=0;n<24&&ratio(out,paper)<4.5;n++)out=skMix(out,skLuminance(paper)>.5?'#000000':'#FFFFFF',.12);return out;
}
