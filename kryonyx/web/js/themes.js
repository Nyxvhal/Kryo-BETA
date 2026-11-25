/* themes.js — библиотека тем: собственные палитры и палитры «по мотивам».
   Каждая тема честно подписана: цвета подобраны на глаз, это не код и не
   ассеты тех приложений, и ни с кем из них мы не связаны. */
'use strict';

const THEME_LIBRARY = {
  tide82: { name:'Tide', group:'kryonyx', accent:'#70E2D1', accent2:'#82A9FF', bg:'#0B171B', flat:true },
  dusk82: { name:'Afterglow', group:'kryonyx', accent:'#F5A8A3', accent2:'#C5A6FF', bg:'#1B131B', flat:true },
  mineral82: { name:'Mineral', group:'oled', accent:'#A8D6D0', accent2:'#AFBDF3', bg:'#090E10', flat:true },
  morning82: { name:'Morning', group:'light', accent:'#315CB4', accent2:'#357E70', bg:'#F5F8FA', light:true, flat:true },
  studio6: { name: 'Studio · Graphite', group: 'kryonyx', accent: '#A995FF', accent2: '#70C9BC', bg: '#111216', flat: true },
  daylight6: { name: 'Studio · Daylight', group: 'light', accent: '#6246C4', accent2: '#267F75', bg: '#F7F8FA', light: true, flat: true },
  /* ------------------------------------------------------------ Kryo */
  nebula:   { name: 'Nebula',    group: 'kryonyx', accent: '#7C5CFF', accent2: '#FF5CA8', bg: '#08080F' },
  midnight: { name: 'Midnight',  group: 'kryonyx', accent: '#4C8DFF', accent2: '#37E6C9', bg: '#05070F' },
  ember:    { name: 'Ember',     group: 'kryonyx', accent: '#FF7A3D', accent2: '#FF3D71', bg: '#120A08' },
  matrix:   { name: 'Matrix',    group: 'kryonyx', accent: '#2BE88B', accent2: '#7CFF5C', bg: '#05100A' },
  sakura:   { name: 'Sakura',    group: 'kryonyx', accent: '#FF7EB6', accent2: '#B47CFF', bg: '#140A12' },
  gold:     { name: 'Gold',      group: 'kryonyx', accent: '#E8B84B', accent2: '#FF8A3D', bg: '#100D06' },
  ice:      { name: 'Ice',       group: 'kryonyx', accent: '#5AC8FA', accent2: '#8E7CFF', bg: '#050B12' },
  coffee:   { name: 'Coffee',    group: 'kryonyx', accent: '#C98A5B', accent2: '#8C5A3C', bg: '#14100D', flat: true },
  sunset:   { name: 'Sunset',    group: 'kryonyx', accent: '#FF6B6B', accent2: '#FFD93D', bg: '#140A14' },
  ocean:    { name: 'Ocean',     group: 'kryonyx', accent: '#22D3EE', accent2: '#3B82F6', bg: '#04121A' },
  aurora:   { name: 'Aurora',    group: 'kryonyx', accent: '#5CE1E6', accent2: '#7C5CFF', bg: '#061018' },
  plum:     { name: 'Plum',      group: 'kryonyx', accent: '#B06CFF', accent2: '#FF6CB0', bg: '#120A18' },
  rust:     { name: 'Rust',      group: 'kryonyx', accent: '#D4663C', accent2: '#F2A65A', bg: '#150D09', flat: true },
  lagoon:   { name: 'Lagoon',    group: 'kryonyx', accent: '#16C5B0', accent2: '#3DDC97', bg: '#04120F' },
  royal:    { name: 'Royal',     group: 'kryonyx', accent: '#4C6BFF', accent2: '#9A6BFF', bg: '#070A18' },
  cherry:   { name: 'Cherry',    group: 'kryonyx', accent: '#FF3B5C', accent2: '#FF8A3D', bg: '#150709' },
  lemon:    { name: 'Lemon',     group: 'kryonyx', accent: '#E8E04B', accent2: '#9BE84B', bg: '#11110A', flat: true },
  cobalt:   { name: 'Cobalt',    group: 'kryonyx', accent: '#2E6BFF', accent2: '#00C2FF', bg: '#04091A' },
  moss:     { name: 'Moss',      group: 'kryonyx', accent: '#8FBF5A', accent2: '#4F9D69', bg: '#0C1009', flat: true },
  dusk:     { name: 'Dusk',      group: 'kryonyx', accent: '#9A8CFF', accent2: '#FFA0C9', bg: '#0C0A14' },
  storm:    { name: 'Storm',     group: 'kryonyx', accent: '#7FA8D9', accent2: '#B6C9DE', bg: '#0A0E14', flat: true },
  candy:    { name: 'Candy',     group: 'kryonyx', accent: '#FF7AC6', accent2: '#7AE0FF', bg: '#140B16' },
  velvet:   { name: 'Velvet',    group: 'kryonyx', accent: '#C04CFF', accent2: '#FF4C7A', bg: '#0F0718' },
  pine:     { name: 'Pine',      group: 'kryonyx', accent: '#3FA66B', accent2: '#8FD96B', bg: '#07110C', flat: true },
  denim:    { name: 'Denim',     group: 'kryonyx', accent: '#5B86C9', accent2: '#7FB2E6', bg: '#080D14', flat: true },
  mango:    { name: 'Mango',     group: 'kryonyx', accent: '#FFA23D', accent2: '#FFD93D', bg: '#140E05' },
  orchid:   { name: 'Orchid',    group: 'kryonyx', accent: '#D46CFF', accent2: '#6CC9FF', bg: '#100A16' },
  ruby:     { name: 'Ruby',      group: 'kryonyx', accent: '#FF2E5B', accent2: '#B02EFF', bg: '#13060B' },
  copper:   { name: 'Copper',    group: 'kryonyx', accent: '#D98A4B', accent2: '#A6553C', bg: '#120C08', flat: true },
  teal:     { name: 'Teal',      group: 'kryonyx', accent: '#2FBFA8', accent2: '#2F8FBF', bg: '#04100F', flat: true },
  glacier:  { name: 'Glacier',   group: 'kryonyx', accent: '#8FD6FF', accent2: '#C9E8FF', bg: '#060C12' },
  vapor:    { name: 'Vapor',     group: 'kryonyx', accent: '#A78BFA', accent2: '#67E8F9', bg: '#0B0A14' },
  sand:     { name: 'Sand',      group: 'kryonyx', accent: '#D9B382', accent2: '#B08C5A', bg: '#110F0A', flat: true },
  grape:    { name: 'Grape',     group: 'kryonyx', accent: '#7A4CFF', accent2: '#4CC9FF', bg: '#0A0714' },
  flare:    { name: 'Flare',     group: 'kryonyx', accent: '#FF5C2B', accent2: '#FFC32B', bg: '#120804' },

  /* ---------------------------------------------------- нарисованные темы */
  /* Темы со своим слоем оформления: `sketch: true` включает css/sketch.css —
     чернильные обводки, смещённые тени и рукописный шрифт. Сами палитры
     («скины») лежат в js/sketch.js и дописываются в каталог ниже, сразу
     после его объявления: так один список скинов обслуживает и экран тем,
     и панель тонкой настройки.
     Старый ключ `sketch` остаётся ради баз, где он уже сохранён. */
  sketch:   { name: 'Sketch', group: 'hidden', accent: '#3FB4E8', accent2: '#F2C230', bg: '#FFFCF4',
              light: true, sketch: true, skin: 'saba' },

  /* ------------------------------------------------------- светлые темы */
  paper:    { name: 'Paper',     group: 'light', accent: '#6B4CFF', accent2: '#FF4C8B', bg: '#F6F5FB', light: true },
  mint:     { name: 'Mint',      group: 'light', accent: '#12B981', accent2: '#0EA5E9', bg: '#F3FAF7', light: true },
  mono:     { name: 'Mono',      group: 'light', accent: '#1A1A1A', accent2: '#5A5A5A', bg: '#FFFFFF', light: true, flat: true },
  github:   { name: 'GitHub Light', group: 'light', accent: '#0969DA', accent2: '#8250DF', bg: '#FFFFFF', light: true, flat: true,
              note: 'Palette inspired by GitHub' },
  solarl:   { name: 'Solarized Light', group: 'light', accent: '#268BD2', accent2: '#B58900', bg: '#FDF6E3', light: true, flat: true,
              note: 'Palette by Ethan Schoonover' },
  cream:    { name: 'Cream',     group: 'light', accent: '#C98A3C', accent2: '#8C6239', bg: '#FDF8EF', light: true, flat: true },
  skylight: { name: 'Sky',       group: 'light', accent: '#2D8BF0', accent2: '#39C0ED', bg: '#F4F9FF', light: true },
  blossom:  { name: 'Blossom',   group: 'light', accent: '#E8679B', accent2: '#A97BE8', bg: '#FFF5F8', light: true },
  linen:    { name: 'Linen',     group: 'light', accent: '#6B7F6B', accent2: '#A8906B', bg: '#F7F5EF', light: true, flat: true },
  lavender: { name: 'Lavender',  group: 'light', accent: '#7B6CE8', accent2: '#B48CF0', bg: '#F7F5FF', light: true },
  nordl:    { name: 'Nord Light', group: 'light', accent: '#5E81AC', accent2: '#88C0D0', bg: '#ECEFF4', light: true, flat: true,
              note: 'Nord palette by Arctic Ice Studio' },
  latte:    { name: 'Catppuccin Latte', group: 'light', accent: '#8839EF', accent2: '#EA76CB', bg: '#EFF1F5', light: true,
              note: 'Catppuccin palette by the Catppuccin org' },
  dawn:     { name: 'Rosé Pine Dawn', group: 'light', accent: '#B4637A', accent2: '#907AA9', bg: '#FAF4ED', light: true,
              note: 'Rosé Pine palette by the Rosé Pine team' },
  onelight: { name: 'One Light', group: 'light', accent: '#4078F2', accent2: '#A626A4', bg: '#FAFAFA', light: true, flat: true,
              note: 'Palette inspired by Atom One Light' },
  seashell: { name: 'Seashell',  group: 'light', accent: '#2BA6A0', accent2: '#4FC3B8', bg: '#F2FAF9', light: true },
  peach:    { name: 'Peach',     group: 'light', accent: '#E8734C', accent2: '#F0A86C', bg: '#FFF6F1', light: true },
  sage:     { name: 'Sage',      group: 'light', accent: '#5F8C62', accent2: '#8FB07A', bg: '#F4F8F2', light: true, flat: true },
  slatel:   { name: 'Slate',     group: 'light', accent: '#4A5A75', accent2: '#7C8DA8', bg: '#F1F3F7', light: true, flat: true },
  bubble:   { name: 'Bubblegum', group: 'light', accent: '#E8488F', accent2: '#6C9BFF', bg: '#FFF4F9', light: true },
  honey:    { name: 'Honey',     group: 'light', accent: '#C9941F', accent2: '#E0B23C', bg: '#FFFBEF', light: true, flat: true },
  arctic:   { name: 'Arctic',    group: 'light', accent: '#1F8FD6', accent2: '#5AB8E8', bg: '#F0F7FC', light: true },
  grayl:    { name: 'Newsprint', group: 'light', accent: '#3A3A3A', accent2: '#7A7A7A', bg: '#F4F3F0', light: true, flat: true },

  /* ------------------------------------------------------- OLED и тёмные */
  oled:     { name: 'OLED',      group: 'oled', accent: '#FFFFFF', accent2: '#9AA0A6', bg: '#000000', flat: true },
  oledlime: { name: 'OLED lime', group: 'oled', accent: '#B6FF3C', accent2: '#39FF88', bg: '#000000', flat: true },
  oledblue: { name: 'OLED blue', group: 'oled', accent: '#3CA9FF', accent2: '#7C5CFF', bg: '#000000', flat: true },
  graphite: { name: 'Graphite',  group: 'oled', accent: '#9FB4C7', accent2: '#6E8296', bg: '#0E1114', flat: true },
  oledrose: { name: 'OLED rose', group: 'oled', accent: '#FF5C8A', accent2: '#FF9ABF', bg: '#000000', flat: true },
  oledamber:{ name: 'OLED amber', group: 'oled', accent: '#FFB638', accent2: '#FF7A3D', bg: '#000000', flat: true },
  oledcyan: { name: 'OLED cyan', group: 'oled', accent: '#2BE5FF', accent2: '#2BFFB8', bg: '#000000', flat: true },
  oledmono: { name: 'OLED paper', group: 'oled', accent: '#E8E4DA', accent2: '#A8A49A', bg: '#000000', flat: true },
  ink:      { name: 'Ink', group: 'oled', accent: '#5B8DEF', accent2: '#8E9BB3', bg: '#07080A', flat: true },
  oledgold: { name: 'OLED gold', group: 'oled', accent: '#E8C45C', accent2: '#C99A2E', bg: '#000000', flat: true },
  oledmint: { name: 'OLED mint', group: 'oled', accent: '#3CFFC1', accent2: '#2BE5FF', bg: '#000000', flat: true },
  oledviolet: { name: 'OLED violet', group: 'oled', accent: '#9A6BFF', accent2: '#D46CFF', bg: '#000000', flat: true },
  oledred:  { name: 'OLED red', group: 'oled', accent: '#FF3B3B', accent2: '#FF8A5C', bg: '#000000', flat: true },
  carbon:   { name: 'Carbon', group: 'oled', accent: '#C9CED6', accent2: '#8A919C', bg: '#0A0A0C', flat: true },

  /* ------------------------------------------ палитры «по мотивам» (community) */
  spotify:  { name: 'Spotify', group: 'community', accent: '#1DB954', accent2: '#1ED760', bg: '#121212', flat: true,
              note: 'Colour palette inspired by Spotify; not affiliated' },
  dracula:  { name: 'Dracula', group: 'community', accent: '#BD93F9', accent2: '#FF79C6', bg: '#282A36',
              note: 'Dracula theme palette by Zeno Rocha and contributors' },
  nord:     { name: 'Nord', group: 'community', accent: '#88C0D0', accent2: '#81A1C1', bg: '#2E3440', flat: true,
              note: 'Nord palette by Arctic Ice Studio' },
  gruvbox:  { name: 'Gruvbox', group: 'community', accent: '#FABD2F', accent2: '#FE8019', bg: '#282828', flat: true,
              note: 'Gruvbox palette by morhetz' },
  catppuccin: { name: 'Catppuccin Mocha', group: 'community', accent: '#CBA6F7', accent2: '#F5C2E7', bg: '#1E1E2E',
              note: 'Catppuccin palette by the Catppuccin org' },
  tokyonight: { name: 'Tokyo Night', group: 'community', accent: '#7AA2F7', accent2: '#BB9AF7', bg: '#1A1B26',
              note: 'Tokyo Night palette by enkia' },
  rosepine: { name: 'Rosé Pine', group: 'community', accent: '#EBBCBA', accent2: '#C4A7E7', bg: '#191724',
              note: 'Rosé Pine palette by the Rosé Pine team' },
  everforest: { name: 'Everforest', group: 'community', accent: '#A7C080', accent2: '#DBBC7F', bg: '#2D353B', flat: true,
              note: 'Everforest palette by sainnhe' },
  solard:   { name: 'Solarized Dark', group: 'community', accent: '#268BD2', accent2: '#2AA198', bg: '#002B36', flat: true,
              note: 'Palette by Ethan Schoonover' },
  winamp:   { name: 'Winamp', group: 'community', accent: '#00FF00', accent2: '#FFCC00', bg: '#1A1A1A', flat: true,
              note: 'A nod to the classic Nullsoft player' },
  synthwave: { name: 'Synthwave', group: 'community', accent: '#FF2E97', accent2: '#00E5FF', bg: '#1A0B2E',
              note: 'Retro 80s palette' },
  vinyl:    { name: 'Vinyl', group: 'community', accent: '#E0C097', accent2: '#B85C38', bg: '#12100E', flat: true,
              note: 'Warm analogue palette' },
  monokai:  { name: 'Monokai', group: 'community', accent: '#A6E22E', accent2: '#F92672', bg: '#272822', flat: true,
              note: 'Monokai palette by Wimer Hazenberg' },
  onedark:  { name: 'One Dark', group: 'community', accent: '#61AFEF', accent2: '#C678DD', bg: '#282C34', flat: true,
              note: 'Palette inspired by Atom One Dark' },
  ayu:      { name: 'Ayu Mirage', group: 'community', accent: '#FFCC66', accent2: '#5CCFE6', bg: '#1F2430', flat: true,
              note: 'Ayu palette by dempfi' },
  material: { name: 'Material Ocean', group: 'community', accent: '#80CBC4', accent2: '#C792EA', bg: '#0F111A', flat: true,
              note: 'Material theme palette by Mattia Astorino' },
  kanagawa: { name: 'Kanagawa', group: 'community', accent: '#7E9CD8', accent2: '#E6C384', bg: '#1F1F28', flat: true,
              note: 'Kanagawa palette by rebelot' },
  nightowl: { name: 'Night Owl', group: 'community', accent: '#82AAFF', accent2: '#C792EA', bg: '#011627', flat: true,
              note: 'Night Owl palette by Sarah Drasner' },
  palenight:{ name: 'Palenight', group: 'community', accent: '#C792EA', accent2: '#89DDFF', bg: '#292D3E',
              note: 'Palenight palette by Olaolu Olawuyi' },
  horizon:  { name: 'Horizon', group: 'community', accent: '#E95678', accent2: '#FAB795', bg: '#1C1E26',
              note: 'Horizon palette by Jonathan Olaleye' },
  poimandres: { name: 'Poimandres', group: 'community', accent: '#5DE4C7', accent2: '#ADD7FF', bg: '#1B1E28', flat: true,
              note: 'Poimandres palette by Daniel Sternlicht' },
  cyberpunk: { name: 'Cyberpunk', group: 'community', accent: '#FCEE09', accent2: '#00F0FF', bg: '#0D0221',
              note: 'Neon tribute palette' },
  moonlight: { name: 'Moonlight', group: 'community', accent: '#82AAFF', accent2: '#C099FF', bg: '#212337',
              note: 'Moonlight palette by Atom Material' },
  vitesse:  { name: 'Vitesse', group: 'community', accent: '#4D9375', accent2: '#BD976A', bg: '#121212', flat: true,
              note: 'Vitesse palette by Anthony Fu' },
  iceberg:  { name: 'Iceberg', group: 'community', accent: '#84A0C6', accent2: '#A093C7', bg: '#161821', flat: true,
              note: 'Iceberg palette by cocopon' },
  zenburn:  { name: 'Zenburn', group: 'community', accent: '#DFAF8F', accent2: '#8CD0D3', bg: '#3F3F3F', flat: true,
              note: 'Zenburn palette by Jani Nurminen' },
  gruvlight: { name: 'Gruvbox Light', group: 'community', accent: '#B57614', accent2: '#AF3A03', bg: '#FBF1C7', light: true, flat: true,
              note: 'Gruvbox palette by morhetz' },
  macchiato: { name: 'Catppuccin Macchiato', group: 'community', accent: '#C6A0F6', accent2: '#F5BDE6', bg: '#24273A',
              note: 'Catppuccin palette by the Catppuccin org' },
  tokyostorm: { name: 'Tokyo Night Storm', group: 'community', accent: '#7AA2F7', accent2: '#9ECE6A', bg: '#24283B',
              note: 'Tokyo Night palette by enkia' },
  rosemoon: { name: 'Rosé Pine Moon', group: 'community', accent: '#C4A7E7', accent2: '#EA9A97', bg: '#232136',
              note: 'Rosé Pine palette by the Rosé Pine team' },
  nordstorm: { name: 'Nord Aurora', group: 'community', accent: '#A3BE8C', accent2: '#EBCB8B', bg: '#3B4252', flat: true,
              note: 'Nord palette by Arctic Ice Studio' },
  dracpro:  { name: 'Dracula Pro', group: 'community', accent: '#9580FF', accent2: '#FF80BF', bg: '#22212C',
              note: 'Dracula theme palette by Zeno Rocha and contributors' },
  dosbox:   { name: 'DOS', group: 'community', accent: '#AAAAAA', accent2: '#55FF55', bg: '#0000AA', flat: true,
              note: 'A nod to the text-mode era' },
  amberterm: { name: 'Amber terminal', group: 'community', accent: '#FFB000', accent2: '#FF8000', bg: '#140C00', flat: true,
              note: 'Classic phosphor monitor' },
  greenterm: { name: 'Green terminal', group: 'community', accent: '#33FF33', accent2: '#00CC66', bg: '#001100', flat: true,
              note: 'Classic phosphor monitor' },
  lofi:     { name: 'Lo-fi', group: 'community', accent: '#D98C8C', accent2: '#8CA9D9', bg: '#1A1620', flat: true,
              note: 'Warm study-beats palette' },
  cassette: { name: 'Cassette', group: 'community', accent: '#E8A33D', accent2: '#4FA9A0', bg: '#1C1A17', flat: true,
              note: 'Tape deck palette' },
};

