/* Home v5 — real actions and honest empty states; no invented catalogue. */
'use strict';
const Home = {
  tr(en, ru) { return Studio.tr(en, ru); },
  init() {
    document.body.classList.add('home-v5');
    const sync = () => document.body.classList.toggle('home-active', $('vHome').classList.contains('on'));
    new MutationObserver(sync).observe($('vHome'), {attributes:true, attributeFilter:['class']}); sync();
    Studio.paintHero = rows => this.paintHero(rows);
    const quick = $('studioQuick'); quick.replaceChildren();
    [
      ['lib','Your library','Медиатека','Playlists, albums and saved tracks','Плейлисты, альбомы и сохранённое',()=>App.go('lib')],
      ['youtube','Clip studio','Студия клипов','Watch while the original downloads','Смотри, пока оригинал загружается',()=>Clips.open(Player.current)],
      ['note','Karaoke','Караоке','Lyrics, timing and your performance','Текст, тайминги и твоё исполнение',()=>{if(Player.current)App.openNow();else{App.go('search');toast(this.tr('Choose a track, then open karaoke.','Выбери трек, затем открой караоке.'));}}],
      ['heart','Liked tracks','Любимое','All your favourites in one place','Всё, что хочется слушать снова',()=>App.openLiked()]
    ].forEach(([ico,en,ru,descEn,descRu,fn],i)=>{
      const b=el('button','home-destination',`<span class="home-destination-icon home-tone-${i}">${icon(ico)}</span><span><strong data-ui-i18n>${this.tr(en,ru)}</strong><small data-ui-i18n>${this.tr(descEn,descRu)}</small></span>${icon('next','ic s')}`);
      b.onclick=fn;quick.appendChild(b);
    });
    const label=el('div','home-section-label',`<span data-ui-i18n>${this.tr('YOUR SPACE','ТВОЁ ПРОСТРАНСТВО')}</span>`);label.id='homeQuickLabel';quick.before(label);
    const apply=Studio.apply.bind(Studio); Studio.apply=()=>{apply();label.hidden=quick.hidden;};
    const recent=$('workspaceRecentTracks');
    const decorate=()=>{
      const empty=!!recent.querySelector('p');recent.classList.toggle('home-recent-empty',empty);
      if(empty&&!recent.querySelector('button')){
        const b=el('button','btn g',`${icon('search','ic s')}<span data-ui-i18n>${this.tr('Find a track','Найти первый трек')}</span>`);
        b.onclick=()=>{App.go('search');$('q').focus();};recent.appendChild(b);
      }
    };
    new MutationObserver(decorate).observe(recent,{childList:true});decorate();
    // Only mark the known neutral onboarding state. Errors remain visible.
    const rows=$('rows'); const markEmpty=()=>{
      const e=rows.querySelector(':scope > .empty');
      if(e && e.textContent.trim()===t('Nothing to show yet — find your first track and the picks will build themselves')) e.classList.add('home-neutral-empty');
    };new MutationObserver(markEmpty).observe(rows,{childList:true});
    const filter=$('workspaceSideFilter');
    if(filter){const b=el('button','home-new-playlist',`${icon('plus','ic s')}<span data-ui-i18n>${this.tr('New playlist','Новый плейлист')}</span>`);b.onclick=()=>{openModal('mNewPl');$('newPlName').focus();};filter.closest('.workspace-side-filter').after(b);}
    this.paintHero([]);Studio.apply();
  },
  paintHero(rows) {
    const oldInput=$('homeQuery'),previousQuery=oldInput?.value||'',hadFocus=document.activeElement===oldInput,selection=oldInput?[oldInput.selectionStart,oldInput.selectionEnd]:null;
    $('greet').textContent=this.tr('Your music. Your way.','Твоя музыка. Твой ритм.');
    const eyebrow=$('vHome').querySelector('.studio-page-head .studio-eyebrow');if(eyebrow)eyebrow.textContent=this.tr('HOME / KRYO','ГЛАВНАЯ / KRYO');
    const tracks=rows.flatMap(r=>r.unresolved||r.kind==='albums'||r.kind==='playlists'?[]:r.items||[]).filter(t=>t.id&&t.title);
    const track=Player.current||tracks[0];const box=$('studioHero');
    box.innerHTML=`<div class="home-search-copy"><span class="home-kicker" data-ui-i18n>${this.tr('PRESS PLAY ON YOUR DAY','НАЧНИ С ТОГО, ЧТО ЛЮБИШЬ')}</span><h2 data-ui-i18n>${this.tr('What shall we play?','Что включим сегодня?')}</h2><p data-ui-i18n>${this.tr('Find a song, explore an artist or paste a link.','Найди песню, открой исполнителя или вставь ссылку.')}</p><form class="home-search-form"><label class="sr-only" for="homeQuery" data-ui-i18n>${this.tr('Track, artist or link','Трек, исполнитель или ссылка')}</label><div class="home-search-field">${icon('search')}<input id="homeQuery" autocomplete="off" placeholder="${this.tr('Track, artist or link','Трек, исполнитель или ссылка')}"></div><button class="btn" type="submit" data-ui-i18n>${this.tr('Search','Найти')}</button></form></div><button class="home-feature ${track?'home-has-track':''}" type="button"><img alt="" src="/img/avatars/kryonyx-core.png"><span class="home-feature-copy"><small data-ui-i18n>${track?this.tr('READY TO PLAY','ВКЛЮЧАЙ И СЛУШАЙ'):this.tr('ONE PLAYER. MORE POSSIBILITIES.','ОДИН ПЛЕЕР. БОЛЬШЕ ВОЗМОЖНОСТЕЙ.')}</small><strong data-ui-i18n>${track?esc(track.title):this.tr('Music. Clips. Karaoke.','Музыка. Клипы. Караоке.')}</strong><span data-ui-i18n>${track?esc(track.artist||''):this.tr('Everything starts with your first track.','Всё начинается с твоего первого трека.')}</span></span><span class="home-feature-play">${icon(track?'play':'next','ic s')}</span></button>`;
    if(track){box.querySelector('.home-feature-copy strong').dataset.entityName='';box.querySelector('.home-feature-copy>span').dataset.entityName='';}
    const input=$('homeQuery');input.value=previousQuery;if(hadFocus){input.focus({preventScroll:true});if(selection)input.setSelectionRange(...selection);}input.setAttribute('aria-label',this.tr('Track, artist or link','Трек, исполнитель или ссылка'));input.setAttribute('enterkeyhint','search');box.querySelector('form').onsubmit=e=>{e.preventDefault();const q=input.value.trim();if(q)App.search(q);else input.focus();};
    const feature=box.querySelector('.home-feature');feature.onclick=()=>track?(Player.current?.id===track.id?Player.toggle():Player.play(track,tracks)):App.go('search');
    if(track)setImg(feature.querySelector('img'),track.thumbnail,240);
  }
};
