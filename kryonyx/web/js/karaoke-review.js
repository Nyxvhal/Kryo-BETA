/* Diagnostic labels are deliberately conservative: timed != correct. */
'use strict';
const KaraokeReview = {
  label(en,ru){return t(en);},
  describe(data){
    const d=data.document||data, q=data.quality||d.quality||{}, a=d.alignment||{};
    const warnings=q.warnings||[];
    const texts={partial_word_text:['Word marks do not cover the complete line','Метки слов не покрывают всю строку'],refinement_skipped:['Timing refinement skipped; ASR timing retained','Уточнение пропущено; сохранены метки ASR'],asr_draft:['Automatic transcript · draft','Автораспознавание · черновик'],light_model:['Fast model: unreliable on vocals','Быстрая модель: ненадёжна на вокале'],timing_estimated:['Word timing needs listening review','Метки слов нужно проверить на слух'],line_only:['Line timing only','Только метки строк'],low_confidence:['Low-confidence words','Есть неуверенно распознанные слова'],short_words:['Very short word intervals','Есть слишком короткие метки'],long_words:['Long word intervals','Есть длинные метки слов'],repetition:['Repetitions: compare with recording','Повторы: сравните с записью'],outside_audio:['Timing outside audio duration','Метки выходят за длину аудио']};
    let title=q.reviewed?this.label('Reviewed by you','Проверено вами'):a.forced?this.label('Reference aligned · check timing','Текст выровнен · проверьте тайминги'):a.engine?this.label('ASR draft · check text and timing','Черновик ASR · проверьте текст и тайминги'):data.synced||d.lines?.length?this.label('Imported · not checked','Импорт · не проверено'):this.label('No synchronized lyrics','Нет синхронизированного текста');
    return {title,warnings:warnings.map(k=>this.label(...(texts[k]||[k,k]))),reviewed:!!q.reviewed};
  },
  mount(){
    if($('kStage'))return;const stage=el('div','k-stage');stage.id='kStage';
    const status=el('div','k-stage-status');status.id='kStageStatus';status.textContent=this.label('Prepare lyrics for this recording','Подготовьте текст для этой записи');stage.appendChild(status);
    const actions=el('div','k-stage-actions');
    const select=el('select');select.id='kTimingMode';select.setAttribute('aria-label',this.label('Highlight mode','Режим подсветки'));
    [['line','Lines','Строки']].forEach(([v,en,ru])=>{const o=el('option','',this.label(en,ru));o.value=v;select.appendChild(o);});select.value='line';select.onchange=()=>{S.karaokeTiming=select.value;saveSettings();Karaoke.render();Karaoke.resync();Disc.reset();};actions.appendChild(select);
    const edit=el('button','btn g',this.label('Edit timing','Править тайминги'));edit.id='kEditNow';edit.disabled=true;edit.onclick=()=>KaraokeEditor.openCurrent();actions.appendChild(edit);
    const gen=el('button','btn',this.label('Prepare lyrics','Подготовить текст'));gen.onclick=()=>KaraokeTools.open();actions.appendChild(gen);stage.appendChild(actions);$('nowTop').after(stage);
  },
  loaded(data){
    this.mount();const info=this.describe(data);$('kStageStatus').textContent=info.title;$('kStageStatus').title=info.warnings.join('\n');$('kStageStatus').classList.toggle('reviewed',info.reviewed);
    $('kEditNow').disabled=!data.document;
    S.karaokeTiming='line';$('kTimingMode').value='line';
  }
};
