/* Kryo UI v6. Additive UI layer: all audio, clip and karaoke engines retained. */
'use strict';
const InterfaceV6 = {
  tr(en, ru) { return t(en); },
  init(){
    document.body.classList.add('ui-v6');
    this.home(); this.sound(); this.settings(); this.dialog(); this.labelControls();
    addEventListener('keydown',e=>{
      if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&!/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)&&!e.target.isContentEditable&&!document.querySelector('.modal.on')&&K.view==='home'){
        e.preventDefault();$('homeQuery')?.focus();
      }
    });
  },
  home(){
    const head=$('vHome').querySelector('.studio-page-head');
    const badge=el('span','ui-home-badge',this.tr('A space for your sound','Место для твоей музыки'));badge.dataset.uiI18n='';head.querySelector('.studio-eyebrow').replaceWith(badge);
    const tabs=el('nav','ui-home-tabs');tabs.setAttribute('aria-label',this.tr('Music sections','Разделы музыки'));
    [[this.tr('Overview','Обзор'),()=>App.go('home'),true],[this.tr('Recently played','Недавние'),()=>App.openHistory()],[this.tr('Favourites','Любимое'),()=>App.openLiked()]].forEach(([label,fn,on])=>{const b=el('button',on?'on':'',esc(label));b.type='button';b.dataset.uiI18n='';b.onclick=fn;if(on)b.setAttribute('aria-current','page');tabs.appendChild(b);});head.after(tabs);
    const paint=Home.paintHero.bind(Home);Home.paintHero=rows=>{paint(rows);this.decorateHero();};
    this.decorateHero();
    $('homeQuickLabel').textContent=this.tr('MORE THAN MUSIC','БОЛЬШЕ, ЧЕМ МУЗЫКА');
    $('homeQuickLabel').dataset.uiI18n='';
    const side=el('div','ui-side-foot',`<span class="ui-side-dot"></span><span data-ui-i18n>${this.tr('Your personal music space','Твоя музыкальная территория')}</span>`);$('side').appendChild(side);
  },
  decorateHero(){
    const box=$('studioHero');if(!box)return;
    const kicker=box.querySelector('.home-kicker');kicker.textContent=this.tr('FIND YOUR NEXT FAVOURITE','НАЙДИ ТО, ЧТО ЗАЦЕПИТ');
    box.querySelector('h2').textContent=this.tr('Tune into\nyour own world.','На своей\nволне.');
    box.querySelector('p').textContent=this.tr('Your tracks, your discoveries. Search by name or paste a link — we’ll take it from here.','Любимые треки и новые открытия. Найди по названию или вставь ссылку — дальше мы сами.');
    const feature=box.querySelector('.home-feature');
    feature.setAttribute('aria-label',feature.textContent.trim());
    if(!feature.classList.contains('home-has-track')){
      feature.querySelector('img').remove();
      const vinyl=el('span','ui-vinyl');vinyl.setAttribute('aria-hidden','true');vinyl.innerHTML='<span class="ui-vinyl-label">K<span>33⅓ RPM</span></span>';feature.prepend(vinyl);
      feature.querySelector('strong').textContent=this.tr('It starts with a song','Начинается с одной песни');
      feature.querySelector('.home-feature-copy>span').textContent=this.tr('Find your first favourite','Найди свою первую любимую');
    }
    const hint=el('span','ui-search-hint',this.tr('Tip: press / to start searching','Подсказка: нажми / для быстрого поиска'));hint.dataset.uiI18n='';box.querySelector('.ui-search-hint')?.remove();box.querySelector('.home-search-form').after(hint);
  },
  sound(){
    const pane=document.querySelector('.pane[data-pane="sound"]');
    const head=el('section','ui-sound-intro',`<h2 data-ui-i18n>${this.tr('Hear it your way.','Услышать по-новому.')}</h2><p data-ui-i18n>${this.tr('Choose a starting point, then make it yours. Presets enable the equalizer.','Выбери характер звучания. Пресет включает эквалайзер — дальше можно настроить вручную.')}</p><div class="ui-sound-presets" id="uiSoundPresets"></div>`);pane.prepend(head);
    [['flat','Balanced','Ровно'],['bass','More bass','Больше баса'],['vocal','Clear vocals','Голос'],['lounge','Lounge','Лаунж']].forEach(([id,en,ru])=>{
      const b=el('button','chip',esc(this.tr(en,ru)));b.type='button';b.dataset.uiI18n='';b.dataset.uiEq=id;
      b.onclick=()=>{const preset=EQ_PRESETS.find(p=>p[0]===id);Equalizer.setAll(preset[2],id);if(!S.eqOn)Equalizer.toggle(true);this.syncSound();};$('uiSoundPresets').appendChild(b);
    });
    head.after($('setEq'));
    const value=el('span','ui-volume-value');value.id='uiVolumeValue';$('sVolume').closest('.set').querySelector('.l').appendChild(value);
    const sync=()=>{value.textContent=' · '+Math.round(S.volume)+'%';this.syncSound();};$('sVolume').addEventListener('input',sync);sync();
    addEventListener('kryonyx:settings-save',sync);
  },
  syncSound(){document.querySelectorAll('[data-ui-eq]').forEach(b=>{const selected=S.eqOn&&S.eqPreset===b.dataset.uiEq;b.classList.toggle('on',selected);b.setAttribute('aria-pressed',String(!!selected));});},
  labelControls(){
    document.querySelectorAll('#mSettings .set').forEach((row,i)=>{
      const label=row.querySelector('.l'),hint=row.querySelector('.h');if(!label)return;
      if(!label.id)label.id='ui-setting-label-'+i;if(hint&&!hint.id)hint.id='ui-setting-hint-'+i;
      row.querySelectorAll('input,select,textarea').forEach(control=>{if(!control.hasAttribute('aria-label')&&!control.hasAttribute('aria-labelledby'))control.setAttribute('aria-labelledby',label.id);if(hint)control.setAttribute('aria-describedby',hint.id);});
    });
  },
  settings(){
    const nav=$('setTabs');
    const groups=[['workspace','START HERE','ГЛАВНОЕ'],['look','PERSONALISATION','ПЕРСОНАЛИЗАЦИЯ'],['sound','MUSIC & TOOLS','МУЗЫКА И ИНСТРУМЕНТЫ'],['data','APPLICATION','ПРИЛОЖЕНИЕ']];
    groups.forEach(([pane,en,ru])=>{const b=nav.querySelector(`[data-pane="${pane}"]`);const title=el('div','ui-settings-group',this.tr(en,ru));title.dataset.uiI18n='';b.before(title);});
    const header=$('mSettings').querySelector('.workspace-settings-head');
    header.querySelector('.studio-eyebrow').textContent=this.tr('MAKE IT YOURS','ПОДСТРОЙ ПОД СЕБЯ');
    const sub=el('p','ui-settings-description');sub.id='uiSettingsDescription';sub.dataset.uiI18n='';header.querySelector('div').appendChild(sub);
    const status=el('button','ui-save-status',this.tr('Changes save automatically','Изменения сохраняются автоматически'));status.id='uiSaveStatus';status.type='button';status.dataset.uiI18n='';status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.onclick=()=>{if(status.dataset.state==='error')saveSettings(true);};header.lastElementChild.before(status);
    addEventListener('kryonyx:settings-save',e=>{
      const state=SAFE?'safe':e.detail;status.dataset.state=state;
      status.textContent=state==='pending'?this.tr('Saving…','Сохраняем…'):state==='saved'?this.tr('Saved on this device','Сохранено на устройстве'):this.tr('Server save failed · retry','Не сохранено в базе · повторить');
    });
    if(SAFE){status.textContent=this.tr('Safe mode · changes are not saved','Безопасный режим · без сохранения');status.dataset.state='safe';}
    const overview=document.querySelector('.pane[data-pane="workspace"]');
    overview.querySelector('h2').textContent=this.tr('A player that feels like you.','Плеер, в котором всё по-твоему.');
    overview.querySelector('p').textContent=this.tr('Start with the essentials. Advanced controls stay one click away.','Начни с главного. Тонкие настройки — всегда в одном клике.');
    const cards=$('workspaceSettingsLinks');cards.replaceChildren();
    [['themes','palette','Appearance','Оформление','Themes, colours and cover art','Темы, цвета и обложки'],['sound','vol','Sound','Звук','Equalizer, volume and transitions','Эквалайзер, громкость и переходы'],['karaoke','lyrics','Karaoke','Караоке','Lyrics, timing and atmosphere','Текст, тайминги и атмосфера'],['lib','lib','Sources','Источники','Music libraries and availability','Музыкальные библиотеки и доступность']].forEach(([pane,ico,en,ru,de,dr])=>{
      const b=el('button','ui-settings-card',`${icon(ico)}<strong data-ui-i18n>${this.tr(en,ru)}</strong><span data-ui-i18n>${this.tr(de,dr)}</span>${icon('next','ui-card-arrow')}`);b.type='button';b.onclick=()=>this.openPane(pane);cards.appendChild(b);
    });
    const appearance=el('section','ui-quick-appearance',`<div class="ui-section-title"><h3 data-ui-i18n>${this.tr('Your atmosphere','Твоя атмосфера')}</h3><span data-ui-i18n>${this.tr('Only changes the theme','Меняет только тему')}</span></div><div class="ui-theme-choices" id="uiThemeChoices"></div>`);cards.after(appearance);
    [['studio6','Graphite','Графит','dark'],['daylight6','Daylight','Светлая','light'],['nebula','Nebula','Туманность','purple']].forEach(([id,en,ru,style])=>{
      const b=el('button','ui-theme-choice '+style,`<span class="ui-theme-preview" aria-hidden="true"><i></i><i></i><i></i></span><span data-ui-i18n>${this.tr(en,ru)}</span><span class="ui-theme-check">${icon('check','ic s')}</span>`);b.type='button';b.dataset.themeId=id;b.onclick=()=>{useTheme(id);App.syncSettingsUI();this.syncThemes();};$('uiThemeChoices').appendChild(b);
    });
    const simple=el('div','ui-quick-options');
    [['noAnim','Less motion','Меньше движения','A calmer interface without animations','Спокойный интерфейс без анимаций'],['normalize','Even volume','Ровная громкость','Reduce loudness differences between tracks','Уменьшить перепады громкости между треками']].forEach(([key,en,ru,de,dr])=>{
      const row=el('label','set ui-quick-option',`<span><span class="l" data-ui-i18n>${this.tr(en,ru)}</span><span class="h" data-ui-i18n>${this.tr(de,dr)}</span></span><input type="checkbox" data-ui-pref="${key}">`);
      row.querySelector('input').onchange=e=>{const target=document.querySelector(`.sw[data-sw="${key}"]`);if(target){if(!!S[key]!==e.target.checked)target.click();}else{S[key]=e.target.checked;saveSettings();applyTheme();}this.syncPrefs();};simple.appendChild(row);
    });$('workspacePreferenceControls').appendChild(simple);
    let lastPrefs38='';new MutationObserver(()=>{const key=JSON.stringify([S.theme,S.noAnim,S.normalize]);if(key===lastPrefs38)return;lastPrefs38=key;if($('mSettings').classList.contains('on')){this.syncThemes();this.syncPrefs();}}).observe(document.body,{attributes:true,attributeFilter:['class']});
    const open=App.openPane.bind(App);App.openPane=name=>{open(name);const button=nav.querySelector(`[data-pane="${CSS.escape(name)}"]`);nav.querySelectorAll('[data-pane]').forEach(b=>b.setAttribute('aria-current',b===button?'page':'false'));sub.textContent=this.paneDescription(name);this.syncPrefs();this.syncThemes();this.syncSound();};
    const info=el('div','ui-search-results');info.id='uiSettingsSearchInfo';info.setAttribute('role','status');info.setAttribute('aria-live','polite');info.hidden=true;document.querySelector('.set-body').prepend(info);
    $('setFind').setAttribute('aria-label',this.tr('Search all settings','Поиск по всем настройкам'));
    App.openPane('workspace');
  },
  paneDescription(name){const descriptions={workspace:['The essentials, all in one place','Главное — в одном месте'],look:['Comfort, motion and window behaviour','Удобство, анимации и поведение окна'],themes:['Choose a palette or fine-tune your own','Выбери палитру или настрой свою'],sound:['Make every track sound right','Настрой звучание под себя'],karaoke:['Lyrics and performance, your way','Текст и исполнение в твоём стиле'],lib:['Manage where your music comes from','Управляй источниками своей музыки'],data:['Storage, history and safe cleanup','Хранилище, история и очистка'],keys:['Less clicking. More listening.','Меньше кликов. Больше музыки.']};return this.tr(...(descriptions[name]||['Fine-tune your player','Тонкая настройка плеера']));},
  openPane(name){$('setFind').value='';this.searchRun?.();App.openPane(name);},
  syncThemes(){document.querySelectorAll('[data-theme-id]').forEach(b=>{const selected=S.theme===b.dataset.themeId;if(b.classList.contains('on')!==selected)b.classList.toggle('on',selected);if(b.getAttribute('aria-pressed')!==String(selected))b.setAttribute('aria-pressed',String(selected));});},
  syncPrefs(){document.querySelectorAll('[data-ui-pref]').forEach(n=>n.checked=!!S[n.dataset.uiPref]);},
  bindSettingsSearch(){
    const field=$('setFind'),body=document.querySelector('.set-body');if(!field||!body)return;
    const saved=new Map();const norm=s=>s.toLocaleLowerCase().replace(/ё/g,'е');
    const restore=()=>{saved.forEach((value,node)=>{node.style.display=value;});saved.clear();body.classList.remove('finding');$('uiSettingsSearchInfo')?.setAttribute('hidden','');};
    this.searchRun=()=>{
      restore();const q=norm(field.value.trim());if(!q)return;
      const hide=(node,display)=>{if(!saved.has(node))saved.set(node,node.style.display);node.style.display=display;};
      body.classList.add('finding');let matches=0;
      body.querySelectorAll('.pane').forEach(pane=>{
        const tab=$('setTabs').querySelector(`[data-pane="${CSS.escape(pane.dataset.pane)}"]`);const bySection=norm(tab?.textContent||'').includes(q);
        let count=0;pane.querySelectorAll('.set').forEach(row=>{const yes=bySection||norm(row.textContent+' '+(row.querySelector('[data-sw]')?.dataset.sw||'')).includes(q);hide(row,yes?'':'none');if(yes)count++;});
        if(bySection){count=Math.max(1,count);}else{
          [...pane.children].forEach(n=>{if(!n.matches('.set')&&!n.querySelector('.set'))hide(n,'none');});
          pane.querySelectorAll('h3,h4,.hint,.ui-section-title').forEach(n=>hide(n,'none'));
        }
        let title=pane.querySelector('.ui-search-pane-title');if(!title){title=el('h3','ui-search-pane-title');title.dataset.uiI18n='';pane.prepend(title);}title.textContent=tab?.textContent.trim()||pane.dataset.pane;hide(title,count?'block':'none');hide(pane,count?'block':'none');matches+=count;
      });
      const info=$('uiSettingsSearchInfo');if(info){info.hidden=false;info.textContent=matches?this.tr('Matches: ','Найдено: ')+matches:this.tr('Nothing found. Try “sound”, “theme” or “volume”.','Ничего не найдено. Попробуй «звук», «тема» или «громкость».');}
      body.scrollTop=0;
    };
    field.addEventListener('input',debounce(()=>this.searchRun(),120));
    field.addEventListener('keydown',e=>{if(e.key==='Escape'&&field.value){e.preventDefault();e.stopPropagation();field.value='';this.searchRun();}});
    $('setTabs').addEventListener('click',e=>{if(e.target.closest('[data-pane]')){field.value='';restore();}});
  },
  dialog(){
    const modal=$('mSettings');modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby','workspaceSettingsTitle');
    let previous=null;let on=false;
    new MutationObserver(()=>{
      const visible=modal.classList.contains('on');if(visible===on)return;on=visible;
      if(visible){previous=document.activeElement;requestAnimationFrame(()=>$('setFind').focus());}
      else if(previous?.isConnected&&!document.querySelector('.modal.on'))previous.focus();
    }).observe(modal,{attributes:true,attributeFilter:['class']});
    modal.addEventListener('keydown',e=>{
      if(e.key!=='Tab')return;const nodes=[...modal.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter(n=>n.getClientRects().length&&!n.closest('[hidden]'));
      const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
    });
  }
};
