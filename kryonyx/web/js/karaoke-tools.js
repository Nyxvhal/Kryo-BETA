/* UI for the existing lyric service. Processing is a local subprocess, not a
   second player; no audio listeners or animation loops are added here. */
'use strict';
const KaraokeTools = {
  job:null, pollTimer:null, track:null,
  label(en,ru){return t(en);},
  init(){
    if($('mKaraokeGenerate'))return;
    const modal=el('div','modal wide');modal.id='mKaraokeGenerate';modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby','kgTitle');
    modal.innerHTML=`<div class="mh"><h3 id="kgTitle">${this.label('Karaoke studio','Студия караоке')}</h3><button class="ib" data-close aria-label="${this.label('Close','Закрыть')}">${icon('close')}</button></div>
      <div class="mb karaoke-generator"><div class="k-workflow"><span>01 · <span>${this.label('Audio','Аудио')}</span></span><span>02 · <span>${this.label('Correct lyrics','Правильный текст')}</span></span><span>03 · <span>${this.label('Review','Проверка')}</span></span></div><p id="kgHardware" class="hint"></p>
      <p class="hint">${this.label('Local processing. First use downloads model weights. No audio is sent to a cloud API. Without a file, the completed audio cache of the current track is used.','Локальная обработка. При первом запуске скачиваются веса модели. Аудио не отправляется в облачный API. Без файла используется готовый аудиокэш текущего трека.')}</p>
      <div class="karaoke-form-grid"><label>${this.label('Audio file · up to 256 MiB / 1 hour','Аудиофайл · до 256 МиБ / 1 часа')}<input id="kgAudio" type="file" accept="audio/*,.webm,.mp4"></label>
      <label>${this.label('Correct lyrics file','Файл с правильным текстом')}<input id="kgReference" type="file" accept=".txt,.lrc,.srt,.ttml,.xml,.json"></label>
      </div><details class="k-generator-advanced"><summary>${this.label('Language, model and hardware','Язык, модель и оборудование')}</summary><div class="karaoke-form-grid"><label>${this.label('Language','Язык')}<select id="kgLanguage"><option value="auto">Auto</option><option value="en">English</option><option value="ru">Русский</option><option value="ja">日本語</option><option value="ko">한국어</option><option value="zh">中文</option><option value="es">Español</option><option value="de">Deutsch</option><option value="fr">Français</option></select></label>
      <label>${this.label('Model','Модель')}<select id="kgModel"><option value="small">small</option><option value="medium">medium</option><option value="base">base</option><option value="tiny">tiny</option><option value="large-v3">large-v3</option></select></label>
      <label>${this.label('Engine','Движок')}<select id="kgEngine"><option value="auto">Auto</option><option value="faster-whisper">faster-whisper · ASR</option><option value="stable-ts">${t('stable-ts · alignment')}</option></select></label>
      <label>${this.label('Hardware','Оборудование')}<select id="kgDevice"><option value="auto">${t('Auto · GPU / CPU')}</option><option value="cpu">CPU</option><option value="cuda">${t('CUDA → CPU fallback')}</option></select></label></div>
      </details><label class="k-reference-label">${this.label('Or paste the correct lyrics · keep line breaks','Или вставьте правильный текст · сохраните переносы строк')}<textarea id="kgText" rows="5" placeholder="${this.label('Lyrics must match this exact recording','Текст должен соответствовать именно этой записи')}"></textarea></label>
      <label class="karaoke-check"><input id="kgDraft" type="checkbox">${this.label('No lyrics: generate an ASR draft (can contain wrong words)','Нет текста: создать черновик ASR (возможны неверные слова)')}</label>
      <p class="k-notice">${this.label('No result is applied automatically. Review text and timing before replacing saved lyrics. Tiny/base are diagnostics only for singing; a larger model is not a guarantee.','Результат не применяется автоматически. Перед заменой проверьте слова и тайминги. Tiny/base — только быстрый тест на вокале; крупная модель тоже не даёт гарантии.')}</p>
      <label class="karaoke-check"><input id="kgRefine" type="checkbox" checked>${this.label('Refine ASR timing with stable-ts (does not correct wrong lyrics)','Уточнить тайминги ASR через stable-ts (не исправляет неверный текст)')}</label>
      <label class="karaoke-check"><input id="kgSeparation" type="checkbox">${this.label('Separate vocals (optional Demucs installation)','Отделить вокал (нужен необязательный Demucs)')}</label>
      <label class="karaoke-check"><input id="kgBind" type="checkbox"> <span id="kgBindText"></span></label>
      <p class="hint">${this.label('Reference text uses forced alignment, not an ASR prompt. Verify that it matches this recording. Word timestamps are estimates; syllable timings are used only when explicitly supplied.','Предоставленный текст используется для forced alignment, а не как подсказка распознавания. Текст должен совпадать с записью. Тайминги слов — оценка модели; тайминги слогов используются только при явной разметке.')}</p>
      <progress id="kgProgress" max="1" value="0" aria-label="${this.label('Processing progress','Ход обработки')}"></progress><p id="kgStatus" role="status" aria-live="polite"></p><div id="kgQuality" class="k-notice" hidden></div><button id="kgReview" class="btn" hidden>${this.label('Review result','Проверить результат')}</button><a id="kgDownload" class="btn g" hidden>${this.label('Download Karaoke JSON','Скачать Karaoke JSON')}</a></div>
      <div class="acts"><button class="btn g" id="kgCancel" disabled>${this.label('Cancel processing','Отменить обработку')}</button><button class="btn" id="kgStart">${this.label('Generate synchronized lyrics','Создать синхронизацию')}</button></div>`;
    document.body.appendChild(modal);
    modal.addEventListener('keydown',event=>{
      if(event.key==='Escape'){event.preventDefault();closeModals();clearTimeout(this.pollTimer);this.returnFocus?.focus();}
      if(event.key!=='Tab')return;
      const controls=[...modal.querySelectorAll('button,input,select,a[href]')].filter(n=>!n.disabled&&n.getClientRects().length);
      const first=controls[0],last=controls[controls.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    });
    modal.querySelector('[data-close]').onclick=()=>{closeModals();clearTimeout(this.pollTimer);};
    $('kgStart').onclick=()=>this.generate();$('kgCancel').onclick=()=>this.cancel();
    $('kgReview').onclick=()=>this.review();
    this.mount();
    KaraokeReview.mount();
    this.hardwareTask=api("/api/karaoke/hardware",{timeout:35000}).catch(e=>({error:e.message}));
  },
  mount(){
    const find=$('kFind');if(!find||$('karaokeV2Settings'))return;
    const root=el('div','karaoke-v2-settings');root.id='karaokeV2Settings';
    const heading=el('h4','',this.label('Karaoke studio','Студия караоке'));root.appendChild(heading);
    const modes=el('div','row-acts');modes.setAttribute('aria-label',this.label('Timing mode','Режим синхронизации'));
    [['line','Lines','Строки']].forEach(([value,en,ru])=>{
      const b=el('button','chip',this.label(en,ru));b.dataset.timing=value;b.setAttribute('aria-pressed',String('line'===value));b.classList.toggle('on','line'===value);
      b.onclick=()=>{S.karaokeTiming=value;saveSettings();modes.querySelectorAll('button').forEach(n=>{n.classList.toggle('on',n===b);n.setAttribute('aria-pressed',String(n===b));});Karaoke.render();Karaoke.resync();Disc.reset();};modes.appendChild(b);
    });root.appendChild(modes);
    root.appendChild(el('p','hint',this.label('Whole lines follow the recording timestamps. Word marks remain available for timing edits.','Строки подсвечиваются целиком по меткам записи. Метки слов остаются доступны в редакторе таймингов.')));
    const actions=el('div','row-acts');const generate=el('button','btn',this.label('Generate synchronized lyrics','Создать синхронизацию'));generate.onclick=()=>this.open();actions.appendChild(generate);
    const importLabel=el('label','btn g',this.label('Import lyrics','Импорт текста'));const input=el('input');input.type='file';input.id='karaokeImportFile';input.accept='.json,.lrc,.txt,.srt,.ttml,.xml';input.className='karaoke-import-file';input.setAttribute('aria-label',this.label('Import lyrics','Импорт текста'));input.onchange=()=>this.importFile(input);importLabel.appendChild(input);actions.appendChild(importLabel);root.appendChild(actions);
    const offsetRow=el('label','karaoke-offset',this.label('Track offset (positive = lyrics earlier)','Поправка трека (плюс = текст раньше)'));
    const offset=el('input');offset.id='karaokeExactOffset';offset.type='number';offset.min='-30';offset.max='30';offset.step='.01';offset.value=0;offset.onchange=()=>{const current=+Karaoke.offsets[Karaoke.trackId]||0;if(!Player.current||Player.current.id!==Karaoke.trackId||offset.value.trim()===''||!Number.isFinite(Number(offset.value))){offset.value=current;return;}const v=Math.max(-30,Math.min(30,Number(offset.value)));Karaoke.nudge(v-current);};offsetRow.appendChild(offset);root.appendChild(offsetRow);
    const preset=el('div','row-acts');[-2,-1,-.5,0,.5,1,2].forEach(v=>{const b=el('button','chip',(v>0?'+':'')+v+'s');b.onclick=()=>{if(!Player.current||Player.current.id!==Karaoke.trackId)return;Karaoke.nudge(v-(+Karaoke.offsets[Karaoke.trackId]||0));};preset.appendChild(b);});root.appendChild(preset);
    const speedRow=el('label','karaoke-offset',this.label('Playback speed','Скорость воспроизведения'));const speed=el('select');speed.id='karaokePlaybackSpeed';[.5,.75,1,1.25,1.5,2].forEach(v=>{const o=el('option','',v+'×');o.value=v;speed.appendChild(o);});speed.onchange=()=>{const value=Number(speed.value);if(typeof Sound72!=='undefined'&&Sound72.setSpeed)Sound72.setSpeed(value);else{S.playbackSpeed=value;Player.deck.forEach(a=>{a.playbackRate=value;});saveSettings();Karaoke.resync();}};speedRow.appendChild(speed);root.appendChild(speedRow);
    const variants=el('select');variants.id='karaokeVariant';variants.setAttribute('aria-label',this.label('Lyric variant','Вариант текста'));variants.hidden=true;variants.onchange=()=>{Karaoke.variant=variants.value;dropCache('/api/lyrics');Karaoke.fetchLyrics(Player.current);};root.appendChild(variants);
    const badge=el('p','hint');badge.id='karaokePrecision';root.appendChild(badge);
    const reset=el('button','btn g',this.label('Remove imported/generated lyrics','Удалить локальную разметку'));reset.onclick=async()=>{if(!Player.current)return;if(!confirm(this.label('Remove the saved local lyric document?','Удалить сохранённую локальную разметку?')))return;const id=Player.current.id;try{await api('/api/karaoke/document?'+new URLSearchParams({track_id:id}),{method:'DELETE'});dropCache('/api/lyrics');if(Player.current?.id===id){Karaoke.variant='';Karaoke.onTrack(Player.current,{force:true});}}catch(e){toast(e.message);}};root.appendChild(reset);
    find.closest('.set').after(root);
    this.syncSettingsControls();addEventListener('kryonyx:settings-save',()=>this.syncSettingsControls());
    const top=$('nowTop');if(top){const b=el('button','ib');b.id='karaokeGenerateNow';b.innerHTML=icon('lyrics');b.title=this.label('Generate / import synchronized lyrics','Создать / импортировать синхронизацию');b.setAttribute('aria-label',b.title);b.onclick=()=>this.open();top.appendChild(b);}
  },
  syncSettingsControls(){
    const speed=$('karaokePlaybackSpeed');if(!speed)return;const value=String(+S.playbackSpeed||1);
    const custom=speed.querySelector('[data-custom-speed]');if(custom&&custom.value!==value)custom.remove();
    if(![...speed.options].some(o=>o.value===value)){const option=el('option','',value+'×');option.value=value;option.dataset.customSpeed='';speed.append(option);}
    speed.value=value;
  },
  resetTrack(){
    this.syncSettingsControls();
    const variants=$('karaokeVariant');if(variants){variants.textContent='';variants.hidden=true;}
    const badge=$('karaokePrecision');if(badge)badge.textContent='';
    KaraokeReview.loaded({});
  },
  loaded(data){
    KaraokeReview.loaded(data);
    const offset=$('karaokeExactOffset');if(offset)offset.value=+Karaoke.offsets[Karaoke.trackId]||0;
    const variants=$('karaokeVariant');if(variants){variants.textContent='';const list=data.variants||[];variants.hidden=!list.length;if(list.length){const o=el('option','',this.label('Original','Оригинал'));o.value='';variants.appendChild(o);list.forEach(v=>{const op=el('option','',v.label||v.language||v.id);op.value=v.id;variants.appendChild(op);});variants.value=Karaoke.variant||'';}}
    const badge=$('karaokePrecision');if(badge){const words=data.lines?.flatMap(l=>l.words||[])||[];badge.textContent=data.precise?this.label('Karaoke JSON / imported timestamps.','Karaoke JSON / импортированные тайминги.')+(words.some(w=>w.syllables?.length)?this.label(' Supplied syllables available.',' Есть размеченные слоги.'):this.label(' No acoustic syllable timing: word interpolation.',' Акустических таймингов слогов нет: интерполяция слов.')):data.words?this.label('Source word timing.','Пословные метки источника.'):data.synced?this.label('LRC: word timing is estimated, not aligned.','LRC: время слов приблизительное, точной синхронизации нет.'):this.label('Plain lyrics / no timestamps.','Обычный текст / нет таймингов.');}
  },
  async open(){
    this.track=Player.current?{...Player.current}:null;
    $('kgBind').checked=!!this.track;$('kgBind').disabled=!this.track;
    $('kgBindText').textContent=this.track?this.label('Target recording after review: ','Целевая запись после проверки: ')+this.track.title:this.label('No current track: download a standalone JSON','Нет текущего трека: сохраните отдельный JSON');
    this.returnFocus=document.activeElement;
    openModal('mKaraokeGenerate');$('kgAudio').focus();
    $('kgHardware').textContent=this.label('Checking local worker…','Проверяю локальный worker…');
    try{const h=await this.hardwareTask;$('kgHardware').textContent=`CPU: ✓ · CUDA: ${h.cuda||h.torch_cuda?'✓':'—'} · ASR: ${h.faster_whisper?'✓':'—'} · alignment: ${h.stable_ts?'✓':'—'}${h.error?' · '+h.error:''}`;}catch(e){$('kgHardware').textContent=e.message;}
    if(this.job)this.poll();
  },
  async importFile(input){
    const f=input.files[0];if(!f)return;
    try{if(!Player.current)throw new Error(this.label('Choose a track first','Сначала выберите трек'));if(f.size>2*1024*1024)throw new Error('Max 2 MiB');
      const id=Player.current.id;
      await api('/api/karaoke/document',{method:'PUT',body:{track_id:id,filename:f.name,source:await f.text()}});
      dropCache('/api/lyrics');if(Player.current?.id===id){Karaoke.variant='';await Karaoke.onTrack(Player.current,{force:true});}toast(this.label('Lyrics imported','Разметка импортирована'));
    }catch(e){toast(e.message);}finally{input.value='';}
  },
  async generate(){
    if(this.job)return;
    const audio=$('kgAudio').files[0],ref=$('kgReference').files[0];
    const pasted=$('kgText').value.trim();
    try{if(audio&&audio.size>256*1024*1024)throw new Error('Max audio 256 MiB');if(ref&&ref.size>2*1024*1024)throw new Error('Max lyrics 2 MiB');
      if(ref&&pasted)throw new Error(this.label('Use a lyrics file OR pasted text, not both','Используйте файл текста ИЛИ поле текста, не оба сразу'));
      if(!ref&&!pasted&&!$('kgDraft').checked)throw new Error(this.label('Provide correct lyrics or explicitly choose ASR draft','Добавьте правильный текст или явно выберите черновик ASR'));
      if(!ref&&!pasted&&$('kgEngine').value==='stable-ts'&&$('kgModel').value==='large-v3-turbo')throw new Error('Choose small, medium or large-v3');
      const body=new FormData();body.append('auto_bind','false');if(pasted){body.append('reference',pasted);body.append('reference_name','reference.txt');}if(audio)body.append('audio',audio);if(ref){body.append('reference',await ref.text());body.append('reference_name',ref.name);}
      if($('kgBind').checked&&this.track)body.append('track_id',this.track.id);
      else if(!audio)throw new Error(this.label('Choose an audio file','Выберите аудиофайл'));
      ['language','model','engine','device'].forEach(k=>body.append(k,$('kg'+k[0].toUpperCase()+k.slice(1)).value));body.append('separate',String($('kgSeparation').checked));body.append('refine',String($('kgRefine').checked));
      const response=await fetch('/api/karaoke/generate',{method:'POST',body});const result=await response.json();if(!response.ok)throw new Error(result.error||'Processing failed');
      this.job=result.id;this.pending={track:$('kgBind').checked?this.track:null,audio};this.resultId=null;$('kgReview').hidden=true;$('kgQuality').hidden=true;$('kgDownload').hidden=true;$('kgStart').disabled=true;$('kgCancel').disabled=false;this.poll();
    }catch(e){$('kgStatus').textContent=e.message;$('kgStatus').scrollIntoView({block:'nearest'});}
  },
  async poll(){
    clearTimeout(this.pollTimer);const id=this.job;if(!id)return;
    try{const info=await api('/api/karaoke/jobs/'+id,{timeout:10000});if(this.job!==id)return;
      const names={queued:'В очереди',starting:'Запуск',hardware:'Оборудование',separating:'Отделение вокала','loading-model':'Загрузка модели',recognizing:'Распознавание',aligning:'Привязка текста','refining':'Уточнение таймингов черновика','refinement-skipped':'Уточнение пропущено','detecting-language':'Определение языка',saving:'Сохранение',finishing:'Завершение',done:'Готово',error:'Ошибка',cancelled:'Отменено','cpu-fallback':'Переход на CPU'};
      const progress=$('kgProgress');if(info.total_seconds){progress.value=Math.min(1,info.processed_seconds/info.total_seconds||0);}else progress.removeAttribute('value');
      $('kgStatus').textContent=(this.label(info.stage,names[info.stage]||info.stage))+(info.processed_seconds?' · '+fmt(info.processed_seconds)+' / '+fmt(info.total_seconds):'')+(info.error?' · '+info.error:'')+(info.cached?this.label(' · reused cache',' · использован кэш'):'');
      if(['done','error','cancelled'].includes(info.stage)){
        this.job=null;$('kgStart').disabled=false;$('kgCancel').disabled=true;
        if(info.stage==='done'){this.resultId=id;progress.value=1;$('kgDownload').href='/api/karaoke/jobs/'+id+'/result';$('kgDownload').hidden=false;$('kgReview').hidden=false;const q=KaraokeReview.describe({quality:info.quality});$('kgQuality').textContent=this.label('Draft ready. Nothing replaced. ','Черновик готов. Ничего не заменено. ')+q.warnings.join(' · ');$('kgQuality').hidden=false;$('kgReview').scrollIntoView({block:'nearest'});}
        return;
      }
    }catch(e){$('kgStatus').textContent=e.message;}
    if(this.job&&$('mKaraokeGenerate').classList.contains('on'))this.pollTimer=setTimeout(()=>this.poll(),1000);
  },
  async review(){try{const document=await api('/api/karaoke/jobs/'+this.resultId+'/result',{timeout:10000});await KaraokeEditor.open(document,this.pending?.track,this.pending?.audio);}catch(e){$('kgStatus').textContent=e.message;}},
  async cancel(){const id=this.job;if(!id)return;await api('/api/karaoke/jobs/'+id,{method:'DELETE'});this.poll();}
};