/* Reference-driven UI tokens; preserve old IDs for saved selections. */
const REFERENCE_PALETTES = {
  "spotify": {
    "referenceUrl": "https://developer.spotify.com/documentation/design",
    "text": "#FFFFFF",
    "muted": "#B3B3B3",
    "surface": "#1F1F1F",
    "surface2": "#292929",
    "flat": true,
    "accent": "#1ED760",
    "accent2": "#B3B3B3",
    "note": "Unofficial UI adaptation · Spotify design guidelines"
  },
  "winamp": {
    "referenceUrl": "https://raw.githubusercontent.com/captbaritone/webamp/master/README.md",
    "text": "#E4E4CB",
    "muted": "#B9B9AB",
    "surface": "#25263A",
    "surface2": "#36374D",
    "flat": true,
    "bg": "#23233B",
    "accent": "#38EF59",
    "accent2": "#E9D66D",
    "note": "Unofficial tribute · classic player chrome, not a Winamp skin"
  },
  "github": {
    "referenceUrl": "https://primer.style/product/getting-started/foundations/color-usage/",
    "text": "#1F2328",
    "muted": "#59636E",
    "surface": "#F6F8FA",
    "surface2": "#EFF2F5",
    "flat": true
  },
  "dracula": {
    "referenceUrl": "https://raw.githubusercontent.com/dracula/dracula-theme/master/README.md",
    "text": "#F8F8F2",
    "muted": "#BCC1D2",
    "surface": "#303240",
    "surface2": "#44475A",
    "flat": true
  },
  "nord": {
    "referenceUrl": "https://raw.githubusercontent.com/nordtheme/nord/develop/src/nord.css",
    "text": "#ECEFF4",
    "muted": "#C4CBD6",
    "surface": "#3B4252",
    "surface2": "#434C5E",
    "flat": true
  },
  "nordl": {
    "referenceUrl": "https://raw.githubusercontent.com/nordtheme/nord/develop/src/nord.css",
    "text": "#2E3440",
    "muted": "#4C566A",
    "surface": "#E5E9F0",
    "surface2": "#D8DEE9",
    "flat": true
  },
  "nordstorm": {
    "referenceUrl": "https://raw.githubusercontent.com/nordtheme/nord/develop/src/nord.css",
    "text": "#ECEFF4",
    "muted": "#D8DEE9",
    "surface": "#434C5E",
    "surface2": "#4C566A",
    "flat": true
  },
  "gruvbox": {
    "referenceUrl": "https://raw.githubusercontent.com/morhetz/gruvbox/master/colors/gruvbox.vim",
    "text": "#EBDBB2",
    "muted": "#BDAE93",
    "surface": "#3C3836",
    "surface2": "#504945",
    "flat": true
  },
  "gruvlight": {
    "referenceUrl": "https://raw.githubusercontent.com/morhetz/gruvbox/master/colors/gruvbox.vim",
    "text": "#3C3836",
    "muted": "#665C54",
    "surface": "#F2E5BC",
    "surface2": "#EBDBB2",
    "flat": true
  },
  "catppuccin": {
    "referenceUrl": "https://raw.githubusercontent.com/catppuccin/palette/main/palette.json",
    "text": "#CDD6F4",
    "muted": "#BAC2DE",
    "surface": "#181825",
    "surface2": "#313244",
    "flat": true
  },
  "latte": {
    "referenceUrl": "https://catppuccin.com/palette/",
    "text": "#4C4F69",
    "muted": "#5C5F77",
    "surface": "#E6E9EF",
    "surface2": "#DCE0E8",
    "flat": true
  },
  "macchiato": {
    "referenceUrl": "https://catppuccin.com/palette/",
    "text": "#CAD3F5",
    "muted": "#B8C0E0",
    "surface": "#1E2030",
    "surface2": "#363A4F",
    "flat": true
  },
  "tokyonight": {
    "referenceUrl": "https://raw.githubusercontent.com/enkia/tokyo-night-vscode-theme/master/README.md",
    "text": "#C0CAF5",
    "muted": "#A9B1D6",
    "surface": "#16161E",
    "surface2": "#24283B",
    "flat": true
  },
  "tokyostorm": {
    "referenceUrl": "https://raw.githubusercontent.com/enkia/tokyo-night-vscode-theme/master/README.md",
    "text": "#C0CAF5",
    "muted": "#A9B1D6",
    "surface": "#1F2335",
    "surface2": "#292E42",
    "flat": true
  },
  "rosepine": {
    "referenceUrl": "https://raw.githubusercontent.com/rose-pine/neovim/main/lua/rose-pine/palette.lua",
    "text": "#E0DEF4",
    "muted": "#B2ACC4",
    "surface": "#1F1D2E",
    "surface2": "#26233A",
    "flat": true
  },
  "rosemoon": {
    "referenceUrl": "https://raw.githubusercontent.com/rose-pine/neovim/main/lua/rose-pine/palette.lua",
    "text": "#E0DEF4",
    "muted": "#B4ACC9",
    "surface": "#2A273F",
    "surface2": "#393552",
    "flat": true
  },
  "dawn": {
    "referenceUrl": "https://raw.githubusercontent.com/rose-pine/neovim/main/lua/rose-pine/palette.lua",
    "text": "#575279",
    "muted": "#6B6584",
    "surface": "#FFFAF3",
    "surface2": "#F2E9E1",
    "flat": true
  },
  "everforest": {
    "referenceUrl": "https://raw.githubusercontent.com/sainnhe/everforest/master/palette.md",
    "text": "#D3C6AA",
    "muted": "#B7B29B",
    "surface": "#343F44",
    "surface2": "#3D484D",
    "flat": true
  },
  "solarl": {
    "referenceUrl": "https://ethanschoonover.com/solarized/",
    "text": "#073642",
    "muted": "#586E75",
    "surface": "#EEE8D5",
    "surface2": "#E7DFC6",
    "flat": true
  },
  "solard": {
    "referenceUrl": "https://ethanschoonover.com/solarized/",
    "text": "#EEE8D5",
    "muted": "#93A1A1",
    "surface": "#073642",
    "surface2": "#10404B",
    "flat": true
  },
  "monokai": {
    "referenceUrl": "https://monokai.pro/",
    "text": "#F8F8F2",
    "muted": "#B7B5A6",
    "surface": "#303129",
    "surface2": "#3E3D32",
    "flat": true
  },
  "onedark": {
    "referenceUrl": "https://raw.githubusercontent.com/atom/one-dark-syntax/master/styles/colors.less",
    "text": "#ABB2BF",
    "muted": "#A4ADBA",
    "surface": "#21252B",
    "surface2": "#2C313A",
    "flat": true
  },
  "onelight": {
    "referenceUrl": "https://raw.githubusercontent.com/atom/one-light-syntax/master/styles/colors.less",
    "text": "#383A42",
    "muted": "#666972",
    "surface": "#F0F0F0",
    "surface2": "#E5E5E6",
    "flat": true
  },
  "ayu": {
    "referenceUrl": "https://raw.githubusercontent.com/ayu-theme/ayu-colors/master/themes/mirage.yaml",
    "text": "#CCCAC2",
    "muted": "#A9A9A2",
    "surface": "#242936",
    "surface2": "#2D3343",
    "flat": true,
    "accent": "#FFCC66"
  },
  "material": {
    "referenceUrl": "https://material-theme.com/docs/reference/color-palette",
    "text": "#D8DDEB",
    "muted": "#9DA4B9",
    "surface": "#181A1F",
    "surface2": "#1F2233",
    "flat": true,
    "name": "Material · Deep Ocean",
    "accent": "#84FFFF",
    "note": "UI adaptation · Material Theme Deep ocean reference"
  },
  "kanagawa": {
    "referenceUrl": "https://raw.githubusercontent.com/rebelot/kanagawa.nvim/master/lua/kanagawa/colors.lua",
    "text": "#DCD7BA",
    "muted": "#C0BBA2",
    "surface": "#16161D",
    "surface2": "#2A2A37",
    "flat": true
  },
  "nightowl": {
    "referenceUrl": "https://raw.githubusercontent.com/sdras/night-owl-vscode-theme/main/themes/Night%20Owl-color-theme.json",
    "text": "#D6DEEB",
    "muted": "#A8B5C3",
    "surface": "#071E30",
    "surface2": "#0B2942",
    "flat": true
  },
  "palenight": {
    "referenceUrl": "https://raw.githubusercontent.com/whizkydee/vscode-palenight-theme/master/themes/palenight.json",
    "text": "#A6ACCD",
    "muted": "#B5BDD8",
    "surface": "#232534",
    "surface2": "#34374E",
    "flat": true
  },
  "horizon": {
    "referenceUrl": "https://raw.githubusercontent.com/jolaleye/horizon-theme/master/README.md",
    "text": "#D5D8DA",
    "muted": "#ADB4BE",
    "surface": "#232530",
    "surface2": "#2E303E",
    "flat": true
  },
  "poimandres": {
    "referenceUrl": "https://raw.githubusercontent.com/drcmda/poimandres-theme/main/themes/poimandres-color-theme.json",
    "text": "#A6ACCD",
    "muted": "#B3BAD9",
    "surface": "#1B1E28",
    "surface2": "#303340",
    "flat": true,
    "note": "UI adaptation · drcmda/poimandres-theme"
  },
  "moonlight": {
    "referenceUrl": "https://raw.githubusercontent.com/atomiks/moonlight-vscode-theme/master/README.md",
    "text": "#C8D3F5",
    "muted": "#A9B8E8",
    "surface": "#1E2030",
    "surface2": "#2F334D",
    "flat": true,
    "note": "UI adaptation · atomiks/moonlight-vscode-theme"
  },
  "vitesse": {
    "referenceUrl": "https://raw.githubusercontent.com/antfu/vscode-theme-vitesse/main/README.md",
    "text": "#DBD7CA",
    "muted": "#B0ADA3",
    "surface": "#181818",
    "surface2": "#222222",
    "flat": true
  },
  "iceberg": {
    "referenceUrl": "https://raw.githubusercontent.com/cocopon/iceberg.vim/master/colors/iceberg.vim",
    "text": "#C6C8D1",
    "muted": "#A4AEC6",
    "surface": "#1E2132",
    "surface2": "#272C42",
    "flat": true
  },
  "zenburn": {
    "referenceUrl": "https://raw.githubusercontent.com/jnurmine/Zenburn/master/colors/zenburn.vim",
    "text": "#DCDCCC",
    "muted": "#C0C0AA",
    "surface": "#383838",
    "surface2": "#4F4F4F",
    "flat": true
  },
  "dracpro": {
    "name": "Violet Night",
    "note": "Original violet palette · not Dracula Pro",
    "flat": true
  }
};
Object.entries(REFERENCE_PALETTES).forEach(([id,v])=>Object.assign(THEME_LIBRARY[id],v));
function applyReferencePalette() {
 const body=document.body,style=body.style;
 if(body.dataset.palette11){['--text','--muted','--surface','--surface-2','--line','--on-fill','--sk-standard-on-accent'].forEach(k=>style.removeProperty(k));delete body.dataset.palette11;}
 const x=THEME_LIBRARY[S.theme];if(S.sketch||!x||!x.text)return;
 body.dataset.palette11=S.theme;
 style.setProperty('--text',x.text);style.setProperty('--muted',x.muted);
 style.setProperty('--surface',x.surface);style.setProperty('--surface-2',x.surface2);
 style.setProperty('--line',skMix(x.bg,x.text,.25));style.setProperty('--on-fill',skOnColor(S.accent));style.setProperty('--sk-standard-on-accent',skOnColor(S.accent));
}

