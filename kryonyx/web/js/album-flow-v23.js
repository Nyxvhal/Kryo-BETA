'use strict';
const albumLabels23={"ru": ["Цвета обложки", "Плавно переливающийся фон в цветах текущей обложки"], "es": ["Colores de la portada", "Fondo fluido con los colores de la portada actual"], "pt": ["Cores da capa", "Fundo fluido com as cores da capa atual"], "de": ["Coverfarben", "Sanft fließender Hintergrund in den Farben des aktuellen Covers"], "fr": ["Couleurs de la pochette", "Fond fluide aux couleurs de la pochette actuelle"], "it": ["Colori della copertina", "Sfondo fluido nei colori della copertina attuale"], "tr": ["Kapak renkleri", "Geçerli kapağın renklerinde yavaşça akan arka plan"], "pl": ["Kolory okładki", "Płynne tło w kolorach bieżącej okładki"], "uk": ["Кольори обкладинки", "Плавний перелив фону в кольорах поточної обкладинки"], "zh": ["封面流光", "随当前封面色彩缓缓流动的背景"], "ja": ["ジャケットの彩り", "現在のジャケットの色がゆっくり流れる背景"]};
for(const [lang,labels]of Object.entries(albumLabels23)){PACKS[lang]['Album flow']=labels[0];PACKS[lang]['Slow flowing colours sampled from the current artwork']=labels[1];}

const AlbumFlow23={
 paint(){const colors=CoverPalette23.forCover(Player.current?.thumbnail);colors.forEach((c,i)=>$('now')?.style.setProperty('--cover'+i,c));$('now')?.classList.toggle('flow-still23',!!S.noAnim||!Karaoke.playing||document.hidden);MiniPlayer.push();},
 init(){
  // One-time upgrade of the old default; keep deliberately selected alternative scenes.
  if(!S.albumFlowRev23){if(!S.karaokeStyle||S.karaokeStyle==='aurora'||S.karaokeStyle==='stage'||S.karaokeStyle==='albumflow'){S.karaokeStyle='aurora';}S.albumFlowRev23=true;saveSettings();}
  const toggle=Karaoke.setPlaying.bind(Karaoke);Karaoke.setPlaying=(...args)=>{const result=toggle(...args);this.paint();return result;};
  const volume=Player.setVolume.bind(Player);Player.setVolume=(...args)=>{const result=volume(...args);MiniPlayer.push();return result;};
  addEventListener('kryonyx:coverpalette',()=>this.paint());document.addEventListener('visibilitychange',()=>this.paint());
  const apply=App.applyKaraoke.bind(App);App.applyKaraoke=(...args)=>{const result=apply(...args);this.paint();return result;};
  this.paint();App.applyKaraoke();document.body.classList.add('ui-v23');
 }
};
const boot23=App.boot.bind(App);App.boot=async function(...args){await boot23(...args);AlbumFlow23.init();};
