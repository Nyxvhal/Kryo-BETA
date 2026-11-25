/* Personal quick picks; the shelves below still come from provider radio/taste ranking. */
'use strict';
const HomePicks20={
 items:[],mode:'all',
 tr(en,ru){return LANG==='ru'?ru:t(en);},
 init(){const tr=this.tr.bind(this),box=el('section','home-picks20');box.id='homePicks20';box.innerHTML=`<div class="home-rec20"><div><h2 data-ui-i18n>${tr('Picked for you','Твоя волна')}</h2><p data-ui-i18n>${tr('Your history and favourites, with discoveries from related-track radio below.','История и любимые треки здесь, открытия из радио похожих треков — ниже.')}</p></div><button class="btn g" id="homePicksMix">${icon('play','ic s f')}${tr('Play my mix','Включить мой микс')}</button></div><div class="home-rec20-filters" role="group" aria-label="${tr('Recommendations','Рекомендации')}"></div><div id="homePicksTracks"></div><p id="homePicksNote" class="muted" role="status"></p>`;$('studioHero').before(box);
 for(const [mode,label]of [['all',tr('For you','Для тебя')],['discover',tr('Discoveries','Открытия')],['familiar',tr('Listen again','Послушать снова')]]){const b=el('button','chip',label);b.dataset.mode=mode;b.onclick=()=>{this.mode=mode;this.render();};box.querySelector('.home-rec20-filters').append(b);}
 $('homePicksMix').onclick=()=>$('bMix').click();const navigate=App.go.bind(App);App.go=(view,...args)=>{const result=navigate(view,...args);if(view==='home')this.load();return result;};
 const hero=Studio.paintHero.bind(Studio);Studio.paintHero=rows=>{hero(rows);this.render();};this.load();
 },
 async load(){try{const d=await api('/api/recommend/quick',{timeout:8000});this.items=d.items||[];this.render();}catch{$('homePicksNote').textContent=this.tr('Could not load your quick picks.','Не удалось загрузить твою волну.');}},
 render(){if(!$('homePicksTracks'))return;const all=[...this.items,...Studio.homeData.filter(r=>!['albums','playlists'].includes(r.kind)&&!r.unresolved).flatMap(r=>r.items||[])];const familiar=new Set(this.items.map(t=>t.id));let tracks=all.filter(t=>t.id&&t.title&&(this.mode==='all'||(this.mode==='familiar'?familiar.has(t.id):!familiar.has(t.id))));const seen=new Set();tracks=tracks.filter(t=>{const key=[t.artist,t.title].join('|').toLocaleLowerCase();if(seen.has(key)||seen.has(t.id))return false;seen.add(key);seen.add(t.id);return true;}).slice(0,8);
 $('homePicksTracks').replaceChildren(...tracks.map((t,i)=>Views.trackRow(t,i,tracks)));$('homePicksNote').textContent=tracks.length?'':this.tr('Play or like some songs to build your own wave. New discoveries also depend on source availability.','Послушай или лайкни несколько песен — появится твоя волна. Новые открытия также зависят от доступности источников.');for(const b of document.querySelectorAll('.home-rec20-filters button'))b.setAttribute('aria-pressed',String(b.dataset.mode===this.mode));
 }
};