/* Скины рисованной темы — полноценные темы каталога: их видно в списке,
   по ним работает поиск, и выбор такой темы включает нужный скин. */
if (typeof SKETCH_SKINS !== 'undefined') {
  Object.entries(SKETCH_SKINS).forEach(([id, skin]) => {
    if (skin.avatar || skin.family === 'vtuber' || id.startsWith('vt-')) return;
    THEME_LIBRARY['theme:' + id] = {
      name: skin.name,
      skinName: skin.name,
      group: skin.avatar?'vtuber':'community',
      accent: skin.sky, accent2: skin.gold, bg: skin.paper,
      light: !skin.dark, sketch: false, skin: id, note: '', avatar: skin.avatar, text:skin.ink,muted:skMix(skin.ink,skin.paper,.30),surface:skMix(skin.paper,skin.ink,.055),surface2:skMix(skin.paper,skin.ink,.10),referenceImage:skin.referenceImage,channelUrl:skin.channelUrl,channelAvatarStatus:skin.channelAvatarStatus,
    };
  });
}

/* Имя темы на языке интерфейса. Имя скина рисованной темы склеено из двух
   частей («Sketch · Sakura»), и целиком такого ключа в словаре нет — раньше
   все рисованные темы в каталоге оставались английскими. */
function themeName(theme) {
  if (!theme) return '';
  if (theme.sketch && theme.skinName) return 'Sketch · ' + theme.skinName;
  return theme.name;
}

