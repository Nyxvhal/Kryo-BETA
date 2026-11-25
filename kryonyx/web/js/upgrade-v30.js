/* v30: ordinary themes, low-cost interaction polish and clean-scene controls. */
'use strict';
const Upgrade30={
 idleTimer:0,
 labels:['Aurora contrast','Aurora frame rate','Controls hide delay','Lyric scale','Sidebar width','Panel roundness','Interface spacing','Player customization','Reset customization'],
 translations:{
 ru:['Контраст авроры','Частота кадров авроры','Задержка скрытия кнопок','Масштаб текста караоке','Ширина боковой панели','Скругление панелей','Отступы интерфейса','Настройка плеера','Сбросить настройку'],
 es:['Contraste de aurora','Fotogramas de aurora','Espera para ocultar controles','Escala de letras','Ancho lateral','Redondeo de paneles','Espaciado de interfaz','Personalizar reproductor','Restablecer ajustes'],
 pt:['Contraste da aurora','Quadros da aurora','Tempo para ocultar controles','Escala das letras','Largura lateral','Cantos dos painéis','Espaçamento da interface','Personalizar player','Redefinir ajustes'],
 de:['Aurora-Kontrast','Aurora-Bildrate','Bedienelemente ausblenden nach','Liedtextgröße','Seitenleistenbreite','Panel-Rundung','Oberflächenabstände','Player anpassen','Anpassungen zurücksetzen'],
 fr:['Contraste de l’aurore','Images par seconde de l’aurore','Délai de masquage des commandes','Taille des paroles','Largeur latérale','Arrondi des panneaux','Espacement de l’interface','Personnaliser le lecteur','Réinitialiser les réglages'],
 it:['Contrasto aurora','Fotogrammi aurora','Ritardo scomparsa comandi','Scala dei testi','Larghezza laterale','Angoli dei pannelli','Spaziatura interfaccia','Personalizza lettore','Ripristina impostazioni'],
 tr:['Aurora kontrastı','Aurora kare hızı','Denetimleri gizleme süresi','Şarkı sözü ölçeği','Kenar çubuğu genişliği','Panel yuvarlaklığı','Arayüz aralığı','Oynatıcıyı özelleştir','Ayarları sıfırla'],
 pl:['Kontrast zorzy','Klatki zorzy','Czas ukrycia przycisków','Skala tekstu','Szerokość paska bocznego','Zaokrąglenie paneli','Odstępy interfejsu','Dostosuj odtwarzacz','Resetuj ustawienia'],
 uk:['Контраст аврори','Частота кадрів аврори','Затримка приховування кнопок','Масштаб тексту караоке','Ширина бічної панелі','Заокруглення панелей','Відступи інтерфейсу','Налаштування плеєра','Скинути налаштування'],
 zh:['极光对比度','极光帧率','控件隐藏延迟','歌词缩放','侧栏宽度','面板圆角','界面间距','自定义播放器','重置自定义'],
 ja:['オーロラのコントラスト','オーロラのフレームレート','操作ボタンを隠すまでの時間','歌詞のサイズ','サイドバーの幅','パネルの角丸','画面の間隔','プレーヤーをカスタマイズ','カスタマイズをリセット']
 },
 settings:[['auroraContrast30',0,.6,1.6,.05,1.15],['auroraFps30',1,24,60,6,30],['idleDelay30',2,2,10,1,3],['lyricScale30',3,.75,1.25,.05,1],['sidebarWidth30',4,190,320,10,232],['panelRadius30',5,0,24,2,14],['interfaceSpace30',6,8,24,2,14]],
 migrate(){
  if(S.theme==='sketch')S.theme='theme:'+(S.sketchSkin||'saba');
  if(String(S.theme).startsWith('sketch:')){const id=String(S.theme).replace('sketch:','theme:');if(THEMES[id]){S.theme=id;const v=THEMES[id];Object.assign(S,{accent:v.accent,accent2:v.accent2,bg:v.bg,light:!!v.light});}}
  S.sketch=false;
  if(!S.upgrade30){S.upgrade30=true;saveSettings();}
 },
 apply(){for(const [key,,min,max,,def]of this.settings){const v=Number(S[key]);S[key]=Number.isFinite(v)?Math.max(min,Math.min(max,v)):def;}const st=document.documentElement.style;for(const [key,css,unit,def]of [['sidebarWidth30','--sidebar-width30','px',232],['panelRadius30','--panel-radius30','px',14],['interfaceSpace30','--space30','px',14],['lyricScale30','--lyric-scale30','',1]])st.setProperty(css,S[key]+unit);FluidCover24.sync();},
 wake(){clearTimeout(this.idleTimer);$('now')?.classList.remove('idle30');},
 refreshLabels(){document.querySelectorAll('[data-label30]').forEach(n=>{n.textContent=t(this.labels[+n.dataset.label30]);});for(const [id,key]of [['sceneSettings30','Settings'],['sceneExit30','Close'],['sceneFull30','Fullscreen']]){const b=$(id);if(b){b.title=t(key);b.setAttribute('aria-label',t(key));}}},
 init(){
  this.migrate();
  delete $('now').dataset.performance; $('ui9StageSkin')?.remove(); // Appearance lives only in Settings, not in karaoke.
  $('albumTop24')?.remove();
  const top=el('div','scene-tools30');top.id='sceneTools30';
  for(const [id,key,ico,action]of [['sceneSettings30','Settings','gear',()=>{Workspace.openSettings();App.openPane('karaoke');}],['sceneFull30','Fullscreen','expand',()=>App.fullscreen()],['sceneExit30','Close','close',()=>$('nClose').click()]]){const b=el('button','ib',icon(ico));b.type='button';b.id=id;b.title=t(key);b.setAttribute('aria-label',t(key));b.onclick=action;top.append(b);}
  $('now').append(top);$('now').addEventListener('pointermove',()=>this.wake(),{passive:true});$('now').addEventListener('pointerdown',()=>this.wake(),{passive:true});$('now').addEventListener('keydown',()=>this.wake());$('now').addEventListener('focusin',()=>this.wake());
  const open=App.openNow.bind(App);App.openNow=(...a)=>{const v=open(...a);this.wake();Atmo.kick();return v;};
  const close=$('nClose').onclick;$('nClose').onclick=(...a)=>{clearTimeout(this.idleTimer);$('now').classList.remove('idle30');const v=close?.(...a);Atmo.kick();return v;};
  const host=document.querySelector('.pane[data-pane="workspace"]')||document.querySelector('.pane[data-pane="karaoke"]');
  const section=el('section','customize30');section.id='customize30';const heading=el('h3');heading.dataset.label30='7';section.append(heading);
  for(const [key,label,min,max,step,def]of this.settings){const row=el('label','customize-row30'),name=el('span'),out=el('output'),input=el('input');name.dataset.label30=label;input.type='range';input.id=key;input.min=min;input.max=max;input.step=step;input.value=S[key]??def;input.setAttribute('aria-labelledby',key+'Label');name.id=key+'Label';out.value=input.value;input.oninput=()=>{S[key]=+input.value;out.value=input.value;this.apply();if(key==='idleDelay30')this.wake();};input.onchange=()=>saveSettings();row.append(name,out,input);section.append(row);}
  const reset=el('button','btn g');reset.dataset.label30='8';reset.onclick=()=>{this.settings.forEach(([key,,,,,def])=>{S[key]=def;$(key).value=def;$(key).previousElementSibling.value=def;});this.apply();saveSettings();};section.append(reset);host?.append(section);
  const lang=App.afterLangChange.bind(App);App.afterLangChange=(...a)=>{const v=lang(...a);this.refreshLabels();return v;};
  document.addEventListener('visibilitychange',()=>{if(document.hidden)Karaoke.stop();else if($('now').classList.contains('on'))Karaoke.start();});
  new MutationObserver(()=>{if(!$('now').classList.contains('on'))Karaoke.stop();}).observe($('now'),{attributes:true,attributeFilter:['class']});
  this.apply();this.refreshLabels();applyTheme();Themes.build();this.wake();document.body.classList.add('ui-v30');
 }
};
for(const [lang,values]of Object.entries(Upgrade30.translations))for(let i=0;i<values.length;i++)PACKS[lang][Upgrade30.labels[i]]=values[i];
// Migrate before any boot stage applies a saved legacy theme.
const applyTheme30=applyTheme;applyTheme=function(...args){Upgrade30.migrate();return applyTheme30(...args);};
const openPane30=App.openPane.bind(App);App.openPane=(name,...args)=>openPane30(name==='sketch'?'themes':name,...args);
// Do not re-create hundreds of lyric nodes for unrelated preference toggles.
const render30=Karaoke.render.bind(Karaoke);Karaoke.render=function(...args){const key=JSON.stringify([this.trackId,this.synced,this.lines,S.karaokeDots]);if(this.renderKey30===key&&$('lyrics')?.querySelector('.lyr-l')){this.applyStyle();return;}this.renderKey30=key;return render30(...args);};
// Hidden full-window ambience must not compete with the visible karaoke renderer.
const atmoRunning30=Atmo.running.bind(Atmo);Atmo.running=()=>!$('now')?.classList.contains('on')&&atmoRunning30();
// Accessible sibling actions, not buttons illegally nested inside another button.
const trackCard30=Views.trackCard.bind(Views);Views.trackCard=function(track,list,options){const card=trackCard30(track,list,options),shell=el('div','track-shell30'),actions=el('div','track-actions30');shell.append(card);for(const [key,ico,fn]of [['Like','heart',async()=>{await toggleLike(track);paint();}],['Add to playlist','lib',()=>Workspace.addToPlaylistDialog([track])]]){const b=el('button','ib',icon(ico));b.type='button';b.title=t(key);b.setAttribute('aria-label',t(key));b.onclick=e=>{e.stopPropagation();fn();};if(key==='Like'){b.dataset.like=track.id;var like=b;}actions.append(b);}function paint(){const yes=K.likes.has(track.id);like.classList.toggle('on',yes);like.title=t(yes?'Unlike':'Like');like.setAttribute('aria-label',like.title);like.setAttribute('aria-pressed',String(yes));}paint();shell.append(actions);return shell;};
const queue30=Views.renderQueue.bind(Views);Views.renderQueue=function(...args){const v=queue30(...args);clearTimeout(Player._warmTimer30);Player._warmTimer30=setTimeout(()=>Player.prefetchNext(),200);return v;};
const boot30=App.boot.bind(App);App.boot=async function(...a){await boot30(...a);Upgrade30.init();};