const THEME_GROUPS = [
  ['all', 'All'],
  ['kryonyx', 'Kryo'],
  ['community', 'Community'],
  ['light', 'Light'],
  ['oled', 'OLED'],
];

/* Экран «Темы»: поиск, группы и сетка превью. */
const Themes = {
  group: 'all',
  query: '',

  build() {
    if (!$('mSettings')?.classList.contains('on')) { this._deferredBuild = true; return; }
    this._deferredBuild = false;
    const groups = $('themeGroups');
    if (groups) {
      groups.innerHTML = '';
      THEME_GROUPS.forEach(([id, label]) => {
        const chip = el('button', 'chip' + (this.group === id ? ' on' : ''), t(label));
        chip.onclick = () => { this.group = id; this.build(); };
        groups.appendChild(chip);
      });
      requestAnimationFrame(() => {
        const active = groups.querySelector('.chip.on');
        if (active && groups.clientWidth > 0 && groups.scrollWidth > groups.clientWidth) {
          groups.scrollLeft += active.getBoundingClientRect().left - groups.getBoundingClientRect().left - 8;
        }
      });
    }

    const list = $('themeList');
    if (!list) return;
    const query = this.query.trim().toLowerCase();
    list.innerHTML = '';
    let shown = 0;
    Object.entries(THEME_LIBRARY).forEach(([id, theme]) => {
      if (theme.group === 'hidden') return;
      if (this.group !== 'all' && theme.group !== this.group) return;
      // Искать можно и по переводу названия, и по исходному имени.
      const haystack = `${theme.name} ${themeName(theme)} ${theme.note || ''} ${t(theme.note || '')}`;
      if (query && !haystack.toLowerCase().includes(query)) return;
      shown++;
      const node = el('button', 'theme' + (S.theme === id ? ' on' : ''));
      node.setAttribute('aria-pressed', String(S.theme === id));
      node.type = 'button';
      node.dataset.themeId = id;
      node.setAttribute('aria-label', themeName(theme));
      const preview = el('div', 'sw-prev theme-preview35');
      preview.setAttribute('aria-hidden', 'true');
      const ink = theme.text || (theme.light ? '#202126' : '#f1f1f5');
      const surface = theme.surface || skMix(theme.bg, ink, .09);
      [['--tp-bg',theme.bg],['--tp-ink',ink],['--tp-surface',surface],['--tp-accent',theme.accent],['--tp-accent2',theme.accent2 || theme.accent]].forEach(([k,v])=>preview.style.setProperty(k,v));
      const screen = el('span', 'theme-screen35');
      const screenshot = el('img', 'theme-ui35');
      screenshot.src = '/img/theme-ui/' + id.replace(/[^a-z0-9_-]/gi, '-') + '.webp';
      screenshot.alt = ''; screenshot.loading = 'lazy'; screenshot.decoding = 'async';
      screenshot.onerror = () => { screenshot.remove(); screen.append(el('span', 'theme-fallback35', t('Preview unavailable'))); };
      screen.append(screenshot); preview.append(screen);
      const side = el('span', 'theme-side35');
      if (theme.referenceImage) {
        preview.classList.add('theme-character35');
        const avatar = el('img', 'theme-avatar35');
        avatar.src = theme.referenceImage.replace('/theme-refs/', '/theme-cards/');
        avatar.alt = ''; avatar.title = theme.channelAvatarStatus === 'unresolved' ? t('Channel avatar unavailable') : theme.skinName || theme.name; avatar.loading = 'lazy'; avatar.decoding = 'async';
        avatar.onerror = () => { avatar.remove(); side.classList.add('no-avatar35'); };
        side.append(avatar, el('span', 'theme-kind35', 'VTuber'));
        if (theme.channelAvatarStatus === 'unresolved') side.title = t('Channel avatar unavailable');
      } else {
        const mode = el('span', 'theme-mode35'); mode.innerHTML = icon('palette'); side.append(mode);
        side.append(el('span', 'theme-kind35', t(theme.light ? 'Light' : 'Dark')));
      }
      const swatches = el('span', 'theme-palette35');
      [theme.bg, surface, ink, theme.accent, theme.accent2 || theme.accent].forEach(color => {
        const swatch = el('i'); swatch.style.backgroundColor = color; swatches.append(swatch);
      });
      side.append(swatches); preview.append(side); node.append(preview);
      const selected = el('span', 'theme-check35', '✓');
      selected.setAttribute('aria-hidden', 'true'); node.append(selected);
      // Описательные названия палитр переводятся; имена брендов
      // просто остаются как есть — в словарях их нет.
      node.appendChild(el('span', 'theme-n', esc(themeName(theme))));
      if (theme.note) {
        // Подпись палитры переводится наравне с остальным интерфейсом.
        const note = t(theme.note);
        const hint = el('span', 'theme-h', esc(note));
        hint.title = note;
        node.appendChild(hint);
      }
      node.onclick = () => {
        useTheme(id);
        this.build();
        App.syncSettingsUI();
        if (typeof Sketch !== 'undefined') Sketch.build();
        toast(themeName(theme));
      };
      list.appendChild(node);
    });
    const counter = $('themeCount');
    if (!shown) { const empty = el('p', 'sk10-empty'); empty.textContent = t('No themes found. Try another name.'); list.appendChild(empty); }
    let source=$('sk11PaletteSource');if(!source){source=el('a','sk11-source');source.id='sk11PaletteSource';source.target='_blank';source.rel='noopener noreferrer';if(counter)counter.after(source);}
    const active=THEME_LIBRARY[S.theme];source.hidden=!active?.referenceUrl;if(active?.referenceUrl){source.href=active.referenceUrl;source.textContent=t('Selected palette reference ↗');}
    if (counter) counter.textContent = `${shown} / ${Object.values(THEME_LIBRARY).filter(x => x.group !== 'hidden').length}`;
  },

  bind() {
    const search = $('themeSearch');
    if (search) {
      search.addEventListener('input', debounce(() => {
        this.query = search.value;
        this.build();
      }, 120));
    }
    const random = $('themeRandom');
    if (random) {
      random.onclick = () => {
        const ids = Object.keys(THEME_LIBRARY)
          .filter(key => { const x = THEME_LIBRARY[key]; return x.group !== 'hidden' && (this.group === 'all' || x.group === this.group) && (!this.query.trim() || `${x.name} ${themeName(x)} ${x.note || ''}`.toLowerCase().includes(this.query.trim().toLowerCase())); });
        if (!ids.length) return toast(t('No matching themes'));
        const id = ids[Math.floor(Math.random() * ids.length)];
        useTheme(id);
        this.build();
        App.syncSettingsUI();
        if (typeof Sketch !== 'undefined') Sketch.build();
        toast(themeName(THEME_LIBRARY[id]));
      };
    }
  },
};
